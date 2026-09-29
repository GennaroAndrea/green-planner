"""`python -m pipeline build`: data/raw/ → data/processed/ (Phase 1).

The artefact schema is documented in docs/artefacts.md.
"""

import json
import math
import time
from datetime import UTC, datetime
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from pipeline import indicators as ind
from pipeline import loaders, satellite
from pipeline.config import DATA_DIR, RAW_DIR
from pipeline.grid import make_grid
from pipeline.model import (
    CLASS_KEYS,
    INDICATORS,
    contributions,
    effective_weights,
    quantile_classes,
    robust_minmax,
    score_matrix,
    tree_estimate,
)
from pipeline.sensitivity import (
    dirichlet_concentration,
    one_at_a_time,
    run_sensitivity,
    sample_weights,
)

PROCESSED_DIR = DATA_DIR / "processed"
SCHEMA_VERSION = 1

# Raw column behind each indicator score
RAW_COLUMN = {
    "pollution": "pollution_ratio",
    "green_deficit": "veg_share",  # satellite vegetation share (Q49)
    "traffic": "traffic_index",
    "population": "density_km2",
}

DISCLAIMERS = [
    "relative_priority",  # classes are quartiles: priority relative to the rest of the city
    "model_estimate",  # tree counts are model estimates
    "arpa_validation",  # ARPA data subject to validation/revision
    "no_causality",  # industrial facilities express proximity, never causality
    "satellite_vegetation",  # green = Sentinel-2 summer vegetation (10 m), public and private
    "population_coverage",  # population data covers ~83% of residents; Torre a Mare excluded
]


class Inputs:
    """All cleaned inputs, loaded once and shared by both grid sizes."""

    def __init__(self, config: dict[str, Any]):
        t = config["traffic"]
        self.boundary = loaders.load_boundary()
        self.zones = loaders.load_zones(config)
        self.green = loaders.load_green_areas()
        ndvi = config["sources"]["sentinel2_ndvi"]
        self.ndvi_path = RAW_DIR / "sentinel2_ndvi" / ndvi["filename"]
        self.ndvi_period = ndvi["datetime"]
        self.artificial = loaders.load_artificial_surfaces(tuple(self.boundary.total_bounds))
        pop = loaders.load_population()
        self.people, self.population_stats = loaders.place_population(
            pop, loaders.load_civics(), self.zones
        )
        self.controllers_all = loaders.load_traffic_controllers()
        flows = loaders.load_traffic_flows(
            t["exclude_months"], t["zero_is_missing"], t.get("max_detector_daily_vehicles")
        )
        self.traffic_months = sorted(flows["month"].unique().tolist())
        self.controllers = loaders.controller_daily_means(
            flows, self.controllers_all, t["outlier_iqr_factor"]
        )
        self.stations = loaders.load_air_stations(config)
        self.industry, self.industry_info = loaders.load_industry(config, self.boundary)


def active_indicators(inputs: Inputs) -> list[str]:
    return [k for k in INDICATORS if k != "industry" or inputs.industry_info["active"]]


# ---------------------------------------------------------------------------
# Cells
# ---------------------------------------------------------------------------


def build_cells(
    config: dict[str, Any], inputs: Inputs, size: int, active: list[str]
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    mask_cfg = config["urban_mask"]
    grid = make_grid(inputs.boundary, size, mask_cfg["min_cell_area_share"])
    grid[["zone_id", "zone_covered"]] = ind.assign_zones(grid, inputs.zones)

    # Public green mapped by the Comune: descriptive only since Q49
    grid["green_m2"] = ind.covered_area(grid, inputs.green)
    grid["green_share"] = grid["green_m2"] / grid["area_m2"]
    # Satellite vegetation (Q49): the green indicator and the tree estimate
    veg_m2, veg_valid, _ = satellite.vegetation_area(
        grid, inputs.ndvi_path, config["vegetation"]["ndvi_threshold"]
    )
    grid["veg_m2"] = veg_m2.clip(upper=grid["area_m2"])  # pixel centres vs clipped cells
    grid["veg_share"] = grid["veg_m2"] / grid["area_m2"]
    grid["veg_valid_share"] = veg_valid
    grid["artificial_share"] = ind.covered_area(grid, inputs.artificial) / grid["area_m2"]
    grid[["residents", "vulnerable"]] = ind.sum_points(
        grid, inputs.people, ["residents", "vulnerable"]
    )
    grid["density_km2"] = grid["residents"] / (grid["area_m2"] / 1e6)
    # Non-residential cells (Q50): their trees are reported apart from the zone totals
    # (on the rounded count shown in the UI: residents spread by quartiere can be fractional)
    grid["residential"] = grid["residents"].round(0) > 0
    grid["traffic_index"] = ind.gaussian_kernel_sum(
        grid,
        inputs.controllers,
        "vehicles_day",
        config["traffic"]["kernel_sigma_m"],
        config["traffic"]["kernel_min_weight"],
    )
    grid["pollution_ratio"] = ind.idw(
        grid, inputs.stations, "pollution_ratio", config["air"]["idw_power"]
    )
    if "industry" in active:
        raise NotImplementedError("Industry pressure is active but its spatial method is not set")

    covered = grid["zone_covered"].astype(bool)
    urban = (grid["density_km2"] >= mask_cfg["min_resident_density_km2"]) | (
        grid["artificial_share"] >= mask_cfg["min_artificial_share"]
    )
    grid["analysed"] = covered & urban
    analysed = grid["analysed"]

    # Normalisation (Q9), over the analysed cells only
    norm = config["normalisation"]
    lo, hi, logs = norm["lower_percentile"], norm["upper_percentile"], norm["log_transform"]
    bounds = {}
    for key in active:
        raw = grid[RAW_COLUMN[key]]
        score, bounds[key] = robust_minmax(raw, analysed, lo, hi, key in logs)
        if key == "green_deficit":
            score = 100 - score  # deficit = 100 − normalised coverage
        grid[f"score_{key}"] = score.where(analysed)

    weights = effective_weights(config["weights"], active)
    w = np.array([weights[k] for k in active])
    grid["ipf"] = np.where(analysed, score_matrix(grid, active) @ w, np.nan)
    grid = pd.concat([grid, contributions(grid, weights)], axis=1)

    classes, edges = quantile_classes(grid["ipf"].to_numpy(), config["classes"]["count"])
    grid["ipf_class"] = classes

    trees_cfg = config["trees"]
    trees = tree_estimate(
        grid["area_m2"],
        grid["veg_m2"],
        trees_cfg["target_green_share"],
        trees_cfg["plantable_fraction"],
        trees_cfg["crown_area_m2"],
    )
    grid[trees.columns] = trees.where(analysed)

    # Sensitivity (§6.7) over analysed cells
    sens_cfg = config["sensitivity"]
    idx = grid.index[analysed]
    top_n = math.ceil(sens_cfg["top_share_cells"] * len(idx))
    runs = sample_weights(w, sens_cfg["spread_pp"], sens_cfg["runs"], sens_cfg["seed"])
    scores = score_matrix(grid.loc[idx], active)
    table, summary = run_sensitivity(
        scores, w, runs, top_n, sens_cfg["robust_threshold"], config["classes"]["count"]
    )
    table.index = idx
    grid = grid.join(table)
    summary["one_at_a_time"] = one_at_a_time(
        scores, w, active, sens_cfg["one_at_a_time_delta_pp"], top_n
    )

    info = {
        "cell_size_m": size,
        "cells": len(grid),
        "cells_analysed": int(analysed.sum()),
        "residents_in_analysed_cells": int(round(grid.loc[analysed, "residents"].sum())),
        "normalisation": bounds,
        "class_edges": edges,
        "sensitivity": summary,
    }
    return grid, info


# ---------------------------------------------------------------------------
# Zones (neighbourhoods)
# ---------------------------------------------------------------------------


def build_zones(
    config: dict[str, Any], inputs: Inputs, cells: gpd.GeoDataFrame, active: list[str]
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    """Aggregate analysed cells to quartieri (FR-09).

    Scores are population-weighted means of the cell scores, so the zone IPF equals the
    population-weighted mean of the cell IPFs and stays linear in the weights.
    """
    c = cells[cells["analysed"]].copy()
    pw = c["residents"]
    agg: dict[str, Any] = {}
    for col in [f"score_{k}" for k in active] + ["pollution_ratio", "traffic_index"]:
        c[f"_w_{col}"] = c[col] * pw
        agg[f"_w_{col}"] = "sum"
    for col in ("residents", "vulnerable", "area_m2", "green_m2", "veg_m2"):
        agg[col] = "sum"
    agg["cell_id"] = "count"
    # Tree totals count residential cells only; non-residential trees are kept apart (Q50)
    res = c["residential"].astype(bool)
    for col in ("trees_new", "green_deficit_m2", "plantable_m2"):
        c[f"_res_{col}"] = c[col].where(res, 0)
        agg[f"_res_{col}"] = "sum"
    c["trees_new_nonres"] = c["trees_new"].where(~res, 0)
    c["cells_residential"] = res.astype(int)
    agg["trees_new_nonres"] = "sum"
    agg["cells_residential"] = "sum"
    g = c.groupby("zone_id").agg(agg)
    g = g.rename(
        columns={f"_res_{col}": col for col in ("trees_new", "green_deficit_m2", "plantable_m2")}
    )
    for col in [f"score_{k}" for k in active] + ["pollution_ratio", "traffic_index"]:
        g[col] = g.pop(f"_w_{col}") / g["residents"]
    g = g.rename(columns={"cell_id": "cells_analysed", "area_m2": "analysed_area_m2"})
    g["green_share"] = g["green_m2"] / g["analysed_area_m2"]
    g["veg_share"] = g["veg_m2"] / g["analysed_area_m2"]
    g["density_km2"] = g["residents"] / (g["analysed_area_m2"] / 1e6)

    zones = inputs.zones.merge(g, left_on="zone_id", right_index=True, how="left")
    zones["analysed"] = zones["covered"] & zones["cells_analysed"].fillna(0).gt(0)
    zones["cells_analysed"] = zones["cells_analysed"].fillna(0).astype(int)
    zones["cells_residential"] = zones["cells_residential"].fillna(0).astype(int)

    weights = effective_weights(config["weights"], active)
    w = np.array([weights[k] for k in active])
    an = zones["analysed"]
    zones["ipf"] = np.where(an, score_matrix(zones, active) @ w, np.nan)
    zones = pd.concat([zones, contributions(zones, weights)], axis=1)
    classes, edges = quantile_classes(zones["ipf"].to_numpy(), config["classes"]["count"])
    zones["ipf_class"] = classes

    sens_cfg = config["sensitivity"]
    idx = zones.index[an]
    top_n = min(sens_cfg["top_n_zones"], len(idx))
    runs = sample_weights(w, sens_cfg["spread_pp"], sens_cfg["runs"], sens_cfg["seed"])
    scores = score_matrix(zones.loc[idx], active)
    table, summary = run_sensitivity(
        scores, w, runs, top_n, sens_cfg["robust_threshold"], config["classes"]["count"]
    )
    table.index = idx
    zones = zones.join(table)
    summary["one_at_a_time"] = one_at_a_time(
        scores, w, active, sens_cfg["one_at_a_time_delta_pp"], top_n
    )
    info = {
        "zones": len(zones),
        "zones_analysed": int(an.sum()),
        "aggregated_from_cell_size_m": int(config["zones"]["aggregate_from_cell_size_m"]),
        "class_edges": edges,
        "sensitivity": summary,
    }
    return zones, info


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


INT_COLUMNS = ("zone_id", "rank", "rank_p5", "rank_p95", "trees_new", "trees_new_nonres")
ROUND_0_COLUMNS = ("residents", "vulnerable")  # fractional after the rione spreading


def _to_web(gdf: gpd.GeoDataFrame, simplify_m: float = 0.0) -> gpd.GeoDataFrame:
    out = gdf.copy()
    for col in ROUND_0_COLUMNS:
        if col in out:
            out[col] = out[col].round(0)
    for col in INT_COLUMNS:
        if col in out:
            out[col] = out[col].astype("Int64")
    if "robust" in out:
        out["robust"] = out["robust"].astype("boolean")
    if simplify_m:
        out["geometry"] = out.geometry.simplify(simplify_m, preserve_topology=True)
    out = out.to_crs(loaders.WEB_CRS)
    for col in out.columns:
        if out[col].dtype.kind == "f":
            out[col] = out[col].round(6)
    return out


def _write(gdf: gpd.GeoDataFrame, name: str, parquet: bool = True) -> None:
    if parquet:
        gdf.to_parquet(PROCESSED_DIR / f"{name}.parquet", index=False)
    path = PROCESSED_DIR / f"{name}.geojson"
    path.unlink(missing_ok=True)
    gdf.to_file(path, driver="GeoJSON", COORDINATE_PRECISION=6)


def export_layers(inputs: Inputs) -> None:
    green = inputs.green.rename(columns={"id": "green_id", "id_tipo_ar": "type_id"})
    _write(_to_web(green, simplify_m=1.0), "layer_green_areas", parquet=False)

    ctl = inputs.controllers_all.merge(
        inputs.controllers[
            loaders.CONTROLLER_KEY + ["vehicles_day", "detectors_with_data", "suspicious_total"]
        ],
        on=loaders.CONTROLLER_KEY,
        how="left",
    )
    ctl["has_data"] = ctl["vehicles_day"].notna()
    ctl["suspicious_total"] = ctl["suspicious_total"].fillna(False).astype(bool)
    ctl["vehicles_day"] = ctl["vehicles_day"].round(0)
    _write(_to_web(ctl), "layer_traffic_controllers", parquet=False)

    _write(_to_web(inputs.stations), "layer_air_stations", parquet=False)
    _write(_to_web(inputs.industry), "layer_industry", parquet=False)


def _sources_from_manifest() -> dict[str, Any]:
    manifest = json.loads((RAW_DIR / "manifest.json").read_text(encoding="utf-8"))
    out = {}
    for key, rec in manifest["sources"].items():
        dates = [f["downloaded_at"] for f in rec["files"]]
        out[key] = {
            "status": rec["status"],
            "files": len(rec["files"]),
            "downloaded_at": max(dates) if dates else None,
            "urls": sorted({f["url"] for f in rec["files"]}),
        }
    return out


def _manifest_scenes(key: str) -> list[str]:
    """Acquisition dates of the scenes behind a satellite composite (from the manifest)."""
    manifest = json.loads((RAW_DIR / "manifest.json").read_text(encoding="utf-8"))
    files = manifest["sources"].get(key, {}).get("files", [])
    return [d for f in files for d in f.get("dates", [])]


def build(config: dict[str, Any]) -> dict[str, Any]:
    t0 = time.time()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    print("loading inputs")
    inputs = Inputs(config)
    active = active_indicators(inputs)
    print(f"  active indicators: {', '.join(active)}")

    grids = {}
    grid_info = {}
    for size in config["grid"]["cell_sizes_m"]:
        print(f"grid {size} m")
        cells, info = build_cells(config, inputs, size, active)
        grids[size] = cells
        grid_info[str(size)] = info
        _write(_to_web(cells), f"cells_{size}")
        print(f"  {info['cells_analysed']}/{info['cells']} cells analysed")

    print("zones")
    zones, zone_info = build_zones(
        config, inputs, grids[config["zones"]["aggregate_from_cell_size_m"]], active
    )
    _write(_to_web(zones, simplify_m=2.0), "zones")

    print("context layers")
    export_layers(inputs)

    c250 = grids[config["zones"]["aggregate_from_cell_size_m"]]
    a250 = c250[c250["analysed"]]
    vegetation_info = {
        "source": "Copernicus Sentinel-2 L2A (Microsoft Planetary Computer)",
        "period": inputs.ndvi_period,
        "scenes": _manifest_scenes("sentinel2_ndvi"),
        "ndvi_threshold": config["vegetation"]["ndvi_threshold"],
        "valid_pixel_share": round(
            float(np.average(a250["veg_valid_share"], weights=a250["area_m2"])), 4
        ),
        "cells_without_vegetation": int((a250["veg_m2"] == 0).sum()),
        "nonresidential_cells": int((~a250["residential"].astype(bool)).sum()),
    }

    w = config["sensitivity"]
    center = np.array(list(effective_weights(config["weights"], active).values()))
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "city": config["city"],
        "built_at": datetime.now(UTC).isoformat(),
        "indicators": {
            "all": list(INDICATORS),
            "active": active,
            "dropped": {} if "industry" in active else {"industry": "too_few_facilities"},
            "raw_column": RAW_COLUMN,
        },
        "weights": {
            "configured_pp": config["weights"],
            "effective": effective_weights(config["weights"], active),
        },
        "classes": {
            "count": config["classes"]["count"],
            "keys": list(CLASS_KEYS),
            "method": config["classes"]["method"],
        },  # fmt: skip
        "trees": config["trees"],
        "vegetation": config["vegetation"],
        "urban_mask": config["urban_mask"],
        "normalisation": config["normalisation"],
        "grid": {
            "cell_sizes_m": config["grid"]["cell_sizes_m"],
            "default_cell_size_m": config["grid"]["default_cell_size_m"],
        },  # fmt: skip
        "grids": grid_info,
        "zones": zone_info,
        "sensitivity": {
            **{
                k: w[k]
                for k in (
                    "runs",
                    "spread_pp",
                    "top_n_zones",
                    "top_share_cells",
                    "robust_threshold",
                    "one_at_a_time_delta_pp",
                    "seed",
                )
            },
            "dirichlet_alpha0": round(dirichlet_concentration(center, w["spread_pp"]), 2),
        },  # fmt: skip
        "inputs": {
            "population": inputs.population_stats,
            "traffic": {
                "months_used": inputs.traffic_months,
                "months_excluded": config["traffic"]["exclude_months"],
                "controllers_positioned": len(inputs.controllers_all),
                "controllers_with_data": len(inputs.controllers),
                "controllers_suspicious": int(inputs.controllers["suspicious_total"].sum()),
                "kernel_sigma_m": config["traffic"]["kernel_sigma_m"],
                "kernel_min_weight": config["traffic"]["kernel_min_weight"],
                "max_detector_daily_vehicles": config["traffic"].get("max_detector_daily_vehicles"),
            },
            "air": {
                "reference_year": 2025,
                "stations": len(inputs.stations),
                "pollutants": config["air"]["pollutants"],
                "limit_values_ugm3": config["air"]["limit_values_ugm3"],
                "idw_power": config["air"]["idw_power"],
            },
            "industry": inputs.industry_info,
            "vegetation": vegetation_info,
        },
        "sources": _sources_from_manifest(),
        "disclaimers": DISCLAIMERS,
    }
    (PROCESSED_DIR / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"done in {time.time() - t0:.1f} s → {PROCESSED_DIR}")
    return metadata
