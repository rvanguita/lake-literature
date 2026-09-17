"""Tests for the PDF inventory loader (ingest/raw_pdfs.py).

The loader only records file identity -- the interesting branch is what happens
when a PDF is replaced by a different file under the same name, which is how a
re-downloaded article arrives.
"""

from __future__ import annotations

from pathlib import Path

from lake_literature.db.raw_models import PdfFile
from lake_literature.ingest.raw_pdfs import _load_pdf_dir


def _write_pdf(tmp_path: Path, name: str, content: str) -> Path:
    # Only identity (name/hash/size) is recorded here, so the bytes don't have
    # to be a real PDF -- text extraction happens in gold, from data/articles/.
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_new_pdf_is_inventoried_with_its_hash_and_size(raw_session, tmp_path):
    _write_pdf(tmp_path, "A Paper Title.pdf", "content")

    assert _load_pdf_dir(raw_session, tmp_path) == 1

    row = raw_session.query(PdfFile).one()
    assert row.filename == "A Paper Title.pdf"
    assert row.size_bytes == len("content")
    assert len(row.sha256) == 64


def test_unchanged_pdf_is_not_counted_again(raw_session, tmp_path):
    _write_pdf(tmp_path, "paper.pdf", "content")

    assert _load_pdf_dir(raw_session, tmp_path) == 1
    assert _load_pdf_dir(raw_session, tmp_path) == 0
    assert raw_session.query(PdfFile).count() == 1


def test_replaced_pdf_updates_the_existing_row(raw_session, tmp_path):
    path = _write_pdf(tmp_path, "paper.pdf", "first version")
    _load_pdf_dir(raw_session, tmp_path)
    first_sha = raw_session.query(PdfFile).one().sha256

    path.write_text("a longer second version", encoding="utf-8")

    assert _load_pdf_dir(raw_session, tmp_path) == 1
    row = raw_session.query(PdfFile).one()  # updated in place, not duplicated
    assert row.sha256 != first_sha
    assert row.size_bytes == len("a longer second version")
