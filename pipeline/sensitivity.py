"""Weight sensitivity check (Phase 1.7, §6.7). Vectorised numpy, reused by the backend."""

from typing import Any

import numpy as np
import pandas as pd

from pipeline.model import compute_ipf, quantile_classes, ranks_desc


def dirichlet_concentration(center: np.ndarray, spread_pp: float) -> float:
    """Total concentration α₀ giving a mean standard deviation of `spread_pp` percentage points.

    For a Dirichlet with mean w: var(wᵢ) = wᵢ(1 − wᵢ) / (α₀ + 1).
    """
    sd = spread_pp / 100
    return float(np.mean(center * (1 - center)) / sd**2 - 1)


def sample_weights(center: np.ndarray, spread_pp: float, runs: int, seed: int) -> np.ndarray:
    """Weight vectors (k, runs) from a Dirichlet centred on `center`. Each column sums to 1.

    Zero weights stay 0 in every run: only the non-zero weights are perturbed, and the spread
    is calibrated on them (Q31). Raises ValueError when there is nothing to perturb: fewer than
    two non-zero weights, or weights so concentrated that the spread can't be reached.
    """
    nonzero = center > 0
    alpha0 = dirichlet_concentration(center[nonzero], spread_pp)
    if nonzero.sum() < 2 or alpha0 <= 0:
        raise ValueError("Weights too concentrated for the sensitivity check")
    rng = np.random.default_rng(seed)
    out = np.zeros((len(center), runs))
    out[nonzero] = rng.dirichlet(center[nonzero] * alpha0, size=runs).T
    return out


def _classes_per_run(ipf: np.ndarray, n_classes: int) -> np.ndarray:
    qs = np.linspace(0, 1, n_classes + 1)[1:-1]
    edges = np.quantile(ipf, qs, axis=0)  # (n_classes - 1, runs)
    return (ipf[:, None, :] >= edges[None, :, :]).sum(axis=1) + 1


def _spearman_to_reference(ref_rank: np.ndarray, ranks: np.ndarray) -> np.ndarray:
    """Spearman correlation of each rank column with the reference ranks (no ties)."""
    a = ref_rank - ref_rank.mean()
    b = ranks - ranks.mean(axis=0)
    return (a @ b) / np.sqrt((a @ a) * (b * b).sum(axis=0))


def run_sensitivity(
    scores: np.ndarray,
    center: np.ndarray,
    weights: np.ndarray,
    top_n: int,
    robust_threshold: float,
    n_classes: int = 4,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Rank intervals, top-N frequency, class stability and robustness per zone.

    scores: (n, k) normalised scores; center: (k,) reference weights; weights: (k, runs).
    Returned rows follow the order of `scores`.
    """
    ref_ipf = compute_ipf(scores, center)
    ref_rank = ranks_desc(ref_ipf)
    ref_class, _ = quantile_classes(ref_ipf, n_classes)

    ipf = compute_ipf(scores, weights)  # (n, runs)
    ranks = ranks_desc(ipf)
    in_top = ranks <= top_n
    classes = _classes_per_run(ipf, n_classes)

    top_freq = in_top.mean(axis=1)
    class_stab = (classes == ref_class[:, None]).mean(axis=1)
    ref_top = ref_rank <= top_n
    robust = np.where(ref_top, top_freq >= robust_threshold, class_stab >= robust_threshold)

    table = pd.DataFrame(
        {
            "rank": ref_rank,
            "rank_p5": np.percentile(ranks, 5, axis=1, method="nearest").astype(int),
            "rank_p95": np.percentile(ranks, 95, axis=1, method="nearest").astype(int),
            "top_n_freq": top_freq.round(4),
            "class_stability": class_stab.round(4),
            "robust": robust,
        }
    )
    overlap = (in_top & ref_top[:, None]).sum(axis=0)
    spearman = _spearman_to_reference(ref_rank.astype(float), ranks.astype(float))
    summary = {
        "n": int(scores.shape[0]),
        "top_n": int(top_n),
        "spearman_mean": round(float(spearman.mean()), 4),
        "spearman_p5": round(float(np.percentile(spearman, 5)), 4),
        "top_n_overlap_mean": round(float(overlap.mean()), 2),
        "top_n_overlap_min": int(overlap.min()),
        "robust_share": round(float(robust.mean()), 4),
        "robust_share_top_n": round(float(robust[ref_top].mean()), 4),
    }
    return table, summary


def one_at_a_time(
    scores: np.ndarray, center: np.ndarray, keys: list[str], delta_pp: float, top_n: int
) -> list[dict[str, Any]]:
    """Move each weight by ±delta (others rescaled proportionally); report the top-N change."""
    ref_rank = ranks_desc(compute_ipf(scores, center))
    ref_top = ref_rank <= top_n
    out = []
    for i, key in enumerate(keys):
        for sign in (-1, 1):
            new_wi = float(np.clip(center[i] + sign * delta_pp / 100, 0, 1))
            others = np.delete(center, i)
            w = np.insert(others / others.sum() * (1 - new_wi), i, new_wi)
            rank = ranks_desc(compute_ipf(scores, w))
            top = rank <= top_n
            rho = _spearman_to_reference(ref_rank.astype(float), rank[:, None].astype(float))[0]
            out.append(
                {
                    "indicator": key,
                    "delta_pp": sign * delta_pp,
                    "weight": round(new_wi, 4),
                    "top_n_kept": int((top & ref_top).sum()),
                    "top_n": int(top_n),
                    "spearman": round(float(rho), 4),
                }
            )
    return out
