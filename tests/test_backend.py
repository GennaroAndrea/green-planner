"""Backend API tests (Phase 2.5) on synthetic artefacts written to a temp dir (Q32).

The fixture follows docs/artefacts.md and computes IPF, classes, ranks and sensitivity with the
pipeline's own functions, like `pipeline build` does. A last smoke test runs against the real
data/processed/ when it has been built, and is skipped otherwise.
"""

import json
import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box

from backend.main import DEFAULT_DATA_DIR, create_app
from backend.store import Store, WeightsError, parse_weights
from pipeline.model import compute_ipf, quantile_classes, ranks_desc, score_matrix
from pipeline.sensitivity import one_at_a_time, run_sensitivity, sample_weights

ACTIVE = ["pollution", "green_deficit", "traffic", "population"]
INACTIVE = ["industry"]
RAW = {
    "pollution": "pollution_ratio",
    "green_deficit": "green_share",
    "traffic": "traffic_index",
    "population": "density_km2",
}
DEFAULT_PP = {"pollution": 20, "green_deficit": 30, "traffic": 20, "population": 20}
EFFECTIVE = {k: v / 90 for k, v in DEFAULT_PP.items()}
SENS = {
    "runs": 200,
    "spread_pp": 5,
    "top_n_zones": 3,
    "top_share_cells": 0.2,
    "robust_threshold": 0.8,
    "one_at_a_time_delta_pp": 10,
    "seed": 42,
}
CUSTOM = "pollution:10,green_deficit:50,traffic:25,population:15"


def _no_nan(text: str):
    def fail(c):
        raise ValueError(f"non-JSON constant {c}")

    return json.loads(text, parse_constant=fail)


def _score_frame(n: int, analysed: np.ndarray, rng: np.random.Generator, top_n: int):
    """Scores, raw values, IPF, classes, ranks and sensitivity, as `pipeline build` makes them."""
    df = pd.DataFrame({"analysed": analysed})
    for k in ACTIVE:
        df[RAW[k]] = rng.uniform(0, 1, n)
        df[f"score_{k}"] = np.where(analysed, rng.uniform(0, 100, n), np.nan)
    w = np.array([EFFECTIVE[k] for k in ACTIVE])
    df["ipf"] = np.where(analysed, score_matrix(df, ACTIVE) @ w, np.nan)
    for k in ACTIVE:
        df[f"contrib_{k}"] = df[f"score_{k}"] * EFFECTIVE[k]
    df["ipf_class"], edges = quantile_classes(df["ipf"].to_numpy())
    for col in ("green_deficit_m2", "plantable_m2"):
        df[col] = np.where(analysed, rng.uniform(0, 5000, n), np.nan)
    df["trees_new"] = pd.array(np.where(analysed, rng.integers(0, 80, n), 0), dtype="Int64")
    df.loc[~analysed, "trees_new"] = pd.NA
    df["residents"] = rng.integers(0, 3000, n).astype(float)
    df["vulnerable"] = (df["residents"] * 0.3).round()

    scores = score_matrix(df[analysed], ACTIVE)
    runs = sample_weights(w, SENS["spread_pp"], SENS["runs"], SENS["seed"])
    table, summary = run_sensitivity(scores, w, runs, top_n, SENS["robust_threshold"])
    summary["one_at_a_time"] = one_at_a_time(scores, w, ACTIVE, 10, top_n)
    table.index = df.index[analysed]
    df = df.join(table)
    for col in ("rank", "rank_p5", "rank_p95"):
        df[col] = df[col].astype("Int64")
    df["robust"] = df["robust"].astype("boolean")
    return df, edges, summary


def _cells(size: int, cols: int, rows: int, rng: np.random.Generator):
    n = cols * rows
    step = size / 100_000  # degrees, roughly
    geoms = [
        box(16.8 + c * step, 41.1 + r * step, 16.8 + (c + 1) * step, 41.1 + (r + 1) * step)
        for r in range(rows)
        for c in range(cols)
    ]
    zone_id = np.array([1 + (i % 3) for i in range(n)])  # zone 3 is not covered
    analysed = zone_id != 3
    top_n = math.ceil(SENS["top_share_cells"] * analysed.sum())
    df, edges, summary = _score_frame(n, analysed, rng, top_n)
    df.insert(0, "cell_id", [f"{size}-{i % cols}-{i // cols}" for i in range(n)])
    df["zone_id"] = pd.array(zone_id, dtype="Int64")
    df["zone_covered"] = zone_id != 3
    df["area_m2"] = float(size * size)
    df["area_share"] = 1.0
    df["artificial_share"] = rng.uniform(0, 1, n)
    df["green_m2"] = df["green_share"] * df["area_m2"]
    gdf = gpd.GeoDataFrame(df, geometry=geoms, crs="EPSG:4326")
    info = {
        "cells": n,
        "cells_analysed": int(analysed.sum()),
        "class_edges": edges,
        "sensitivity": summary,
    }
    return gdf, info


def _zones(rng: np.random.Generator):
    # Zone 3 is not analysed; zones need ≥ 4 analysed for quartiles, so there are 6 zones.
    n = 6
    analysed = np.array([True, True, False, True, True, True])
    df, edges, summary = _score_frame(n, analysed, rng, SENS["top_n_zones"])
    df.insert(0, "zone_id", pd.array(range(1, n + 1), dtype="Int64"))
    df["name"] = [f"Zona {i}" for i in range(1, n + 1)]
    df["rione"] = [f"RIONE {i}" for i in range(1, n + 1)]
    df["covered"] = analysed
    df["cells_analysed"] = np.where(analysed, 5, 0)
    df["analysed_area_m2"] = np.where(analysed, 312_500.0, np.nan)
    df["green_m2"] = df["green_share"] * df["analysed_area_m2"]
    geoms = [box(16.8 + i * 0.01, 41.1, 16.81 + i * 0.01, 41.11) for i in range(n)]
    gdf = gpd.GeoDataFrame(df, geometry=geoms, crs="EPSG:4326")
    info = {"zones": n, "zones_analysed": int(analysed.sum()), "class_edges": edges}
    info["sensitivity"] = summary
    return gdf, info


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("processed")
    rng = np.random.default_rng(7)
    grids = {}
    for size, (cols, rows) in {250: (6, 5), 500: (3, 3)}.items():
        gdf, grids[str(size)] = _cells(size, cols, rows, rng)
        gdf.to_parquet(d / f"cells_{size}.parquet")
    zones, zone_info = _zones(rng)
    zones.to_parquet(d / "zones.parquet")
    empty = '{"type":"FeatureCollection","features":[]}'
    for name in ("green_areas", "traffic_controllers", "air_stations", "industry"):
        (d / f"layer_{name}.geojson").write_text(empty)
    metadata = {
        "schema_version": 1,
        "city": "test",
        "built_at": "2026-09-29T00:00:00+00:00",
        "indicators": {
            "all": ACTIVE + INACTIVE,
            "active": ACTIVE,
            "dropped": {"industry": "too_few_facilities"},
            "raw_column": RAW,
        },
        "weights": {"configured_pp": {**DEFAULT_PP, "industry": 10}, "effective": EFFECTIVE},
        "classes": {"count": 4, "keys": ["bassa", "media", "medio_alta", "alta"]},
        "grid": {"cell_sizes_m": [250, 500], "default_cell_size_m": 250},
        "grids": grids,
        "zones": zone_info,
        "sensitivity": SENS,
        "disclaimers": ["relative_priority"],
    }
    (d / "metadata.json").write_text(json.dumps(metadata))
    return d


@pytest.fixture(scope="module")
def client(data_dir):
    with TestClient(create_app(data_dir)) as c:
        yield c


# ---------------------------------------------------------------------------- weights


def test_parse_weights_defaults_and_rescaling():
    assert parse_weights(None, ACTIVE, INACTIVE) is None
    assert parse_weights("  ", ACTIVE, INACTIVE) is None
    w = parse_weights(CUSTOM, ACTIVE, INACTIVE)
    assert list(w) == ACTIVE
    assert w == pytest.approx({"pollution": 0.1, "green_deficit": 0.5, "traffic": 0.25,
                               "population": 0.15})  # fmt: skip
    # UI rounding (sum 99.99) is accepted and rescaled to exactly 1
    w = parse_weights("pollution:22.22,green_deficit:33.33,traffic:22.22,population:22.22",
                      ACTIVE, INACTIVE)  # fmt: skip
    assert sum(w.values()) == pytest.approx(1)
    # inactive indicator with weight 0 is accepted and dropped
    assert "industry" not in parse_weights(CUSTOM + ",industry:0", ACTIVE, INACTIVE)


@pytest.mark.parametrize(
    "raw, message",
    [
        (CUSTOM + ",industry:5", "not active"),
        ("pollution:10,green_deficit:50,traffic:40", "Missing"),
        (CUSTOM + ",noise:0", "Unknown"),
        ("pollution:10,green_deficit:50,traffic:25,population:14", "sum to 100"),
        ("pollution:-10,green_deficit:70,traffic:25,population:15", "between 0 and 100"),
        ("pollution:nan,green_deficit:50,traffic:25,population:25", "between 0 and 100"),
        ("pollution:abc,green_deficit:50,traffic:25,population:25", "not a number"),
        ("pollution=10,green_deficit:90", "Malformed"),
        ("pollution:10,pollution:10,green_deficit:80", "Duplicate"),
    ],
)
def test_parse_weights_rejects(raw, message):
    with pytest.raises(WeightsError, match=message):
        parse_weights(raw, ACTIVE, INACTIVE)


# ---------------------------------------------------------------------------- scenarios


def test_recomputing_the_default_weights_reproduces_the_artefacts(data_dir):
    store = Store(data_dir)
    key = tuple(EFFECTIVE[k] for k in ACTIVE)
    for name in store.levels:
        default = store._compute_scenario(name, None)
        recomputed = store._compute_scenario(name, key)
        pd.testing.assert_frame_equal(default.items, recomputed.items, check_dtype=False)
        assert default.summary == recomputed.summary


def test_custom_scenario_matches_the_formula(data_dir):
    store = Store(data_dir)
    level = store.level("cell", 250)
    w = parse_weights(CUSTOM, ACTIVE, INACTIVE)
    sc = store.scenario(level, w)
    assert not sc.is_default and sc.sensitivity_applicable
    f = level.frame[level.frame["analysed"]]
    expected = compute_ipf(score_matrix(f, ACTIVE), np.array(list(w.values())))
    np.testing.assert_allclose(sc.items.loc[f.index, "ipf"], expected)
    np.testing.assert_array_equal(sc.items.loc[f.index, "rank"], ranks_desc(expected))
    assert sc.items.loc[~level.frame["analysed"], "ipf"].isna().all()
    assert (sc.items.loc[~level.frame["analysed"], "ipf_class"] == 0).all()
    assert store.scenario(level, w) is sc  # cached


# ---------------------------------------------------------------------------- endpoints


def test_health_and_metadata(client):
    assert client.get("/api/health").json() == {
        "status": "ok",
        "built_at": "2026-09-29T00:00:00+00:00",
    }
    meta = client.get("/api/metadata").json()
    assert meta["indicators"]["active"] == ACTIVE
    assert meta["layers"] == ["green", "traffic", "air", "industry"]


def test_cells_geojson(client):
    r = client.get("/api/cells")
    assert r.headers["content-type"] == "application/geo+json"
    fc = _no_nan(r.text)
    assert len(fc["features"]) == 30
    props = fc["features"][0]["properties"]
    assert set(props) == {"cell_id", "zone_id", "analysed", "ipf", "ipf_class", "rank", "robust"}
    not_analysed = [f["properties"] for f in fc["features"] if not f["properties"]["analysed"]]
    assert not_analysed and all(p["ipf"] is None and p["ipf_class"] == 0 for p in not_analysed)
    assert len(_no_nan(client.get("/api/cells?grid=500").text)["features"]) == 9
    assert client.get("/api/cells?grid=300").status_code == 404


def test_custom_weights_change_the_map(client):
    default = _no_nan(client.get("/api/cells").text)["features"]
    custom = _no_nan(client.get(f"/api/cells?weights={CUSTOM}").text)["features"]
    assert [f["properties"]["ipf"] for f in default] != [f["properties"]["ipf"] for f in custom]
    assert client.get(f"/api/cells?weights={CUSTOM},industry:5").status_code == 400


def test_zones_geojson(client):
    fc = _no_nan(client.get("/api/zones").text)
    assert [f["properties"]["zone_id"] for f in fc["features"]] == [1, 2, 3, 4, 5, 6]
    assert fc["features"][0]["properties"]["name"] == "Zona 1"


@pytest.mark.parametrize("weights", [None, CUSTOM])
def test_zone_detail_is_consistent(client, weights):
    url = "/api/zones/1" + (f"?weights={weights}" if weights else "")
    d = _no_nan(client.get(url).text)
    assert d["analysed"] and d["is_default"] is (weights is None)
    assert sum(i["contribution"] for i in d["indicators"]) == pytest.approx(d["ipf"])
    assert sum(d["weights"].values()) == pytest.approx(1)
    contribs = [t["contribution"] for t in d["top_drivers"]]
    assert len(contribs) == 3 and contribs == sorted(contribs, reverse=True)
    assert d["class_key"] in ("bassa", "media", "medio_alta", "alta")
    assert d["sensitivity"]["applicable"] and d["sensitivity"]["top_n"] == 3
    assert d["zone"] == {"zone_id": 1, "name": "Zona 1"}


def test_details_of_not_analysed_items(client):
    d = _no_nan(client.get("/api/zones/3").text)
    assert not d["analysed"] and d["ipf"] is None and d["ipf_class"] == 0
    assert d["class_key"] is None and d["top_drivers"] == []
    cell = _no_nan(client.get("/api/cells/250-2-0").text)  # zone 3
    assert not cell["analysed"] and cell["zone"]["zone_id"] == 3 and cell["grid"] == 250
    assert all(i["score"] is None for i in cell["indicators"])


def test_cell_detail_and_not_found(client):
    d = _no_nan(client.get("/api/cells/500-0-0").text)
    assert d["grid"] == 500 and d["level"] == "cell" and d["ranked_items"] == 6
    for url in ("/api/cells/250-99-99", "/api/cells/abc", "/api/cells/300-0-0", "/api/zones/99"):
        assert client.get(url).status_code == 404, url


def test_ranking(client):
    r = client.get("/api/ranking?level=cell&limit=5").json()
    assert r["total"] == 20 and len(r["items"]) == 5
    assert [i["rank"] for i in r["items"]] == [1, 2, 3, 4, 5]
    ipfs = [i["ipf"] for i in r["items"]]
    assert ipfs == sorted(ipfs, reverse=True)
    assert r["items"][0]["name"].startswith("Zona")
    z = client.get(f"/api/ranking?weights={CUSTOM}").json()
    assert z["total"] == 5 and not z["is_default"] and z["items"][0]["name"]


def test_sensitivity_default_uses_the_precomputed_summary(client):
    s = client.get("/api/sensitivity").json()
    meta = client.get("/api/metadata").json()
    assert s["applicable"] and s["summary"] == meta["zones"]["sensitivity"]
    assert len(s["items"]) == 5 and s["parameters"]["top_n"] == 3


def test_sensitivity_with_a_zero_weight_keeps_it_fixed(client):
    s = client.get("/api/sensitivity?weights=pollution:0,green_deficit:50,traffic:25,population:25")
    s = s.json()
    assert s["applicable"] and s["weights"]["pollution"] == 0
    assert all(i["robust"] is not None for i in s["items"])


def test_sensitivity_not_applicable_with_a_single_indicator(client):
    s = client.get("/api/sensitivity?weights=pollution:100,green_deficit:0,traffic:0,population:0")
    s = s.json()
    assert not s["applicable"] and s["summary"] is None
    assert all(i["rank"] and i["robust"] is None for i in s["items"])


def test_layers(client):
    assert client.get("/api/layers/air").json() == {"type": "FeatureCollection", "features": []}
    assert client.get("/api/layers/nope").status_code == 404


def test_large_responses_are_gzipped(client):
    r = client.get("/api/cells", headers={"accept-encoding": "gzip"})
    assert r.headers["content-encoding"] == "gzip"


# ---------------------------------------------------------------------------- real artefacts


@pytest.mark.skipif(
    not (DEFAULT_DATA_DIR / "metadata.json").is_file(),
    reason="real artefacts not built (uv run python -m pipeline build)",
)
def test_real_artefacts_smoke():
    with TestClient(create_app(DEFAULT_DATA_DIR)) as c:
        meta = c.get("/api/metadata").json()
        for url in ("/api/cells", "/api/cells?grid=500", "/api/zones"):
            fc = _no_nan(c.get(url).text)
            assert fc["features"], url
        top = c.get("/api/ranking").json()
        assert top["total"] == meta["zones"]["zones_analysed"]
        zone = top["items"][0]["zone_id"]
        assert _no_nan(c.get(f"/api/zones/{zone}?weights={CUSTOM}").text)["analysed"]
        assert c.get("/api/sensitivity?level=cell").json()["applicable"]
