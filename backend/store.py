"""Artefact loading and IPF scenarios (Phase 2.1, 2.3).

The artefacts in data/processed/ (schema: docs/artefacts.md) are loaded once at startup. A
*scenario* is the set of per-item results (IPF, class, rank, sensitivity) for one level and one
weight vector. The default weights read the precomputed columns; custom weights are recomputed
with the pipeline's own functions (pipeline.model, pipeline.sensitivity) and cached.
"""

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from pipeline.model import compute_ipf, quantile_classes, ranks_desc, score_matrix
from pipeline.sensitivity import one_at_a_time, run_sensitivity, sample_weights

SUM_TOLERANCE_PP = 0.1  # custom weights must sum to 100 ± this
DEFAULT_TOLERANCE = 1e-4  # effective weights this close to the defaults use the artefacts
COORD_DECIMALS = 6  # ≈ 0.1 m, plenty for 250 m cells
FLOAT_DECIMALS = 3  # map properties (the detail endpoints return full precision)
SCENARIO_CACHE_SIZE = 32  # per store; each cells_250 scenario keeps ~1.2 MB of GeoJSON
SENSITIVITY_DTYPES = {
    "rank_p5": "Int64",
    "rank_p95": "Int64",
    "top_n_freq": "float64",
    "class_stability": "float64",
    "robust": "boolean",
}
SENSITIVITY_COLUMNS = tuple(SENSITIVITY_DTYPES)
LAYER_FILES = {
    "green": "layer_green_areas.geojson",
    "traffic": "layer_traffic_controllers.geojson",
    "air": "layer_air_stations.geojson",
    "industry": "layer_industry.geojson",
}


class WeightsError(ValueError):
    """Invalid custom weights (the API answers 400)."""


def parse_weights(
    raw: str | None, active: list[str], inactive: list[str]
) -> dict[str, float] | None:
    """Parse `key:pp,key:pp,...` into effective weights (sum 1), or None for the defaults.

    Every active indicator must be given, each weight in [0, 100], and the sum must be 100
    (± SUM_TOLERANCE_PP). Inactive indicators are only accepted with weight 0 (Q30).
    """
    if raw is None or not raw.strip():
        return None
    pp: dict[str, float] = {}
    for part in raw.split(","):
        key, sep, value = part.partition(":")
        key = key.strip()
        if not sep or not key:
            raise WeightsError(f"Malformed weight '{part}': expected key:value")
        if key in pp:
            raise WeightsError(f"Duplicate weight for '{key}'")
        try:
            pp[key] = float(value)
        except ValueError:
            raise WeightsError(f"Weight for '{key}' is not a number") from None
        if not math.isfinite(pp[key]) or not 0 <= pp[key] <= 100:
            raise WeightsError(f"Weight for '{key}' must be between 0 and 100")
    unknown = set(pp) - set(active) - set(inactive)
    if unknown:
        raise WeightsError(f"Unknown indicator(s): {', '.join(sorted(unknown))}")
    for key in inactive:
        if pp.pop(key, 0) != 0:
            raise WeightsError(f"Indicator '{key}' is not active: its weight must be 0")
    missing = [k for k in active if k not in pp]
    if missing:
        raise WeightsError(f"Missing weight(s): {', '.join(missing)}")
    total = sum(pp.values())
    if abs(total - 100) > SUM_TOLERANCE_PP:
        raise WeightsError(f"Weights must sum to 100 (got {total:g})")
    return {k: pp[k] / total for k in active}


@dataclass
class Scenario:
    """Results of one weight vector at one level. `items` is indexed like the level's frame."""

    weights: dict[str, float]
    is_default: bool
    items: pd.DataFrame  # ipf, ipf_class, rank + SENSITIVITY_COLUMNS (null when not analysed)
    class_edges: list[float]
    top_n: int
    sensitivity_applicable: bool
    summary: dict[str, Any] | None  # city-level stability summary (None when not applicable)
    _geojson: dict[tuple[str, ...], bytes] = field(default_factory=dict, repr=False)


@dataclass
class Level:
    """One spatial level: a grid (`cells_250`, `cells_500`) or the zones."""

    name: str
    frame: gpd.GeoDataFrame  # indexed by the item id (cell_id / zone_id)
    geometry_json: pd.Series  # pre-serialised GeoJSON geometries, same index
    info: dict[str, Any]  # metadata.grids.<size> or metadata.zones
    top_n: int


class Store:
    def __init__(self, data_dir: Path):
        meta_path = data_dir / "metadata.json"
        if not meta_path.is_file():
            raise FileNotFoundError(
                f"No artefacts in {data_dir}: run `uv run python -m pipeline build` first"
            )
        self.data_dir = data_dir
        self.metadata: dict[str, Any] = json.loads(meta_path.read_text(encoding="utf-8"))
        self.active: list[str] = self.metadata["indicators"]["active"]
        self.inactive = [k for k in self.metadata["indicators"]["all"] if k not in self.active]
        self.default_weights: dict[str, float] = self.metadata["weights"]["effective"]
        self.sens_cfg: dict[str, Any] = self.metadata["sensitivity"]
        self.n_classes: int = self.metadata["classes"]["count"]
        self.grid_sizes: list[int] = self.metadata["grid"]["cell_sizes_m"]

        self.levels: dict[str, Level] = {}
        for size in self.grid_sizes:
            frame = gpd.read_parquet(data_dir / f"cells_{size}.parquet").set_index("cell_id")
            n = int(frame["analysed"].sum())
            top_n = math.ceil(self.sens_cfg["top_share_cells"] * n)
            self._add_level(f"cells_{size}", frame, self.metadata["grids"][str(size)], top_n)
        zones = gpd.read_parquet(data_dir / "zones.parquet").set_index("zone_id")
        top_n = min(self.sens_cfg["top_n_zones"], int(zones["analysed"].sum()))
        self._add_level("zones", zones, self.metadata["zones"], top_n)

        self.layers = {k: (data_dir / f).read_bytes() for k, f in LAYER_FILES.items()}
        self._scenario = lru_cache(maxsize=SCENARIO_CACHE_SIZE)(self._compute_scenario)

    def _add_level(self, name: str, frame: gpd.GeoDataFrame, info: dict, top_n: int) -> None:
        required = ["analysed", "ipf", "ipf_class", "rank", *SENSITIVITY_COLUMNS]
        required += [f"score_{k}" for k in self.active]
        missing = [c for c in required if c not in frame.columns]
        if missing:
            raise ValueError(f"{name}: artefact is missing columns {missing}")
        geoms = shapely.transform(
            frame.geometry.to_numpy(), lambda xy: np.round(xy, COORD_DECIMALS)
        )
        geometry_json = pd.Series(shapely.to_geojson(geoms), index=frame.index)
        self.levels[name] = Level(name, frame, geometry_json, info, top_n)

    # ------------------------------------------------------------------ scenarios

    def level(self, level: str, grid: int | None = None) -> Level:
        """`level` is "cell" or "zone"; cells need a grid size."""
        if level == "zone":
            return self.levels["zones"]
        if grid not in self.grid_sizes:
            raise KeyError(f"Unknown grid size {grid}; available: {self.grid_sizes}")
        return self.levels[f"cells_{grid}"]

    def is_default(self, weights: Mapping[str, float] | None) -> bool:
        return weights is None or all(
            abs(weights[k] - self.default_weights[k]) <= DEFAULT_TOLERANCE for k in self.active
        )

    def scenario(self, level: Level, weights: Mapping[str, float] | None) -> Scenario:
        if self.is_default(weights):
            return self._scenario(level.name, None)
        key = tuple(round(weights[k], 10) for k in self.active)
        return self._scenario(level.name, key)

    def _compute_scenario(self, name: str, key: tuple[float, ...] | None) -> Scenario:
        level = self.levels[name]
        frame = level.frame
        analysed = frame["analysed"].to_numpy(dtype=bool)
        if key is None:
            items = frame[["ipf", "ipf_class", "rank", *SENSITIVITY_COLUMNS]].copy()
            return Scenario(
                weights=dict(self.default_weights),
                is_default=True,
                items=items,
                class_edges=level.info["class_edges"],
                top_n=level.top_n,
                sensitivity_applicable=True,
                summary=level.info["sensitivity"],
            )

        weights = dict(zip(self.active, key, strict=True))
        w = np.array(key)
        scores = score_matrix(frame.loc[analysed], self.active)
        ipf = np.full(len(frame), np.nan)
        ipf[analysed] = compute_ipf(scores, w)
        classes, edges = quantile_classes(ipf, self.n_classes)
        rank = pd.array([pd.NA] * len(frame), dtype="Int64")
        rank[analysed] = ranks_desc(ipf[analysed])
        items = pd.DataFrame({"ipf": ipf, "ipf_class": classes, "rank": rank}, index=frame.index)
        # Same dtypes as the artefacts; values stay null when not analysed or not applicable
        for col, dtype in SENSITIVITY_DTYPES.items():
            empty = np.nan if dtype == "float64" else pd.NA
            items[col] = pd.Series(empty, index=frame.index, dtype=dtype)

        cfg = self.sens_cfg
        try:
            runs = sample_weights(w, cfg["spread_pp"], cfg["runs"], cfg["seed"])
        except ValueError:
            runs = None
        summary = None
        if runs is not None:
            table, summary = run_sensitivity(
                scores, w, runs, level.top_n, cfg["robust_threshold"], self.n_classes
            )
            summary["one_at_a_time"] = one_at_a_time(
                scores, w, self.active, cfg["one_at_a_time_delta_pp"], level.top_n
            )
            for col in SENSITIVITY_COLUMNS:
                items.loc[analysed, col] = table[col].to_numpy()
        return Scenario(
            weights=weights,
            is_default=False,
            items=items,
            class_edges=edges,
            top_n=level.top_n,
            sensitivity_applicable=runs is not None,
            summary=summary,
        )

    # ------------------------------------------------------------------ GeoJSON

    def geojson(
        self, level: Level, scenario: Scenario, columns: tuple[str, ...], id_key: str
    ) -> bytes:
        """FeatureCollection with the item id (as `id_key`), the given static columns and the
        scenario results. Floats are rounded to FLOAT_DECIMALS.

        Built by string concatenation over pre-serialised geometries, and cached per scenario.
        """
        cache_key = (id_key, *columns)
        if cache_key in scenario._geojson:
            return scenario._geojson[cache_key]
        static = [c for c in columns if c not in scenario.items.columns]
        props = level.frame[static].join(
            scenario.items[[c for c in columns if c in scenario.items.columns]]
        )[list(columns)]
        records = [
            {id_key: to_json_value(i)}
            | {k: _round(to_json_value(v)) for k, v in zip(columns, row, strict=True)}
            for i, row in zip(props.index, props.itertuples(index=False, name=None), strict=True)
        ]
        features = ",".join(
            f'{{"type":"Feature","geometry":{g},"properties":{json.dumps(p, ensure_ascii=False)}}}'
            for g, p in zip(level.geometry_json, records, strict=True)
        )
        out = f'{{"type":"FeatureCollection","features":[{features}]}}'.encode()
        scenario._geojson[cache_key] = out
        return out


def _round(v: Any) -> Any:
    return round(v, FLOAT_DECIMALS) if isinstance(v, float) else v


def to_json_value(v: Any) -> Any:
    """numpy/pandas scalars → JSON-safe Python values (NaN/NA → None)."""
    if v is None or v is pd.NA:
        return None
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return None if math.isnan(v) else float(v)
    return v
