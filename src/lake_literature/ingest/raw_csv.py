"""Load data/ieee/export*.csv (the IEEE Xplore metadata export, 28 columns)
into lit_raw.ieee_csv_rows -- one row per CSV row, values kept as JSON so no
typing/normalization happens yet (that's bronze's job).
"""

from __future__ import annotations

import logging
import math

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from lake_literature.config import IEEE_DIR, relative_path
from lake_literature.db.raw_models import IeeeCsvRow
from lake_literature.ingest.hashing import record_source_file, source_file_status

logger = logging.getLogger(__name__)


def _clean_value(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def _read_export_csv(csv_path) -> pd.DataFrame:
    """Read an IEEE export CSV, tolerating a non-UTF-8 one.

    Xplore exports carry accented author names and affiliations; one saved in a
    legacy encoding used to raise `UnicodeDecodeError` out of the whole raw
    stage. latin-1 decodes any byte sequence, so it is a safe last resort.
    """
    try:
        return pd.read_csv(csv_path, encoding="utf-8")
    except UnicodeDecodeError:
        logger.warning("_read_export_csv: %r is not UTF-8, falling back to latin-1", str(csv_path))
        return pd.read_csv(csv_path, encoding="latin-1")


def _stage_rows(session: Session, df: pd.DataFrame, stored_path: str) -> int:
    """Add one `IeeeCsvRow` per CSV row to the session. Returns how many."""
    staged = 0
    for idx, row in df.iterrows():
        fields = {col: _clean_value(row[col]) for col in df.columns}
        doi = fields.get("DOI")
        doi = doi.strip() if isinstance(doi, str) else None
        session.add(
            IeeeCsvRow(
                row_index=int(idx),
                source_file=stored_path,
                fields=fields,
                doi=doi,
            )
        )
        staged += 1
    return staged


def _load_csv_dir(session: Session, directory) -> dict:
    """Load every export*.csv in `directory`.

    Returns `{"rows": rows written, "failed_files": [...]}`. Each file is
    committed on its own so one unreadable export doesn't discard the others.
    Takes the directory as an argument (like `raw_bib._load_bib_dir`) so it can
    be exercised against a temporary one in tests.
    """
    written = 0
    failed: list[str] = []
    for csv_path in sorted(directory.glob("export*.csv")):
        stored_path = relative_path(csv_path)
        try:
            # Hashing is inside the try on purpose: an unreadable file fails
            # here, before anything is parsed.
            sha, changed = source_file_status(session, csv_path)
            already_loaded = session.scalar(
                select(IeeeCsvRow.id).where(IeeeCsvRow.source_file == stored_path)
            )
            if not changed and already_loaded is not None:
                continue

            df = _read_export_csv(csv_path)
            session.execute(delete(IeeeCsvRow).where(IeeeCsvRow.source_file == stored_path))
            file_rows = _stage_rows(session, df, stored_path)
        except Exception:
            # The read is not the only thing that can fail on a malformed
            # export: pandas happily parses a ragged file by turning the extra
            # columns into an index, and the breakage only surfaces while
            # building the rows -- so the whole per-file ingest is isolated.
            logger.warning("load_ieee_csv: failed to ingest %r", stored_path, exc_info=True)
            session.rollback()
            failed.append(stored_path)
            continue

        # Recorded only now that the file parsed and its rows are staged.
        record_source_file(session, csv_path, source="ieee", kind="csv", sha=sha)
        session.commit()
        written += file_rows

    return {"rows": written, "failed_files": failed}


def load_ieee_csv(session: Session) -> dict:
    """Load every data/ieee/export*.csv file (see `_load_csv_dir`)."""
    return _load_csv_dir(session, IEEE_DIR)
