import numpy as np
import pytest

from pipeline.sensitivity import (
    dirichlet_concentration,
    one_at_a_time,
    run_sensitivity,
    sample_weights,
)

CENTER = np.array([2, 3, 2, 2]) / 9


def test_sampled_weights_sum_to_one_with_requested_spread():
    w = sample_weights(CENTER, spread_pp=5, runs=20_000, seed=1)
    assert w.shape == (4, 20_000)
    np.testing.assert_allclose(w.sum(axis=0), 1)
    np.testing.assert_allclose(w.mean(axis=1), CENTER, atol=0.002)
    assert w.std(axis=1).mean() == pytest.approx(0.05, abs=0.002)


def test_concentration_formula():
    alpha0 = dirichlet_concentration(CENTER, 5)
    var = CENTER * (1 - CENTER) / (alpha0 + 1)
    assert np.sqrt(var).mean() == pytest.approx(0.05, rel=0.05)


def test_clear_leader_is_robust_and_ranks_are_reported():
    rng = np.random.default_rng(0)
    scores = rng.uniform(0, 50, size=(40, 4))
    scores[0] = 100  # dominates under any weights
    runs = sample_weights(CENTER, 5, 500, seed=2)
    table, summary = run_sensitivity(scores, CENTER, runs, top_n=4, robust_threshold=0.8)
    assert table.loc[0, "rank"] == 1
    assert table.loc[0, "rank_p5"] == table.loc[0, "rank_p95"] == 1
    assert table.loc[0, "top_n_freq"] == 1 and bool(table.loc[0, "robust"])
    assert (table["rank_p5"] <= table["rank"]).all() and (table["rank"] <= table["rank_p95"]).all()
    assert 0 < summary["spearman_mean"] <= 1
    assert summary["top_n_overlap_min"] >= 1


def test_identical_weights_give_perfect_stability():
    scores = np.random.default_rng(3).uniform(0, 100, size=(30, 4))
    runs = np.repeat(CENTER[:, None], 10, axis=1)
    table, summary = run_sensitivity(scores, CENTER, runs, top_n=5, robust_threshold=0.8)
    assert summary["spearman_mean"] == pytest.approx(1)
    assert table["class_stability"].eq(1).all() and table["robust"].all()


def test_one_at_a_time_rescales_other_weights():
    scores = np.random.default_rng(4).uniform(0, 100, size=(20, 4))
    keys = ["a", "b", "c", "d"]
    out = one_at_a_time(scores, CENTER, keys, delta_pp=10, top_n=5)
    assert len(out) == 8
    first = out[0]
    assert first["indicator"] == "a" and first["delta_pp"] == -10
    assert first["weight"] == pytest.approx(CENTER[0] - 0.1, abs=1e-4)
    assert all(0 <= r["top_n_kept"] <= 5 for r in out)


def test_zero_weights_stay_fixed_and_the_others_get_the_requested_spread():
    center = np.array([0.0, 0.5, 0.25, 0.25])
    w = sample_weights(center, spread_pp=5, runs=20_000, seed=1)
    assert (w[0] == 0).all()
    np.testing.assert_allclose(w.sum(axis=0), 1)
    assert w[1:].std(axis=1).mean() == pytest.approx(0.05, abs=0.003)


def test_default_sampling_is_unchanged_by_the_zero_weight_rule():
    rng = np.random.default_rng(3)
    alpha0 = dirichlet_concentration(CENTER, 5)
    np.testing.assert_array_equal(
        sample_weights(CENTER, 5, 50, seed=3), rng.dirichlet(CENTER * alpha0, size=50).T
    )


@pytest.mark.parametrize("center", [[1.0, 0, 0, 0], [0.999, 0.001, 0, 0]])
def test_too_concentrated_weights_cannot_be_perturbed(center):
    with pytest.raises(ValueError, match="too concentrated"):
        sample_weights(np.array(center), 5, 10, seed=0)
