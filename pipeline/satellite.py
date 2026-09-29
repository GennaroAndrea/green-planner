"""Satellite vegetation (Q49): Sentinel-2 L2A NDVI composite and vegetation area per cell.

`pipeline download` builds one median NDVI composite of the cloud-free scenes of a season,
cropped to the city, and caches it as a GeoTIFF in data/raw/<source>/ (with the list of scenes in
the manifest). `pipeline build` then counts, for every grid cell, the 10 m pixels whose NDVI is at
least the configured threshold. Scenes come from Microsoft Planetary Computer (no account needed:
an anonymous SAS token signs the asset URLs).
"""

import hashlib
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import httpx
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.windows import from_bounds

NDVI_SCALE = 10_000  # NDVI stored as int16 × 10,000
NODATA = -32768
# Scene classification (SCL) classes that are not a valid land observation:
# no data, saturated/defective, cloud shadow, water, cloud (medium/high probability), cirrus
SCL_INVALID = (0, 1, 3, 6, 8, 9, 10)


def search_scenes(client: httpx.Client, spec: dict[str, Any]) -> list[dict[str, Any]]:
    """STAC items of the configured tile and period below the cloud cover limit, one per date
    (the least cloudy), oldest first."""
    body = {
        "collections": [spec["collection"]],
        "bbox": spec["bbox"],
        "datetime": spec["datetime"],
        "query": {
            "eo:cloud_cover": {"lt": spec["max_cloud_cover"]},
            "s2:mgrs_tile": {"eq": spec["mgrs_tile"]},
        },
        "limit": 200,
    }
    resp = client.post(f"{spec['stac_api']}/search", json=body)
    resp.raise_for_status()
    by_date: dict[str, dict[str, Any]] = {}
    for item in resp.json()["features"]:
        day = item["properties"]["datetime"][:10]
        best = by_date.get(day)
        if (
            best is None
            or item["properties"]["eo:cloud_cover"] < best["properties"]["eo:cloud_cover"]
        ):
            by_date[day] = item
    return [by_date[d] for d in sorted(by_date)]


def _scene_ndvi(item: dict[str, Any], token: str, bounds: tuple[float, ...]):
    """NDVI of one scene over `bounds` (EPSG:32633), with invalid pixels set to NaN."""

    def open_(asset: str):
        return rasterio.open(f"{item['assets'][asset]['href']}?{token}")

    with open_("B04") as src:
        if src.crs.to_epsg() != 32633:
            raise ValueError(f"{item['id']}: expected EPSG:32633, got {src.crs}")
        win = from_bounds(*bounds, src.transform).round_offsets().round_lengths()
        red = src.read(1, window=win).astype("float32")
        transform = src.window_transform(win)
        win_bounds = rasterio.windows.bounds(win, src.transform)
    with open_("B08") as src:
        nir = src.read(1, window=from_bounds(*win_bounds, src.transform)).astype("float32")
    with open_("SCL") as src:  # 20 m: resampled onto the 10 m pixels
        scl = src.read(
            1,
            window=from_bounds(*win_bounds, src.transform),
            out_shape=red.shape,
            resampling=Resampling.nearest,
        )
    ndvi = (nir - red) / np.maximum(nir + red, 1)
    ndvi[np.isin(scl, SCL_INVALID) | (red == 0) | (nir == 0)] = np.nan
    return ndvi, transform


def download_ndvi_composite(
    client: httpx.Client, spec: dict[str, Any], target: Path
) -> dict[str, Any]:
    """Build the median NDVI composite and write it to `target`. Returns the manifest entry."""
    items = search_scenes(client, spec)
    if not items:
        raise ValueError("No Sentinel-2 scene matches the configured tile, period and cloud cover")
    token = client.get(spec["sas_token_url"]).json()["token"]
    west, south, east, north = spec["bbox"]
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32633", always_xy=True)
    bounds = to_utm.transform_bounds(west, south, east, north)
    stack, transform = [], None
    for item in items:
        print(f"  scene {item['id']}")
        ndvi, transform = _scene_ndvi(item, token, bounds)
        stack.append(ndvi)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # pixels never seen clear stay NaN
        median = np.nanmedian(np.stack(stack), axis=0)
    out = np.where(np.isnan(median), NODATA, np.round(median * NDVI_SCALE)).astype("int16")

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".part.tif")
    profile = {
        "driver": "GTiff",
        "dtype": "int16",
        "count": 1,
        "width": out.shape[1],
        "height": out.shape[0],
        "crs": "EPSG:32633",
        "transform": transform,
        "nodata": NODATA,
        "compress": "deflate",
        "tiled": True,
    }
    with rasterio.open(tmp, "w", **profile) as dst:
        dst.write(out, 1)
        dst.update_tags(
            description=f"Median NDVI x {NDVI_SCALE}, Sentinel-2 L2A, {spec['datetime']}",
            scenes=",".join(i["id"] for i in items),
        )
    tmp.replace(target)
    sha = hashlib.sha256(target.read_bytes()).hexdigest()
    return {
        "url": f"{spec['stac_api']}/search",
        "path": f"{target.parent.name}/{target.name}",
        "bytes": target.stat().st_size,
        "sha256": sha,
        "downloaded_at": datetime.now(UTC).isoformat(),
        "scenes": [i["id"] for i in items],
        "dates": [i["properties"]["datetime"][:10] for i in items],
    }


def vegetation_area(
    grid: gpd.GeoDataFrame, ndvi_path: Path, threshold: float
) -> tuple[pd.Series, pd.Series, dict[str, Any]]:
    """Vegetated area per cell: 10 m pixels with NDVI ≥ threshold whose centre is in the cell.

    Returns (vegetation m², share of the cell's pixels with a valid NDVI, raster info). Pixels
    that were never observed clear (NaN in the composite) count as not vegetated.
    """
    with rasterio.open(ndvi_path) as src:
        if src.crs.to_epsg() != int(str(grid.crs.to_epsg())):
            raise ValueError(f"NDVI raster CRS {src.crs} differs from the grid CRS {grid.crs}")
        raw = src.read(1)
        transform = src.transform
        scenes = (src.tags().get("scenes") or "").split(",")
    pixel_m2 = abs(transform.a * transform.e)
    valid = raw != NODATA
    vegetated = valid & (raw >= round(threshold * NDVI_SCALE))
    ids = rasterize(
        ((geom, i + 1) for i, geom in enumerate(grid.geometry)),
        out_shape=raw.shape,
        transform=transform,
        fill=0,
        dtype="int32",
    )
    n = len(grid) + 1
    total = np.bincount(ids.ravel(), minlength=n)[1:]
    veg = np.bincount(ids[vegetated], minlength=n)[1:]
    ok = np.bincount(ids[valid], minlength=n)[1:]
    veg_m2 = pd.Series(veg * pixel_m2, index=grid.index, dtype=float)
    valid_share = pd.Series(np.where(total > 0, ok / np.maximum(total, 1), 0.0), index=grid.index)
    info = {"pixel_m2": pixel_m2, "scenes": len([s for s in scenes if s])}
    return veg_m2, valid_share, info
