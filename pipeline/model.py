"""IPF model: normalisation, weights, index, classes, tree estimate (Phase 1.6, §6.3–6.6).

Pure numpy/pandas, no geo dependencies: the backend reuses these functions to recompute the IPF
with custom weights.
"""

from collections.abc import Mapping

import numpy as np
import pandas as pd

# Indicator keys, in display order. Score columns are `score_<key>`.
INDICATORS = ("pollution", "green_deficit", "traffic", "population", "industry")
CLASS_KEYS = ("bassa", "media", "medio_alta", "alta")  # class 1..4 (i18n keys for the UI)


def robust_minmax(
    values: pd.Series, mask: pd.Series, lower_pct: float, upper_pct: float, log: bool = False
) -> tuple[pd.Series, dict[str, float]]:
    """Scale to 0–100 between the given percentiles of the masked values (Q9).

    Values outside the mask get a score too (clipped), so they can be shown for context.
    Returns the scores and the reference bounds (in raw units) for the methodology page.
    """
    x = np.log1p(values.astype(float)) if log else values.astype(float)
    lo, hi = np.nanpercentile(x[mask], [lower_pct, upper_pct])
    if hi <= lo:
        scores = pd.Series(np.where(x > lo, 100.0, 0.0), index=values.index)
    else:
        scores = ((x - lo) / (hi - lo)).clip(0, 1) * 100
    inv = np.expm1 if log else (lambda v: v)
    return scores, {"lower": float(inv(lo)), "upper": float(inv(hi)), "log": log}


def effective_weights(
    weights: Mapping[str, float], active: list[str] | tuple[str, ...]
) -> dict[str, float]:
    """Keep the active indicators and rescale their weights to sum to 1 (proportional
    redistribution of dropped weights, Q10)."""
    w = {k: float(weights[k]) for k in active}
    total = sum(w.values())
    if total <= 0 or any(v < 0 for v in w.values()):
        raise ValueError("Weights must be non-negative with a positive sum")
    return {k: v / total for k, v in w.items()}


def score_matrix(df: pd.DataFrame, active: list[str] | tuple[str, ...]) -> np.ndarray:
    return df[[f"score_{k}" for k in active]].to_numpy(dtype=float)


def compute_ipf(scores: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """IPF = Σ wᵢ · scoreᵢ. `scores` is (n, k), `weights` (k,) or (k, runs)."""
    return scores @ weights


def quantile_classes(values: np.ndarray, n_classes: int = 4) -> tuple[np.ndarray, list[float]]:
    """Classes 1..n from quantile boundaries of `values` (Q11). NaN stays class 0."""
    finite = values[~np.isnan(values)]
    edges = np.quantile(finite, np.linspace(0, 1, n_classes + 1)[1:-1]) if finite.size else []
    classes = np.where(np.isnan(values), 0, np.searchsorted(edges, values, side="right") + 1)
    return classes.astype(int), [float(e) for e in edges]


def ranks_desc(values: np.ndarray) -> np.ndarray:
    """Rank 1 = highest value. Works along axis 0 for 2-D input (one column per run)."""
    order = np.argsort(-values, axis=0, kind="stable")
    ranks = np.empty_like(order)
    if values.ndim == 1:
        ranks[order] = np.arange(1, len(values) + 1)
    else:
        np.put_along_axis(ranks, order, np.arange(1, values.shape[0] + 1)[:, None], axis=0)
    return ranks


def contributions(df: pd.DataFrame, weights: Mapping[str, float]) -> pd.DataFrame:
    """Weighted contribution wᵢ·scoreᵢ of each indicator, in IPF points."""
    return pd.DataFrame(
        {f"contrib_{k}": df[f"score_{k}"] * w for k, w in weights.items()}, index=df.index
    )


def top_drivers(row: Mapping[str, float], weights: Mapping[str, float], n: int = 3) -> list[dict]:
    """Top-n indicators by weighted contribution, for the explanation (§6.6).

    Returns keys + numbers only; the Italian sentences live in the frontend.
    """
    items = [
        {
            "indicator": k,
            "score": float(row[f"score_{k}"]),
            "weight": w,
            "contribution": float(row[f"score_{k}"]) * w,
        }
        for k, w in weights.items()
    ]
    return sorted(items, key=lambda d: d["contribution"], reverse=True)[:n]


def tree_estimate(
    area_m2: pd.Series,
    green_m2: pd.Series,
    target_share: float,
    plantable_fraction: float,
    crown_area_m2: float,
) -> pd.DataFrame:
    """New trees needed to reach the target green share (§6.5). A model estimate."""
    deficit = (target_share * area_m2 - green_m2).clip(lower=0)
    plantable = deficit * plantable_fraction
    trees = np.floor(plantable / crown_area_m2).astype(int)
    return pd.DataFrame(
        {"green_deficit_m2": deficit, "plantable_m2": plantable, "trees_new": trees},
        index=area_m2.index,
    )
