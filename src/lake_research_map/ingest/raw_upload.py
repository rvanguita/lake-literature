"""Save a dashboard file upload into `data/{ieee,elsevier}/` and ingest it
into the raw layer, reusing the same loaders/idempotency the CLI pipeline
uses (`raw_csv.load_ieee_csv`, `raw_bib.load_bib_entries`).

IEEE has both a CSV export and `.bib` files; Elsevier only ever has `.bib`
in this project (see CLAUDE.md's source comparison table) -- there is no
"Elsevier CSV" format to invent, so the allowed extensions are per-source.
"""

from __future__ import annotations

from pathlib import Path

from lake_research_map.config import ELSEVIER_DIR, IEEE_DIR
from lake_research_map.db.engines import get_session
from lake_research_map.ingest.raw_bib import load_bib_entries
from lake_research_map.ingest.raw_csv import load_ieee_csv

SOURCE_UPLOAD_SPECS = {
    "ieee": {
        "csv": {"dir": IEEE_DIR, "stem": "export_upload"},
        "bib": {"dir": IEEE_DIR, "stem": "upload"},
    },
    "elsevier": {
        "bib": {"dir": ELSEVIER_DIR, "stem": "upload"},
    },
}


class RawUploadError(ValueError):
    """Raised when an uploaded file's source/extension combination isn't supported."""


def _extension(filename: str) -> str:
    return Path(filename).suffix.lstrip(".").lower()


def _unique_path(directory: Path, stem: str, ext: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / f"{stem}.{ext}"
    n = 1
    while candidate.exists():
        candidate = directory / f"{stem}_{n}.{ext}"
        n += 1
    return candidate


def save_uploaded_file(source: str, filename: str, data: bytes) -> Path:
    """Write an uploaded file into the right `data/` directory for `source`.

    Raises `RawUploadError` if `source`/the file's extension isn't one of the
    combinations that source actually produces. Never overwrites an existing
    corpus file -- picks a fresh, non-colliding name in the same directory
    each loader already globs (`export*.csv`, `*.bib`).
    """
    specs = SOURCE_UPLOAD_SPECS.get(source)
    if specs is None:
        raise RawUploadError(
            f"unknown source {source!r}, expected one of {list(SOURCE_UPLOAD_SPECS)}"
        )

    ext = _extension(filename)
    spec = specs.get(ext)
    if spec is None:
        raise RawUploadError(
            f"{source!r} only accepts {list(specs)} uploads, got {ext or filename!r}"
        )

    path = _unique_path(spec["dir"], spec["stem"], ext)
    path.write_bytes(data)
    return path


def ingest_uploaded_file(path: Path) -> dict:
    """Run the matching raw loader for `path`'s extension.

    Both loaders scan their whole source directory and skip files whose
    content hash hasn't changed (`ingest/hashing.py::record_source_file`), so
    calling them after adding a single new file only (re)processes that file.
    """
    session = get_session("raw")
    try:
        if path.suffix.lower() == ".csv":
            written = load_ieee_csv(session)
            return {"ieee_csv_rows": written}
        written = load_bib_entries(session)
        return {"bib_entries": written}
    finally:
        session.close()
