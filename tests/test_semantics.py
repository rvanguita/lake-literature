"""Tests for the pure parts of `transform.semantics`.

Vectors are hand-built so the expected answer is arithmetic, not a property of
the real embedding model -- these tests never load fastembed or touch MySQL.
"""

from __future__ import annotations

import numpy as np

from lake_literature.transform.semantics import (
    discover_themes,
    near_duplicate_pairs,
    project_2d,
    relevance_scores,
)


def _unit(*values: float) -> np.ndarray:
    vector = np.array(values, dtype="float32")
    return vector / np.linalg.norm(vector)


def test_relevance_scores_ranks_by_angle_to_anchor():
    anchor = _unit(1, 0)
    matrix = np.array([_unit(1, 0), _unit(1, 1), _unit(0, 1)])

    scores = relevance_scores(matrix, anchor)

    assert scores[0] > scores[1] > scores[2]
    assert np.isclose(scores[0], 1.0, atol=1e-6)
    assert np.isclose(scores[2], 0.0, atol=1e-6)


def test_relevance_scores_normalizes_unnormalized_input():
    """A caller passing raw (non-unit) vectors must get the same ranking."""
    anchor = np.array([5.0, 0.0], dtype="float32")
    matrix = np.array([[3.0, 0.0], [0.0, 7.0]], dtype="float32")

    scores = relevance_scores(matrix, anchor)

    assert np.isclose(scores[0], 1.0, atol=1e-6)
    assert np.isclose(scores[1], 0.0, atol=1e-6)


def test_relevance_scores_handles_empty_matrix():
    assert relevance_scores(np.zeros((0, 4), dtype="float32"), _unit(1, 0, 0, 0)).shape == (0,)


def test_near_duplicate_pairs_respects_threshold_and_never_self_pairs():
    matrix = np.array([_unit(1, 0), _unit(1, 0.02), _unit(0, 1)])
    dois = ["10.1/a", "10.1/b", "10.1/c"]

    pairs = near_duplicate_pairs(matrix, dois, threshold=0.95)

    assert len(pairs) == 1
    doi_a, doi_b, similarity = pairs[0]
    assert {doi_a, doi_b} == {"10.1/a", "10.1/b"}
    assert doi_a != doi_b
    assert similarity >= 0.95


def test_near_duplicate_pairs_sorted_by_similarity_descending():
    matrix = np.array([_unit(1, 0), _unit(1, 0.3), _unit(1, 0.01)])
    dois = ["10.1/a", "10.1/b", "10.1/c"]

    pairs = near_duplicate_pairs(matrix, dois, threshold=0.5)

    assert [p[2] for p in pairs] == sorted((p[2] for p in pairs), reverse=True)


def test_near_duplicate_pairs_empty_below_two_rows():
    assert near_duplicate_pairs(np.array([_unit(1, 0)]), ["10.1/a"]) == []


def test_discover_themes_separates_two_obvious_groups():
    """Two well-separated blobs must land in different themes, with labels
    drawn from the words that distinguish them."""
    rng = np.random.default_rng(0)
    group_a = np.tile(_unit(1, 0), (6, 1)) + rng.normal(0, 0.01, (6, 2))
    group_b = np.tile(_unit(0, 1), (6, 1)) + rng.normal(0, 0.01, (6, 2))
    matrix = np.vstack([group_a, group_b]).astype("float32")
    texts = ["voltage feeder substation grid"] * 6 + ["logistics warehouse freight truck"] * 6

    labels, theme_labels = discover_themes(matrix, texts, k=2)

    assert len(set(labels[:6])) == 1
    assert len(set(labels[6:])) == 1
    assert labels[0] != labels[6]
    assert set(theme_labels) == set(int(label) for label in labels)
    joined = " ".join(theme_labels.values())
    assert "logistics" in joined or "warehouse" in joined or "freight" in joined


def test_discover_themes_is_deterministic():
    rng = np.random.default_rng(1)
    matrix = rng.normal(0, 1, (20, 5)).astype("float32")
    texts = [f"topic {i % 3} power distribution planning" for i in range(20)]

    first_labels, first_names = discover_themes(matrix, texts, k=3)
    second_labels, second_names = discover_themes(matrix, texts, k=3)

    assert np.array_equal(first_labels, second_labels)
    assert first_names == second_names


def test_discover_themes_caps_k_at_sample_count():
    matrix = np.array([_unit(1, 0), _unit(0, 1)], dtype="float32")

    labels, theme_labels = discover_themes(matrix, ["alpha text", "beta text"], k=8)

    assert len(labels) == 2
    assert len(theme_labels) <= 2


def test_project_2d_returns_one_coordinate_pair_per_row():
    rng = np.random.default_rng(2)
    matrix = rng.normal(0, 1, (12, 6)).astype("float32")

    coords = project_2d(matrix)

    assert coords.shape == (12, 2)
    assert np.isfinite(coords).all()


def test_project_2d_handles_degenerate_input():
    """Fewer than 3 rows can't be projected -- must degrade, not raise."""
    assert project_2d(np.zeros((0, 4), dtype="float32")).shape == (0, 2)
    assert project_2d(np.array([_unit(1, 0)], dtype="float32")).shape == (1, 2)
