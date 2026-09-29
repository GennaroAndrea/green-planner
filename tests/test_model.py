import numpy as np
import pandas as pd
import pytest

from pipeline.model import (
    compute_ipf,
    contributions,
    effective_weights,
    quantile_classes,
    ranks_desc,
    robust_minmax,
    top_drivers,
    tree_estimate,
)


def test_robust_minmax_clips_to_percentiles():
    values = pd.Series(np.arange(101, dtype=float))
    mask = pd.Series(True, index=values.index)
    scores, bounds = robust_minmax(values, mask, 5, 95)
    assert bounds == {"lower": 5.0, "upper": 95.0, "log": False}
    assert scores.iloc[0] == 0 and scores.iloc[5] == 0
    assert scores.iloc[50] == pytest.approx(50)
    assert scores.iloc[95] == 100 and scores.iloc[100] == 100


def test_robust_minmax_uses_only_masked_values_for_bounds():
    values = pd.Series([0.0, 10.0, 20.0, 1000.0])
    mask = pd.Series([True, True, True, False])
    scores, bounds = robust_minmax(values, mask, 0, 100)
    assert bounds["upper"] == 20.0
    assert scores.iloc[3] == 100  # outside the mask, clipped


def test_robust_minmax_log_bounds_in_raw_units():
    values = pd.Series([0.0, 9.0, 99.0, 999.0])
    mask = pd.Series(True, index=values.index)
    scores, bounds = robust_minmax(values, mask, 0, 100, log=True)
    assert bounds["lower"] == pytest.approx(0.0)
    assert bounds["upper"] == pytest.approx(999.0)
    assert scores.iloc[2] == pytest.approx(200 / 3)  # log10(100) / log10(1000)


def test_effective_weights_redistributes_dropped_indicator_proportionally():
    w = effective_weights(
        {"pollution": 20, "green_deficit": 30, "traffic": 20, "population": 20, "industry": 10},
        ["pollution", "green_deficit", "traffic", "population"],
    )
    assert sum(w.values()) == pytest.approx(1)
    assert w["green_deficit"] == pytest.approx(30 / 90)
    assert w["pollution"] == pytest.approx(20 / 90)


def test_effective_weights_rejects_invalid():
    with pytest.raises(ValueError):
        effective_weights({"a": 0, "b": 0}, ["a", "b"])
    with pytest.raises(ValueError):
        effective_weights({"a": -1, "b": 2}, ["a", "b"])


def test_ipf_is_weighted_sum_and_contributions_add_up():
    df = pd.DataFrame({"score_a": [100.0, 0.0], "score_b": [50.0, 50.0]})
    weights = {"a": 0.25, "b": 0.75}
    ipf = compute_ipf(df[["score_a", "score_b"]].to_numpy(), np.array([0.25, 0.75]))
    np.testing.assert_allclose(ipf, [62.5, 37.5])
    np.testing.assert_allclose(contributions(df, weights).sum(axis=1), ipf)


def test_quantile_classes_are_balanced_and_keep_nan_as_zero():
    values = np.array([*range(1, 9), np.nan], dtype=float)
    classes, edges = quantile_classes(values, 4)
    assert len(edges) == 3
    assert list(classes) == [1, 1, 2, 2, 3, 3, 4, 4, 0]


def test_ranks_desc_1d_and_2d():
    assert list(ranks_desc(np.array([3.0, 9.0, 1.0]))) == [2, 1, 3]
    two = ranks_desc(np.array([[3.0, 1.0], [9.0, 2.0], [1.0, 3.0]]))
    assert two[:, 0].tolist() == [2, 1, 3]
    assert two[:, 1].tolist() == [3, 2, 1]


def test_top_drivers_sorted_by_contribution():
    row = {"score_a": 90.0, "score_b": 50.0, "score_c": 10.0}
    drivers = top_drivers(row, {"a": 0.1, "b": 0.6, "c": 0.3}, n=2)
    assert [d["indicator"] for d in drivers] == ["b", "a"]
    assert drivers[0]["contribution"] == pytest.approx(30)


def test_tree_estimate():
    area = pd.Series([62_500.0, 62_500.0])
    green = pd.Series([0.0, 20_000.0])  # second cell already above the 15% target
    out = tree_estimate(area, green, 0.15, 0.25, 30)
    # 9,375 m² deficit × 25% = 2,343.75 m² → 78 trees of 30 m²
    assert out["trees_new"].tolist() == [78, 0]
    assert out["green_deficit_m2"].iloc[1] == 0
