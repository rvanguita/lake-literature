"""Tests for the embedding batch alignment (transform/embeddings.py).

`build_embeddings` zips the model's output positionally against this list, so a
row in the wrong position attaches one chunk's vector to another chunk's text --
a silent, hard-to-notice corruption of every downstream semantic signal.
"""

from __future__ import annotations

from dataclasses import dataclass

from lake_literature.transform.embeddings import _ordered_by_ids


@dataclass
class _Row:
    id: int
    text: str


def test_rows_follow_the_requested_id_order_not_the_query_order():
    # `WHERE id IN (...)` gives no ordering guarantee, so the rows can come
    # back in any order -- here, reversed.
    rows = [_Row(3, "third"), _Row(1, "first"), _Row(2, "second")]

    ordered = _ordered_by_ids(rows, [1, 2, 3])

    assert [r.text for r in ordered] == ["first", "second", "third"]


def test_ids_with_no_matching_row_are_skipped_without_shifting_the_rest():
    rows = [_Row(1, "first"), _Row(3, "third")]

    ordered = _ordered_by_ids(rows, [1, 2, 3])

    # id 2 vanished (deleted between the id query and the row fetch); the
    # remaining pairs must still line up with their own text.
    assert [(r.id, r.text) for r in ordered] == [(1, "first"), (3, "third")]


def test_empty_batch_is_empty():
    assert _ordered_by_ids([], []) == []
    assert _ordered_by_ids([_Row(1, "x")], []) == []
