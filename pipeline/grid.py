"""Regular square grid over the city, clipped to the municipal boundary (Phase 1.3)."""

import math

import geopandas as gpd
import numpy as np
from shapely import box

ORIGIN_STEP_M = 1000  # grid origin snapped to this, so the 250 m and 500 m grids nest


def make_grid(
    boundary: gpd.GeoDataFrame, cell_size: int, min_area_share: float
) -> gpd.GeoDataFrame:
    """Square cells clipped to the boundary. Slivers below `min_area_share` of a cell are dropped.

    `cell_id` is "<size>-<col>-<row>", with col/row counted from the snapped origin, so ids are
    stable across runs.
    """
    minx, miny, maxx, maxy = boundary.total_bounds
    x0 = math.floor(minx / ORIGIN_STEP_M) * ORIGIN_STEP_M
    y0 = math.floor(miny / ORIGIN_STEP_M) * ORIGIN_STEP_M
    cols = np.arange(x0, maxx, cell_size)
    rows = np.arange(y0, maxy, cell_size)
    xx, yy = np.meshgrid(cols, rows)
    xx, yy = xx.ravel(), yy.ravel()
    squares = box(xx, yy, xx + cell_size, yy + cell_size)
    ci = ((xx - x0) // cell_size).astype(int)
    ri = ((yy - y0) // cell_size).astype(int)
    grid = gpd.GeoDataFrame(
        {"cell_id": [f"{cell_size}-{c}-{r}" for c, r in zip(ci, ri, strict=True)]},
        geometry=squares,
        crs=boundary.crs,
    )
    city = boundary.geometry.iloc[0]
    grid = grid[grid.intersects(city)].copy()
    grid["geometry"] = grid.intersection(city)
    grid["area_m2"] = grid.area
    grid["area_share"] = grid["area_m2"] / cell_size**2
    grid = grid[grid["area_share"] >= min_area_share]
    return grid.reset_index(drop=True)
