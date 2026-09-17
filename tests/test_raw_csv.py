"""Tests for the IEEE CSV loader (ingest/raw_csv.py).

CLAUDE.md calls the CSV the authoritative record list for IEEE, and the loader
also has to survive a file it cannot read without discarding the ones it
already ingested.
"""

from __future__ import annotations

import math
from pathlib import Path

from lake_literature.db.raw_models import IeeeCsvRow, SourceFile
from lake_literature.ingest.raw_csv import _clean_value, _load_csv_dir

_HEADER = "Document Title,Authors,DOI,Publication Year\n"


def _write_export(tmp_path: Path, name: str, rows: str) -> Path:
    path = tmp_path / name
    path.write_text(_HEADER + rows, encoding="utf-8")
    return path


def test_clean_value_maps_pandas_nan_to_none():
    # pandas reads an empty CSV cell as float nan, which must not reach the
    # JSON column as a NaN (invalid JSON, and meaningless as a value).
    assert _clean_value(float("nan")) is None
    assert _clean_value(math.nan) is None
    assert _clean_value(None) is None
    assert _clean_value("Some Title") == "Some Title"
    assert _clean_value(0) == 0  # falsy but real


def test_load_csv_dir_reads_rows_and_extracts_doi(raw_session, tmp_path):
    _write_export(tmp_path, "export1.csv", "A Paper,J. Doe, 10.1109/example.1 ,2024\n")

    stats = _load_csv_dir(raw_session, tmp_path)

    assert stats == {"rows": 1, "failed_files": []}
    row = raw_session.query(IeeeCsvRow).one()
    assert row.doi == "10.1109/example.1"  # stripped
    assert row.fields["Document Title"] == "A Paper"


def test_load_csv_dir_skips_unchanged_and_reprocesses_changed(raw_session, tmp_path):
    path = _write_export(tmp_path, "export1.csv", "A Paper,J. Doe,10.1109/example.1,2024\n")

    assert _load_csv_dir(raw_session, tmp_path)["rows"] == 1
    assert _load_csv_dir(raw_session, tmp_path)["rows"] == 0
    assert raw_session.query(IeeeCsvRow).count() == 1

    path.write_text(_HEADER + "A Paper Revised,J. Doe,10.1109/example.1,2024\n", encoding="utf-8")

    assert _load_csv_dir(raw_session, tmp_path)["rows"] == 1
    row = raw_session.query(IeeeCsvRow).one()  # replaced, not duplicated
    assert row.fields["Document Title"] == "A Paper Revised"


def test_load_csv_dir_falls_back_to_latin1_for_a_non_utf8_export(raw_session, tmp_path):
    path = tmp_path / "export1.csv"
    path.write_bytes(
        (_HEADER + "Estudo de Distribuição,J. Gonçalves,10.1109/x,2024\n").encode("latin-1")
    )

    stats = _load_csv_dir(raw_session, tmp_path)

    assert stats["rows"] == 1
    assert stats["failed_files"] == []
    assert "Gon" in raw_session.query(IeeeCsvRow).one().fields["Authors"]


def test_one_unreadable_file_does_not_discard_the_others(raw_session, tmp_path):
    _write_export(tmp_path, "export1.csv", "Good Paper,J. Doe,10.1109/good,2024\n")
    # Ragged row: more fields than the header has columns -> pandas parser error.
    (tmp_path / "export2.csv").write_text(
        _HEADER + "Bad,Paper,With,Too,Many,Fields,Here\n", encoding="utf-8"
    )

    stats = _load_csv_dir(raw_session, tmp_path)

    assert stats["rows"] == 1
    assert [Path(p).name for p in stats["failed_files"]] == ["export2.csv"]
    assert raw_session.query(IeeeCsvRow).one().doi == "10.1109/good"

    # The failed file must NOT be recorded as ingested, or the next run skips it.
    recorded = {Path(f.path).name for f in raw_session.query(SourceFile).all()}
    assert recorded == {"export1.csv"}
