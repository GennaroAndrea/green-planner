"""Raw per-cell indicators (Phase 1.5). All inputs in the metric compute CRS."""

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist


def covered_area(grid: gpd.GeoDataFrame, polygons: gpd.GeoDataFrame) -> pd.Series:
    """Area (m²) of each cell covered by the union of `polygons` (overlaps counted once)."""
    union = gpd.GeoDataFrame(geometry=[polygons.union_all()], crs=polygons.crs)
    parts = gpd.overlay(grid[["cell_id", "geometry"]], union, how="intersection")
    area = parts.assign(a=parts.area).groupby("cell_id")["a"].sum()
    return grid["cell_id"].map(area).fillna(0.0).set_axis(grid.index)


def sum_points(
    grid: gpd.GeoDataFrame, points: gpd.GeoDataFrame, columns: list[str]
) -> pd.DataFrame:
    """Sum point attributes per cell (points on a shared edge go to one cell only)."""
    joined = points[columns + ["geometry"]].sjoin(
        grid[["cell_id", "geometry"]], how="inner", predicate="within"
    )
    sums = joined.groupby("cell_id")[columns].sum()
    out = grid[["cell_id"]].merge(sums, left_on="cell_id", right_index=True, how="left")
    return out[columns].fillna(0.0).set_axis(grid.index)


def _centroids(grid: gpd.GeoDataFrame) -> np.ndarray:
    c = grid.geometry.centroid
    return np.column_stack([c.x, c.y])


def _coords(points: gpd.GeoDataFrame) -> np.ndarray:
    return np.column_stack([points.geometry.x, points.geometry.y])


def gaussian_kernel_sum(
    grid: gpd.GeoDataFrame,
    points: gpd.GeoDataFrame,
    value: str,
    sigma_m: float,
    min_weight: float = 0.0,
) -> pd.Series:
    """Σ value_i · exp(−d²/2σ²) at each cell centroid (traffic spread, Q8d).

    Weights below `min_weight` are set to 0, so cells far from every point get exactly 0.
    """
    d = cdist(_centroids(grid), _coords(points))
    w = np.exp(-(d**2) / (2 * sigma_m**2))
    w[w < min_weight] = 0.0
    return pd.Series(w @ points[value].to_numpy(dtype=float), index=grid.index)


def idw(grid: gpd.GeoDataFrame, points: gpd.GeoDataFrame, value: str, power: float) -> pd.Series:
    """Inverse-distance-weighted interpolation at each cell centroid (air pollution, Q3)."""
    d = cdist(_centroids(grid), _coords(points))
    d = np.maximum(d, 1.0)  # a centroid on a station takes (almost) the station's value
    w = 1.0 / d**power
    v = points[value].to_numpy(dtype=float)
    return pd.Series((w @ v) / w.sum(axis=1), index=grid.index)


def assign_zones(grid: gpd.GeoDataFrame, zones: gpd.GeoDataFrame) -> pd.DataFrame:
    """Zone of each cell = the zone containing its centroid (nearest zone if on no zone)."""
    cent = gpd.GeoDataFrame(grid[["cell_id"]], geometry=grid.geometry.centroid, crs=grid.crs)
    cols = ["zone_id", "covered", "geometry"]
    joined = cent.sjoin_nearest(zones[cols], how="left").drop_duplicates("cell_id")
    return joined.set_index(grid.index)[["zone_id", "covered"]]
