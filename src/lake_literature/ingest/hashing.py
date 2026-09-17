"""Shared helpers for idempotent raw ingestion: hash a file and check/record
it against lit_raw.source_files so re-running a stage doesn't reprocess
unchanged inputs.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from lake_literature.config import relative_path
from lake_literature.db import utcnow
from lake_literature.db.raw_models import SourceFile


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_file_status(session: Session, path: Path) -> tuple[str, bool]:
    """`(sha256, changed)` for `path`, without writing anything.

    Split out of `record_source_file` so a loader can ask "do I need to
    reprocess this?" *before* parsing, and only record the hash once the parse
    succeeded. Recording first meant a file that failed to parse was already
    marked as ingested, so the next run skipped it silently.
    """
    sha = sha256_file(path)
    existing = session.scalar(select(SourceFile).where(SourceFile.path == relative_path(path)))
    return sha, existing is None or existing.sha256 != sha


def record_source_file(
    session: Session, path: Path, source: str, kind: str, sha: str | None = None
) -> tuple[SourceFile, bool]:
    """Insert or update the manifest row for `path`.

    Returns (row, changed) where `changed` is True if the file is new or its
    hash differs from what was recorded before -- callers use this to decide
    whether to reprocess the file's contents. Pass `sha` to reuse a digest
    already computed by `source_file_status` instead of hashing twice.
    """
    sha = sha or sha256_file(path)
    stat = path.stat()
    stored_path = relative_path(path)
    existing = session.scalar(select(SourceFile).where(SourceFile.path == stored_path))
    if existing is None:
        row = SourceFile(
            path=stored_path,
            source=source,
            kind=kind,
            sha256=sha,
            size_bytes=stat.st_size,
            mtime=dt.datetime.fromtimestamp(stat.st_mtime),
        )
        session.add(row)
        session.flush()
        return row, True

    changed = existing.sha256 != sha
    if changed:
        existing.sha256 = sha
        existing.size_bytes = stat.st_size
        existing.mtime = dt.datetime.fromtimestamp(stat.st_mtime)
        existing.ingested_at = utcnow()
        session.flush()
    return existing, changed
