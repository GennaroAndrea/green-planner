"""FastAPI application: serves the API under /api and the built frontend at / (Phase 2).

Run with: uv run uvicorn backend.main:app --reload
The artefacts are read from data/processed/ (override with GREEN_PLANNER_DATA_DIR).

Custom weights (FR-23) are passed for every active indicator, each 0–100, and normalised on their
total (Q36): `?weights=pollution:25,green_deficit:35,traffic:20,population:20`. Without `weights`,
the defaults apply.
"""

import math
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from backend import schemas
from backend.chat import client_from_env as chat_client_from_env
from backend.chat import install as install_chat
from backend.chat_auth import auth_from_env
from backend.chat_auth import install as install_chat_auth
from backend.store import LAYER_FILES, Level, Scenario, Store, WeightsError, parse_weights
from backend.store import to_json_value as jv
from pipeline.model import CLASS_KEYS, top_drivers

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "processed"
DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]  # Vite dev server

# Properties sent with the map layers (NFR-04: full rows only in the detail endpoints), plus
# `score_<key>` of each active indicator for the per-indicator map tabs
CELL_MAP_COLUMNS = ("zone_id", "analysed", "ipf", "ipf_class", "rank", "robust")
ZONE_MAP_COLUMNS = ("name", "analysed", "ipf", "ipf_class", "rank", "robust", "trees_new")
CELL_STATS = ("area_m2", "area_share", "artificial_share", "residents", "vulnerable",
              "density_km2", "residential", "veg_m2", "veg_share", "green_m2",
              "green_share")  # fmt: skip
ZONE_STATS = ("rione", "covered", "cells_analysed", "cells_residential", "analysed_area_m2",
              "residents", "vulnerable", "density_km2", "veg_m2", "veg_share", "green_m2",
              "green_share")  # fmt: skip
GEOJSON = "application/geo+json"
_FROM_ENV = object()  # create_app default: chat access configured from the environment

WeightsParam = Annotated[
    str | None,
    Query(
        description="Custom weights of all active indicators (0–100 each, normalised on their "
        "total), e.g. `pollution:25,green_deficit:35,traffic:20,population:20`. "
        "Omit for the defaults.",
    ),
]
GridParam = Annotated[int | None, Query(description="Cell size in metres (cells only)")]
TreesParam = Annotated[int, Query(ge=0, le=1_000_000, description="New trees to plant")]
YearsParam = Annotated[
    int | None,
    Query(ge=0, le=200, description="Years since planting; crowns grow linearly until maturity"),
]


def create_app(
    data_dir: Path | None = None, chat_auth: Any = _FROM_ENV, chat_client: Any = _FROM_ENV
) -> FastAPI:
    """`chat_auth` (access store, Q54) and `chat_client` (Claude client, Q53) default to the
    environment's configuration; `None` for no chat."""
    data_dir = data_dir or Path(os.environ.get("GREEN_PLANNER_DATA_DIR", DEFAULT_DATA_DIR))
    if chat_auth is _FROM_ENV:
        chat_auth = auth_from_env()
    if chat_client is _FROM_ENV:
        chat_client = chat_client_from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.store = Store(data_dir)
        yield

    app = FastAPI(title="Urban Green Planner API", version="0.2.0", lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(CORSMiddleware, allow_origins=DEV_ORIGINS, allow_methods=["GET"])
    _add_routes(app)
    install_chat_auth(app, chat_auth)
    install_chat(app, chat_client)
    # Mounted last so /api routes take precedence. One origin means a single ngrok tunnel.
    if FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    return app


def get_store(request: Request) -> Store:
    return request.app.state.store


StoreDep = Annotated[Store, Depends(get_store)]


def _resolve(
    store: Store, level: str, grid: int | None, weights: str | None
) -> tuple[Level, Scenario]:
    if level == "cell" and grid is None:
        grid = store.metadata["grid"]["default_cell_size_m"]
    try:
        lvl = store.level(level, grid)
    except KeyError as e:
        raise HTTPException(404, str(e.args[0])) from None
    try:
        parsed = parse_weights(weights, store.active, store.inactive)
    except WeightsError as e:
        raise HTTPException(400, str(e)) from None
    return lvl, store.scenario(lvl, parsed)


def _cell(store: Store, cell_id: str, weights: str | None) -> tuple[Level, Scenario]:
    """Level + scenario of a cell id; the grid size is the `cell_id` prefix."""
    try:
        grid = int(cell_id.split("-")[0])
    except ValueError:
        raise HTTPException(404, f"Unknown cell {cell_id}") from None
    lvl, sc = _resolve(store, "cell", grid, weights)
    if cell_id not in lvl.frame.index:
        raise HTTPException(404, f"Unknown cell {cell_id}")
    return lvl, sc


def _zone(store: Store, zone_id: int, weights: str | None) -> tuple[Level, Scenario]:
    lvl, sc = _resolve(store, "zone", None, weights)
    if zone_id not in lvl.frame.index:
        raise HTTPException(404, f"Unknown zone {zone_id}")
    return lvl, sc


def _map_columns(store: Store, base: tuple[str, ...]) -> tuple[str, ...]:
    return base + tuple(f"score_{k}" for k in store.active)


def _grid_of(level: Level) -> int | None:
    return int(level.name.split("_")[1]) if level.name.startswith("cells_") else None


def _zone_names(store: Store) -> dict[int, str]:
    return store.levels["zones"].frame["name"].to_dict()


def _add_routes(app: FastAPI) -> None:
    @app.get("/api/health", response_model=schemas.Health)
    def health(request: Request) -> dict:
        store = getattr(request.app.state, "store", None)
        return {"status": "ok", "built_at": store.metadata["built_at"] if store else None}

    @app.get("/api/metadata", response_model=schemas.Metadata)
    def metadata(store: StoreDep) -> dict:
        """Sources, dates, default weights, parameters, disclaimer keys (FR-24)."""
        return {**store.metadata, "layers": list(LAYER_FILES)}

    @app.get("/api/cells", response_class=Response, responses={200: {"content": {GEOJSON: {}}}})
    def cells(store: StoreDep, grid: GridParam = None, weights: WeightsParam = None) -> Response:
        """Grid cells as GeoJSON (FR-20). Properties: `cell_id`, CELL_MAP_COLUMNS, `score_<key>`."""
        lvl, sc = _resolve(store, "cell", grid, weights)
        columns = _map_columns(store, CELL_MAP_COLUMNS)
        return Response(store.geojson(lvl, sc, columns, "cell_id"), media_type=GEOJSON)

    @app.get("/api/zones", response_class=Response, responses={200: {"content": {GEOJSON: {}}}})
    def zones(store: StoreDep, weights: WeightsParam = None) -> Response:
        """Quartieri as GeoJSON (FR-21). Properties: `zone_id`, ZONE_MAP_COLUMNS, `score_<key>`."""
        lvl, sc = _resolve(store, "zone", None, weights)
        columns = _map_columns(store, ZONE_MAP_COLUMNS)
        return Response(store.geojson(lvl, sc, columns, "zone_id"), media_type=GEOJSON)

    @app.get("/api/cells/{cell_id}", response_model=schemas.Detail)
    def cell_detail(cell_id: str, store: StoreDep, weights: WeightsParam = None) -> dict:
        """Detail of one cell (FR-22). The grid size is the `cell_id` prefix."""
        lvl, sc = _cell(store, cell_id, weights)
        return _detail(store, lvl, sc, cell_id)

    @app.get("/api/zones/{zone_id}", response_model=schemas.Detail)
    def zone_detail(zone_id: int, store: StoreDep, weights: WeightsParam = None) -> dict:
        """Detail of one quartiere (FR-22)."""
        lvl, sc = _zone(store, zone_id, weights)
        return _detail(store, lvl, sc, zone_id)

    @app.get("/api/cells/{cell_id}/simulate", response_model=schemas.Simulation)
    def cell_simulate(
        cell_id: str,
        store: StoreDep,
        trees: TreesParam,
        weights: WeightsParam = None,
        years: YearsParam = None,
    ) -> dict:
        """Tree simulator for one cell (FR-28, Q37, Q37b)."""
        lvl, _ = _cell(store, cell_id, weights)
        return _simulate(store, lvl, cell_id, trees, weights, years)

    @app.get("/api/zones/{zone_id}/simulate", response_model=schemas.Simulation)
    def zone_simulate(
        zone_id: int,
        store: StoreDep,
        trees: TreesParam,
        weights: WeightsParam = None,
        years: YearsParam = None,
    ) -> dict:
        """Tree simulator for one quartiere (FR-28, Q37, Q37b)."""
        lvl, _ = _zone(store, zone_id, weights)
        return _simulate(store, lvl, zone_id, trees, weights, years)

    @app.get("/api/layers/{name}", response_class=Response)
    def layer(name: str, store: StoreDep) -> Response:
        """Context layers (FR-25): green, traffic, air, industry."""
        if name not in store.layers:
            raise HTTPException(404, f"Unknown layer {name}; available: {list(LAYER_FILES)}")
        return Response(store.layers[name], media_type=GEOJSON)

    @app.get("/api/ranking", response_model=schemas.Ranking)
    def ranking(
        store: StoreDep,
        level: schemas.LevelName = "zone",
        grid: GridParam = None,
        limit: Annotated[int, Query(ge=1, le=10_000)] = 20,
        weights: WeightsParam = None,
    ) -> dict:
        """Analysed items sorted by IPF, with rank interval and robustness (FR-46, FR-51)."""
        lvl, sc = _resolve(store, level, grid, weights)
        f = lvl.frame
        rows = sc.items[f["analysed"].astype(bool)].sort_values("rank")
        names = _zone_names(store)
        items = []
        for idx, r in rows.head(limit).iterrows():
            zone_id = jv(idx if level == "zone" else f.at[idx, "zone_id"])
            items.append(
                {
                    "id": str(idx),
                    "name": names.get(zone_id),
                    "zone_id": zone_id,
                    **{
                        k: jv(r[k])
                        for k in (
                            "ipf",
                            "ipf_class",
                            "rank",
                            "rank_p5",
                            "rank_p95",
                            "top_n_freq",
                            "robust",
                        )  # fmt: skip
                    },
                    "trees_new": jv(f.at[idx, "trees_new"]),
                    "trees_new_nonres": jv(f.at[idx, "trees_new_nonres"])
                    if level == "zone"
                    else None,
                    "residential": jv(f.at[idx, "residential"]) if level == "cell" else None,
                    "residents": jv(f.at[idx, "residents"]),
                    "contributions": {
                        k: float(f.at[idx, f"score_{k}"]) * w for k, w in sc.weights.items()
                    },
                }
            )
        return {
            "weights": sc.weights,
            "is_default": sc.is_default,
            "level": level,
            "grid": _grid_of(lvl),
            "total": len(rows),
            "items": items,
        }

    @app.get("/api/sensitivity", response_model=schemas.Sensitivity)
    def sensitivity(
        store: StoreDep,
        level: schemas.LevelName = "zone",
        grid: GridParam = None,
        weights: WeightsParam = None,
    ) -> dict:
        """Weight sensitivity (FR-27): precomputed for the defaults, computed for custom weights."""
        lvl, sc = _resolve(store, level, grid, weights)
        rows = sc.items[lvl.frame["analysed"].astype(bool)].sort_values("rank")
        cfg = store.sens_cfg
        cols = ("rank", "rank_p5", "rank_p95", "top_n_freq", "class_stability", "robust")
        return {
            "weights": sc.weights,
            "is_default": sc.is_default,
            "level": level,
            "grid": _grid_of(lvl),
            "applicable": sc.sensitivity_applicable,
            "parameters": {
                "runs": cfg["runs"],
                "spread_pp": cfg["spread_pp"],
                "top_n": sc.top_n,
                "robust_threshold": cfg["robust_threshold"],
                "one_at_a_time_delta_pp": cfg["one_at_a_time_delta_pp"],
                "seed": cfg["seed"],
            },
            "summary": sc.summary,
            "items": [
                {"id": str(idx), **{k: jv(r[k]) for k in cols}} for idx, r in rows.iterrows()
            ],
        }


def _simulate(
    store: Store, lvl: Level, item_id: Any, trees: int, weights: str | None, years: int | None
) -> dict:
    parsed = parse_weights(weights, store.active, store.inactive)  # already validated
    try:
        result = store.simulate(lvl, item_id, trees, parsed, years)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    for state in (result["before"], result["after"]):
        state["class_key"] = CLASS_KEYS[state["ipf_class"] - 1]
    return {
        **result,
        "level": "zone" if lvl.name == "zones" else "cell",
        "id": str(item_id),
        "grid": _grid_of(lvl),
    }


def _detail(store: Store, lvl: Level, sc: Scenario, item_id: Any) -> dict:
    row = lvl.frame.loc[item_id]
    trees_cfg = store.metadata["trees"]
    crown = trees_cfg["crown_area_m2"]
    res = sc.items.loc[item_id]
    analysed = bool(row["analysed"])
    raw_columns = store.metadata["indicators"]["raw_column"]
    indicators = []
    for k in store.active:
        score = jv(row[f"score_{k}"])
        w = sc.weights[k]
        indicators.append(
            {
                "key": k,
                "raw_column": raw_columns[k],
                "raw_value": jv(row[raw_columns[k]]),
                "score": score,
                "weight": w,
                "contribution": None if score is None else score * w,
            }
        )
    is_zone = lvl.name == "zones"
    zone_id = jv(item_id if is_zone else row["zone_id"])
    ipf_class = int(res["ipf_class"])
    return {
        "weights": sc.weights,
        "is_default": sc.is_default,
        "level": "zone" if is_zone else "cell",
        "id": str(item_id),
        "grid": _grid_of(lvl),
        "analysed": analysed,
        "ipf": jv(res["ipf"]),
        "ipf_class": ipf_class,
        "class_key": CLASS_KEYS[ipf_class - 1] if ipf_class > 0 else None,
        "rank": jv(res["rank"]),
        "ranked_items": int(lvl.frame["analysed"].sum()),
        "indicators": indicators,
        "top_drivers": top_drivers(row, sc.weights) if analysed else [],
        "trees": {
            **{k: jv(row[k]) for k in ("green_deficit_m2", "plantable_m2", "trees_new")},
            "trees_new_nonres": jv(row["trees_new_nonres"]) if is_zone else None,
            "target_green_share": trees_cfg["target_green_share"],
            "trees_for_target": (math.ceil(row["green_deficit_m2"] / crown) if analysed else None),
            "cells_below_target": (
                int(store.cells_below_target.get(item_id, 0)) if is_zone and analysed else None
            ),
        },
        "sensitivity": {
            "applicable": sc.sensitivity_applicable,
            "top_n": sc.top_n,
            **{
                k: jv(res[k])
                for k in ("rank_p5", "rank_p95", "top_n_freq", "class_stability", "robust")
            },  # fmt: skip
        },
        "stats": {k: jv(row[k]) for k in (ZONE_STATS if is_zone else CELL_STATS)},
        "zone": {"zone_id": zone_id, "name": _zone_names(store).get(zone_id)},
    }


app = create_app()
