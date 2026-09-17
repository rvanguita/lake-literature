"""Inventory data/articles/*.pdf into lit_raw.pdf_files.

Only records file identity (name, path, hash, size) here -- title matching
against articles happens in silver, and text extraction happens in gold.
"""

from __future__ import annotations

from sqlalchemy import select

from lake_literature.config import ARTICLES_DIR, relative_path
from lake_literature.db.raw_models import PdfFile
from lake_literature.ingest.hashing import record_source_file, sha256_file


def _load_pdf_dir(session, directory) -> int:
    """Inventory every *.pdf in `directory`. Returns rows written or updated.

    Takes the directory as an argument (like `raw_bib._load_bib_dir`) so the
    "file replaced, hash changed" branch below can be exercised in tests.
    """
    written = 0
    for pdf_path in sorted(directory.glob("*.pdf")):
        record_source_file(session, pdf_path, source="articles", kind="pdf")

        existing = session.scalar(select(PdfFile).where(PdfFile.filename == pdf_path.name))
        stat = pdf_path.stat()
        sha = sha256_file(pdf_path)
        if existing is None:
            session.add(
                PdfFile(
                    filename=pdf_path.name,
                    path=relative_path(pdf_path),
                    sha256=sha,
                    size_bytes=stat.st_size,
                )
            )
            written += 1
        elif existing.sha256 != sha:
            existing.path = relative_path(pdf_path)
            existing.sha256 = sha
            existing.size_bytes = stat.st_size
            written += 1

    session.commit()
    return written


def load_pdf_inventory(session) -> int:
    """Inventory data/articles/*.pdf (see `_load_pdf_dir`)."""
    return _load_pdf_dir(session, ARTICLES_DIR)
