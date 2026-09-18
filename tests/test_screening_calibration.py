"""Tests for SLR screening calibration and stratified sampling."""

from __future__ import annotations

import numpy as np
import pandas as pd

from lake_research_map.transform.screening_calibration import (
    evaluate_screening_threshold,
    find_optimal_screening_threshold,
    generate_stratified_screening_sample,
)


def test_generate_stratified_screening_sample_creates_balanced_strata():
    n = 80
    margins = np.linspace(-0.3, 0.3, n)
    df = pd.DataFrame(
        {
            "doi": [f"10.1000/{i}" for i in range(n)],
            "title": [f"Paper {i}" for i in range(n)],
            "year": [2020] * n,
            "venue": ["Test Journal"] * n,
            "relevance_margin": margins,
            "theme_label": ["Theme A"] * n,
        }
    )

    sample = generate_stratified_screening_sample(df, n_samples=20, seed=42)
    assert len(sample) <= 20
    assert "manual_label" in sample.columns
    assert "stratum" in sample.columns
    # Check that multiple strata are populated
    assert sample["stratum"].nunique() >= 3


def test_evaluate_screening_threshold_metrics():
    # 4 in-scope, 4 out-of-scope
    y_true = np.array([True, True, True, True, False, False, False, False])
    # Margins: in-scope have positive, out-of-scope have negative
    margins = np.array([0.2, 0.1, 0.05, -0.01, 0.02, -0.1, -0.2, -0.3])
    # Cutoff at 0.0:
    # y_pred = [True, True, True, False, True, False, False, False]
    # TP: 3, FN: 1, FP: 1, TN: 3
    res = evaluate_screening_threshold(y_true, margins, threshold=0.0)
    assert res["tp"] == 3
    assert res["fn"] == 1
    assert res["fp"] == 1
    assert res["tn"] == 3
    assert np.isclose(res["recall"], 3 / 4)
    assert np.isclose(res["precision"], 3 / 4)
    assert np.isclose(res["specificity"], 3 / 4)
    assert res["f1"] > 0
    assert res["f2"] > 0


def test_find_optimal_screening_threshold_guarantees_min_recall():
    y_true = np.array([True, True, True, True, False, False, False, False])
    margins = np.array([0.5, 0.4, 0.3, 0.1, -0.1, -0.2, -0.3, -0.4])

    opt = find_optimal_screening_threshold(y_true, margins, min_recall=1.0)
    assert opt["metrics_at_optimal"]["recall"] == 1.0
    # The lowest positive is 0.1, so threshold should be <= 0.1 to get 100% recall
    assert opt["optimal_threshold"] <= 0.1
    # Specificity should still be positive (excluding the negative ones)
    assert opt["metrics_at_optimal"]["specificity"] > 0.5
