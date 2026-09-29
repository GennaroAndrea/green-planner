import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely import Point, box

from pipeline.grid import make_grid
from pipeline.indicators import covered_area, gaussian_kernel_sum, idw, sum_points
from pipeline.loaders import normalise_street, place_population, split_civic

CRS = "EPSG:32633"


@pytest.fixture
def boundary():
    return gpd.GeoDataFrame(geometry=[box(1000, 1000, 2000, 1600)], crs=CRS)


def test_grid_is_clipped_and_nested(boundary):
    g250 = make_grid(boundary, 250, min_area_share=0.1)
    g500 = make_grid(boundary, 500, min_area_share=0.1)
    assert g250["area_m2"].sum() == pytest.approx(1000 * 600)
    assert g500["area_m2"].sum() == pytest.approx(1000 * 600)
    assert g250["cell_id"].is_unique
    assert g250["cell_id"].iloc[0].startswith("250-")
    # the top row of 250 m cells is 100 m tall (clipped): 40% of a cell
    assert g250["area_share"].min() == pytest.approx(0.4)


def test_grid_drops_slivers(boundary):
    grid = make_grid(boundary, 250, min_area_share=0.5)
    assert grid["area_share"].min() >= 0.5


def test_covered_area_counts_overlaps_once(boundary):
    grid = make_grid(boundary, 500, min_area_share=0.1)
    green = gpd.GeoDataFrame(geometry=[box(1000, 1000, 1100, 1100)] * 2, crs=CRS)
    area = covered_area(grid, green)
    assert area.sum() == pytest.approx(100 * 100)


def test_sum_points(boundary):
    grid = make_grid(boundary, 500, min_area_share=0.1)
    pts = gpd.GeoDataFrame(
        {"residents": [3.0, 4.0]}, geometry=[Point(1100, 1100), Point(1110, 1110)], crs=CRS
    )
    total = sum_points(grid, pts, ["residents"])["residents"]
    assert total.sum() == 7 and total.max() == 7


def test_kernel_and_idw(boundary):
    grid = make_grid(boundary, 500, min_area_share=0.1)
    pts = gpd.GeoDataFrame({"v": [10.0, 20.0]}, geometry=[Point(1250, 1250), Point(1750, 1250)])
    pts = pts.set_crs(CRS)
    k = gaussian_kernel_sum(grid, pts, "v", sigma_m=300)
    assert k.max() <= 30 and k.min() >= 0
    # with a 1% cutoff (≈ 910 m at σ = 300 m) no point reaches beyond it
    far = gpd.GeoDataFrame({"v": [10.0]}, geometry=[Point(5000, 5000)], crs=CRS)
    assert gaussian_kernel_sum(grid, far, "v", sigma_m=300, min_weight=0.01).eq(0).all()
    assert gaussian_kernel_sum(grid, far, "v", sigma_m=300).gt(0).all()
    values = idw(grid, pts, "v", power=2)
    assert values.between(10, 20).all()
    # the cell centred on the first point takes (almost) its value
    first = grid.index[
        np.isclose(grid.geometry.centroid.x, 1250) & np.isclose(grid.geometry.centroid.y, 1250)
    ][0]
    assert values[first] == pytest.approx(10, abs=0.01)


def test_address_normalisation():
    assert normalise_street("Via Dante  Alighieri") == "VIA DANTE ALIGHIERI"
    assert normalise_street("VIA DELL'AMORE") == "VIA DELL AMORE"
    assert normalise_street("Piazza Libertà") == "PIAZZA LIBERTA"
    assert split_civic("12/A") == ("12", "A")
    assert split_civic("012") == ("12", "")
    assert split_civic("7 BIS") == ("7", "BIS")


def test_place_population_matches_then_spreads():
    zones = gpd.GeoDataFrame({"rione": ["R1"]}, geometry=[box(0, 0, 100, 100)], crs=CRS)
    civics = gpd.GeoDataFrame(
        {"street_key": ["VIA A", "VIA A"], "number": ["1", "2"], "suffix": ["", "B"]},
        geometry=[Point(10, 10), Point(20, 20)],
        crs=CRS,
    )
    pop = pd.DataFrame(
        {
            "street_key": ["VIA A", "VIA A", "VIA Z"],
            "number": ["1", "2", "9"],
            "suffix": ["", "", ""],  # "2" matches "2/B" on the number only
            "rione": ["R1", "R1", "R1"],
            "residents": [5, 3, 10],
            "vulnerable": [1, 1, 2],
        }
    )
    placed, stats = place_population(pop, civics, zones)
    assert placed["residents"].sum() == pytest.approx(18)
    assert stats["residents_matched_exact"] == 5
    assert stats["residents_matched_number"] == 3
    assert stats["residents_spread_by_zone"] == 10
    assert stats["match_rate"] == pytest.approx(8 / 18, abs=1e-4)
