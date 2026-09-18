"""Methodological calibration for Systematic Literature Review (SLR) screening.

Addresses ROADMAP Item 2: replaces circular pseudo-label evaluation with a
reproducible stratified sampling workflow and threshold calibration tools.

In an SLR, recall (sensitivity) takes priority over precision: discarding a
relevant paper is a fatal methodological flaw, whereas inspecting an extra
false positive is merely an inconvenience. This module supports tuning the
decision boundary with configurable minimum recall targets.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def generate_stratified_screening_sample(
    scored_df: pd.DataFrame,
    n_samples: int = 100,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate a stratified sample of articles across the relevance margin range.

    Partitions the corpus into four distinct strata:
    1. Clearly out-of-scope (margin < -0.10)
    2. Borderline negative (-0.10 <= margin < 0.0)
    3. Borderline positive (0.0 <= margin <= 0.10)
    4. Clearly in-scope (margin > 0.10)

    Returns a DataFrame with columns:
    [doi, title, year, venue, relevance_margin, theme_label, manual_label, reviewer_notes]
    """
    valid = scored_df.dropna(subset=["relevance_margin", "doi"]).copy()
    if valid.empty:
        return pd.DataFrame(
            columns=[
                "doi",
                "title",
                "year",
                "venue",
                "relevance_margin",
                "theme_label",
                "stratum",
                "manual_label",
                "reviewer_notes",
            ]
        )

    strata_masks = {
        "out_of_scope_deep": valid["relevance_margin"] < -0.10,
        "borderline_negative": (valid["relevance_margin"] >= -0.10)
        & (valid["relevance_margin"] < 0.0),
        "borderline_positive": (valid["relevance_margin"] >= 0.0)
        & (valid["relevance_margin"] <= 0.10),
        "in_scope_deep": valid["relevance_margin"] > 0.10,
    }

    per_stratum = max(1, n_samples // len(strata_masks))
    rng = np.random.default_rng(seed)

    sampled_rows: list[pd.DataFrame] = []
    for stratum_name, mask in strata_masks.items():
        subset = valid[mask]
        n_take = min(len(subset), per_stratum)
        if n_take > 0:
            indices = rng.choice(subset.index, size=n_take, replace=False)
            stratum_sample = subset.loc[indices].copy()
            stratum_sample["stratum"] = stratum_name
            sampled_rows.append(stratum_sample)

    if not sampled_rows:
        return pd.DataFrame()

    result = pd.concat(sampled_rows, ignore_index=True)
    result["manual_label"] = ""  # Reviewer enters '1' (include) or '0' (exclude)
    result["reviewer_notes"] = ""

    keep_cols = [
        "doi",
        "title",
        "year",
        "venue",
        "relevance_margin",
        "theme_label",
        "stratum",
        "manual_label",
        "reviewer_notes",
    ]
    existing = [c for c in keep_cols if c in result.columns]
    return result[existing].sort_values("relevance_margin").reset_index(drop=True)


def evaluate_screening_threshold(
    y_true: np.ndarray | pd.Series | list[bool | int],
    margins: np.ndarray | pd.Series | list[float],
    threshold: float = 0.0,
) -> dict[str, float | int]:
    """Evaluate decision metrics for a specific screening threshold.

    An article is classified as in-scope if margin >= threshold.

    Returns dict containing TP, FP, TN, FN, precision, recall, specificity, F1, and F2.
    """
    yt = np.asarray(y_true, dtype=bool)
    m = np.asarray(margins, dtype=float)

    if len(yt) != len(m) or len(yt) == 0:
        return {
            "tp": 0,
            "fp": 0,
            "tn": 0,
            "fn": 0,
            "precision": 0.0,
            "recall": 0.0,
            "specificity": 0.0,
            "f1": 0.0,
            "f2": 0.0,
            "threshold": threshold,
        }

    yp = m >= threshold

    tp = int(np.sum(yt & yp))
    fp = int(np.sum((~yt) & yp))
    tn = int(np.sum((~yt) & (~yp)))
    fn = int(np.sum(yt & (~yp)))

    precision = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    recall = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    specificity = float(tn / (tn + fp)) if (tn + fp) > 0 else 0.0

    # F1 score (harmonic mean)
    f1 = float(2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    # F2 score (weights recall 2x as heavily as precision)
    f2 = (
        float(5 * precision * recall / (4 * precision + recall))
        if (4 * precision + recall) > 0
        else 0.0
    )

    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1": f1,
        "f2": f2,
        "threshold": float(threshold),
    }


def find_optimal_screening_threshold(
    y_true: np.ndarray | pd.Series | list[bool | int],
    margins: np.ndarray | pd.Series | list[float],
    min_recall: float = 0.98,
) -> dict:
    """Find the threshold that maximizes specificity while guaranteeing `min_recall`.

    Essential for SLR rigor: guarantees that almost no relevant article is mistakenly
    excluded, while filtering out as many false positives as possible.
    """
    m = np.asarray(margins, dtype=float)
    threshold_candidates = np.sort(np.unique(m))

    best_res = None
    best_thresh = float(threshold_candidates[0]) if len(threshold_candidates) else 0.0

    for thresh in threshold_candidates:
        metrics = evaluate_screening_threshold(y_true, m, threshold=float(thresh))
        if metrics["recall"] >= min_recall:
            if best_res is None or metrics["specificity"] > best_res["specificity"]:
                best_res = metrics
                best_thresh = float(thresh)

    if best_res is None:
        best_res = evaluate_screening_threshold(y_true, m, threshold=0.0)

    return {
        "optimal_threshold": best_thresh,
        "min_recall_target": min_recall,
        "metrics_at_optimal": best_res,
    }
