"""Tests for the ingest idempotency backbone (ingest/hashing.py).

Every raw-stage loader decides whether to reprocess a file from what these two
functions report, so a wrong answer here either duplicates the corpus or
silently skips new data.
"""

from __future__ import annotations

from pathlib import Path

from lake_literature.db.raw_models import SourceFile
from lake_literature.ingest.hashing import record_source_file, sha256_file, source_file_status


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_sha256_file_matches_content_not_name(tmp_path):
    a = _write(tmp_path, "a.txt", "same content")
    b = _write(tmp_path, "b.txt", "same content")
    c = _write(tmp_path, "c.txt", "other content")

    assert sha256_file(a) == sha256_file(b)
    assert sha256_file(a) != sha256_file(c)


def test_source_file_status_reports_new_then_unchanged_then_changed(raw_session, tmp_path):
    path = _write(tmp_path, "export.csv", "one")

    sha, changed = source_file_status(raw_session, path)
    assert changed is True  # never seen before

    record_source_file(raw_session, path, source="ieee", kind="csv", sha=sha)
    raw_session.commit()

    _, changed = source_file_status(raw_session, path)
    assert changed is False

    path.write_text("two", encoding="utf-8")
    _, changed = source_file_status(raw_session, path)
    assert changed is True


def test_source_file_status_writes_nothing(raw_session, tmp_path):
    """The whole point of splitting it out: asking must not mark the file as ingested."""
    path = _write(tmp_path, "export.csv", "one")

    source_file_status(raw_session, path)
    source_file_status(raw_session, path)

    assert raw_session.query(SourceFile).count() == 0


def test_record_source_file_updates_in_place_instead_of_duplicating(raw_session, tmp_path):
    path = _write(tmp_path, "export.csv", "one")
    row, created = record_source_file(raw_session, path, source="ieee", kind="csv")
    raw_session.commit()
    assert created is True
    first_sha = row.sha256

    path.write_text("two", encoding="utf-8")
    row, changed = record_source_file(raw_session, path, source="ieee", kind="csv")
    raw_session.commit()

    assert changed is True
    assert row.sha256 != first_sha
    assert raw_session.query(SourceFile).count() == 1
