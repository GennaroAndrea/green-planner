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
from pipeline.model import (
    CLASS_KEYS,
    compute_ipf,
    green_deficit_score,
    quantile_classes,
    ranks_desc,
    score_matrix,
    tree_estimate,
)
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


TREES = {"target_green_share": 0.15, "plantable_fraction": 0.25, "crown_area_m2": 30}
GREEN_BOUNDS = {"lower": 0.02, "upper": 0.3, "log": False}


def _model_columns(df: pd.DataFrame, top_n: int) -> tuple[pd.DataFrame, list, dict]:
    """IPF, contributions, classes, ranks and sensitivity from the score columns, as
    `pipeline build` makes them."""
    analysed = df["analysed"].to_numpy(dtype=bool)
    w = np.array([EFFECTIVE[k] for k in ACTIVE])
    df["ipf"] = np.where(analysed, score_matrix(df, ACTIVE) @ w, np.nan)
    for k in ACTIVE:
        df[f"contrib_{k}"] = df[f"score_{k}"] * EFFECTIVE[k]
    df["ipf_class"], edges = quantile_classes(df["ipf"].to_numpy())
    scores = score_matrix(df[analysed], ACTIVE)
    runs = sample_weights(w, SENS["spread_pp"], SENS["runs"], SENS["seed"])
    table, summary = run_sensitivity(scores, w, runs, top_n, SENS["robust_threshold"])
    summary["one_at_a_time"] = one_at_a_time(scores, w, ACTIVE, 10, top_n)
    table.index = df.index[analysed]
    df = df.join(table)
    for col in ("rank", "rank_p5", "rank_p95", "trees_new"):
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
    zone_id = np.array([1 + (i % 6) for i in range(n)])  # zone 3 is not covered
    analysed = zone_id != 3
    df = pd.DataFrame({"cell_id": [f"{size}-{i % cols}-{i // cols}" for i in range(n)]})
    df["zone_id"] = pd.array(zone_id, dtype="Int64")
    df["zone_covered"] = analysed
    df["analysed"] = analysed
    df["area_m2"] = float(size * size)
    df["area_share"] = 1.0
    df["artificial_share"] = rng.uniform(0, 1, n)
    df["green_share"] = np.where(rng.uniform(size=n) < 0.3, 0.0, rng.uniform(0, 0.4, n))
    df["green_m2"] = df["green_share"] * df["area_m2"]
    df["residents"] = rng.integers(1, 3000, n).astype(float)
    df["vulnerable"] = (df["residents"] * 0.3).round()
    df["density_km2"] = df["residents"] / (df["area_m2"] / 1e6)
    for k in ("pollution", "traffic"):
        df[RAW[k]] = rng.uniform(0, 1, n)
    for k in ("pollution", "traffic", "population"):
        df[f"score_{k}"] = np.where(analysed, rng.uniform(0, 100, n), np.nan)
    df["score_green_deficit"] = np.where(
        analysed, green_deficit_score(df["green_share"], GREEN_BOUNDS), np.nan
    )
    trees = tree_estimate(df["area_m2"], df["green_m2"], *TREES.values())
    df[trees.columns] = trees.astype(float)
    df.loc[~analysed, trees.columns] = np.nan
    top_n = math.ceil(SENS["top_share_cells"] * analysed.sum())
    df, edges, summary = _model_columns(df, top_n)
    gdf = gpd.GeoDataFrame(df, geometry=geoms, crs="EPSG:4326")
    info = {
        "cells": n,
        "cells_analysed": int(analysed.sum()),
        "normalisation": {"green_deficit": GREEN_BOUNDS},
        "class_edges": edges,
        "sensitivity": summary,
    }
    return gdf, info


def _zones(cells: pd.DataFrame):
    """Population-weighted aggregation of the analysed 250 m cells, as `build_zones` does."""
    c = cells[cells["analysed"]]
    rows = []
    for zid in range(1, 7):
        z = c[c["zone_id"] == zid]
        row = {"zone_id": zid, "name": f"Zona {zid}", "rione": f"RIONE {zid}"}
        row["covered"] = row["analysed"] = len(z) > 0
        pw = z["residents"]
        for col in [f"score_{k}" for k in ACTIVE] + ["pollution_ratio", "traffic_index"]:
            row[col] = (z[col] * pw).sum() / pw.sum() if len(z) else np.nan
        for col in ("residents", "vulnerable", "green_m2", "green_deficit_m2", "plantable_m2"):
            row[col] = z[col].sum() if len(z) else np.nan
        row["trees_new"] = z["trees_new"].sum() if len(z) else pd.NA
        row["cells_analysed"] = len(z)
        row["analysed_area_m2"] = z["area_m2"].sum() if len(z) else np.nan
        rows.append(row)
    df = pd.DataFrame(rows)
    df["green_share"] = df["green_m2"] / df["analysed_area_m2"]
    df["density_km2"] = df["residents"] / (df["analysed_area_m2"] / 1e6)
    n_analysed = int(df["analysed"].sum())
    df, edges, summary = _model_columns(df, SENS["top_n_zones"])
    geoms = [box(16.8 + i * 0.01, 41.1, 16.81 + i * 0.01, 41.11) for i in range(len(df))]
    gdf = gpd.GeoDataFrame(df, geometry=geoms, crs="EPSG:4326")
    info = {
        "zones": len(df),
        "zones_analysed": n_analysed,
        "aggregated_from_cell_size_m": 250,
        "class_edges": edges,
        "sensitivity": summary,
    }
    return gdf, info


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("processed")
    rng = np.random.default_rng(7)
    grids, frames = {}, {}
    for size, (cols, rows) in {250: (6, 5), 500: (3, 3)}.items():
        frames[size], grids[str(size)] = _cells(size, cols, rows, rng)
        frames[size].to_parquet(d / f"cells_{size}.parquet")
    zones, zone_info = _zones(frames[250])
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
        "trees": TREES,
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
    # any positive total is normalised (Q36), e.g. free sliders summing to 90
    w = parse_weights("pollution:20,green_deficit:30,traffic:20,population:20", ACTIVE, INACTIVE)
    assert w == pytest.approx(EFFECTIVE)
    # inactive indicator with weight 0 is accepted and dropped
    assert "industry" not in parse_weights(CUSTOM + ",industry:0", ACTIVE, INACTIVE)


@pytest.mark.parametrize(
    "raw, message",
    [
        (CUSTOM + ",industry:5", "not active"),
        ("pollution:10,green_deficit:50,traffic:40", "Missing"),
        (CUSTOM + ",noise:0", "Unknown"),
        ("pollution:0,green_deficit:0,traffic:0,population:0", "positive"),
        ("pollution:150,green_deficit:50,traffic:25,population:15", "between 0 and 100"),
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
    scores = {f"score_{k}" for k in ACTIVE}
    assert (
        set(props)
        == {"cell_id", "zone_id", "analysed", "ipf", "ipf_class", "rank", "robust"} | scores
    )
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
    assert d["grid"] == 500 and d["level"] == "cell" and d["ranked_items"] == 7
    for url in ("/api/cells/250-99-99", "/api/cells/abc", "/api/cells/300-0-0", "/api/zones/99"):
        assert client.get(url).status_code == 404, url


def test_ranking(client):
    r = client.get("/api/ranking?level=cell&limit=5").json()
    assert r["total"] == 25 and len(r["items"]) == 5
    assert [i["rank"] for i in r["items"]] == [1, 2, 3, 4, 5]
    ipfs = [i["ipf"] for i in r["items"]]
    assert ipfs == sorted(ipfs, reverse=True)
    assert r["items"][0]["name"].startswith("Zona")
    z = client.get(f"/api/ranking?weights={CUSTOM}").json()
    assert z["total"] == 5 and not z["is_default"] and z["items"][0]["name"]


def test_ranking_contributions_sum_to_the_ipf(client):
    for url in ("/api/ranking?limit=50", f"/api/ranking?level=cell&limit=50&weights={CUSTOM}"):
        for item in client.get(url).json()["items"]:
            assert set(item["contributions"]) == set(ACTIVE)
            assert sum(item["contributions"].values()) == pytest.approx(item["ipf"])


def test_detail_reports_the_green_target(client):
    d = client.get("/api/cells/250-0-0").json()
    assert d["trees"]["target_green_share"] == 0.15
    deficit = d["trees"]["green_deficit_m2"]
    assert d["trees"]["trees_for_target"] == math.ceil(deficit / 30)
    assert d["trees"]["trees_for_target"] >= d["trees"]["trees_new"]


def test_zone_detail_counts_the_cells_below_the_target(client, data_dir):
    cells = gpd.read_parquet(data_dir / "cells_250.parquet")
    cells = cells[cells["analysed"]]
    for zone in (1, 2, 4):
        expected = int((cells.loc[cells["zone_id"] == zone, "green_share"] < 0.15).sum())
        d = client.get(f"/api/zones/{zone}").json()
        assert d["trees"]["cells_below_target"] == expected
        assert expected <= d["stats"]["cells_analysed"]
    assert client.get("/api/zones/3").json()["trees"]["cells_below_target"] is None
    assert client.get("/api/cells/250-0-0").json()["trees"]["cells_below_target"] is None


# ---------------------------------------------------------------------------- simulator


@pytest.mark.parametrize("url", ["/api/cells/250-0-0", "/api/cells/500-0-0", "/api/zones/1"])
def test_simulating_zero_trees_changes_nothing(client, url):
    d = client.get(url).json()
    sim = client.get(f"{url}/simulate?trees=0").json()
    for state in (sim["before"], sim["after"]):
        assert state["ipf"] == pytest.approx(d["ipf"])
        assert state["ipf_class"] == d["ipf_class"] and state["rank"] == d["rank"]
        green = next(i for i in d["indicators"] if i["key"] == "green_deficit")
        assert state["score_green_deficit"] == pytest.approx(green["score"])


def test_simulating_a_cell_follows_the_crown_area_rule(client):
    sim = client.get(f"/api/cells/250-0-0/simulate?trees=100&weights={CUSTOM}").json()
    b, a = sim["before"], sim["after"]
    assert sim["added_green_m2"] == 3000 and a["green_m2"] == pytest.approx(b["green_m2"] + 3000)
    assert a["green_share"] == pytest.approx(a["green_m2"] / 62_500)
    expected = green_deficit_score(a["green_share"], GREEN_BOUNDS)
    assert a["score_green_deficit"] == pytest.approx(float(expected))
    w = sim["weights"]["green_deficit"]
    assert w == pytest.approx(0.5) and not sim["is_default"]
    delta = a["score_green_deficit"] - b["score_green_deficit"]
    assert a["ipf"] == pytest.approx(b["ipf"] + w * delta)
    assert a["ipf"] <= b["ipf"] and a["rank"] >= b["rank"] and a["ipf_class"] <= b["ipf_class"]


def test_planting_the_full_deficit_closes_the_green_gap(client):
    for url in ("/api/cells/250-0-0", "/api/zones/1"):
        target = client.get(url).json()["trees"]["trees_for_target"]
        sim = client.get(f"{url}/simulate?trees={target}").json()
        assert sim["trees_for_target"] == target
        assert sim["after"]["green_share"] >= 0.15 - 1e-9
        assert sim["after"]["score_green_deficit"] <= sim["before"]["score_green_deficit"]


def _zone_expected_score(cells: pd.DataFrame, trees: int, spread_by: str) -> float:
    added = trees * 30 * cells[spread_by] / cells[spread_by].sum()
    scores = green_deficit_score((cells["green_m2"] + added) / cells["area_m2"], GREEN_BOUNDS)
    return float((scores * cells["residents"]).sum() / cells["residents"].sum())


def test_simulating_a_zone_spreads_trees_by_deficit(client, data_dir):
    cells = gpd.read_parquet(data_dir / "cells_250.parquet")
    cells = cells[cells["analysed"]]
    deficits = cells.groupby("zone_id")["green_deficit_m2"].sum()
    zone = int(deficits.idxmax())
    assert deficits[zone] > 0
    expected = _zone_expected_score(cells[cells["zone_id"] == zone], 200, "green_deficit_m2")
    sim = client.get(f"/api/zones/{zone}/simulate?trees=200").json()
    assert sim["after"]["score_green_deficit"] == pytest.approx(expected)
    assert sim["level"] == "zone" and sim["after"]["class_key"] in CLASS_KEYS
    # a zone without deficit: trees are spread by cell area instead
    assert (deficits == 0).any()  # the fixture (seed 7) has one
    zone = int(deficits[deficits == 0].index[0])
    expected = _zone_expected_score(cells[cells["zone_id"] == zone], 200, "area_m2")
    sim = client.get(f"/api/zones/{zone}/simulate?trees=200").json()
    assert sim["after"]["score_green_deficit"] == pytest.approx(expected)


def test_simulator_errors(client):
    assert client.get("/api/zones/3/simulate?trees=10").status_code == 400  # not analysed
    assert client.get("/api/zones/99/simulate?trees=10").status_code == 404
    assert client.get("/api/zones/1/simulate?trees=-1").status_code == 422
    assert client.get("/api/zones/1/simulate").status_code == 422
    assert client.get("/api/zones/1/simulate?trees=5&weights=x").status_code == 400


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
