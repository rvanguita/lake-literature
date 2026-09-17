"""Parse every .bib file under data/ieee/ and data/elsevier/ into
lit_raw.bib_entries.

Uses bibtexparser (a real BibTeX parser) rather than naive line/`@`
splitting -- the IEEE files close one entry and open the next on the same
line (`month={Feb},}@ARTICLE{...`), which a naive splitter would merge or
truncate. bibtexparser 2.x handles this correctly out of the box.
"""

from __future__ import annotations

import logging

import bibtexparser
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from lake_literature.config import ELSEVIER_DIR, IEEE_DIR, relative_path
from lake_literature.db.raw_models import BibEntry
from lake_literature.ingest.hashing import record_source_file, source_file_status

logger = logging.getLogger(__name__)


def _stage_entries(session: Session, library, source: str, stored_path: str) -> int:
    """Add one `BibEntry` per parsed entry to the session. Returns how many."""
    staged = 0
    for entry in library.entries:
        fields = {f.key: f.value for f in entry.fields}
        doi = fields.get("doi")
        doi = doi.strip() if isinstance(doi, str) else None
        session.add(
            BibEntry(
                source=source,
                bib_key=entry.key,
                entry_type=entry.entry_type,
                source_file=stored_path,
                fields=fields,
                doi=doi,
            )
        )
        staged += 1
    return staged


def _load_bib_dir(session: Session, source: str, directory) -> tuple[int, list[str], int]:
    """Parse every .bib in `directory`.

    Returns `(rows written, files that failed entirely, entries lost to
    unparseable blocks)`.

    Each file is committed on its own: the corpus is paginated into a dozen-plus
    .bib files per source, and a single malformed one used to abort the whole
    raw stage and roll back every file processed before it.
    """
    written = 0
    blocks_failed = 0
    failed: list[str] = []
    for bib_path in sorted(directory.glob("*.bib")):
        stored_path = relative_path(bib_path)
        try:
            # Hashing is inside the try on purpose: an unreadable file fails
            # here, before anything is parsed, and that used to take the whole
            # stage down with it.
            sha, changed = source_file_status(session, bib_path)
            already_loaded = session.scalar(
                select(BibEntry.id).where(BibEntry.source_file == stored_path)
            )
            if not changed and already_loaded is not None:
                continue

            library = bibtexparser.parse_file(str(bib_path))
            # bibtexparser doesn't raise on a truncated/corrupt entry -- it drops
            # it into `failed_blocks` and carries on, so without this check a
            # damaged export is ingested as "fine, just smaller".
            if library.failed_blocks:
                logger.warning(
                    "_load_bib_dir: %d block(s) in %r could not be parsed and were skipped",
                    len(library.failed_blocks),
                    stored_path,
                )
                blocks_failed += len(library.failed_blocks)
            session.execute(delete(BibEntry).where(BibEntry.source_file == stored_path))
            file_entries = _stage_entries(session, library, source, stored_path)
        except Exception:
            # bibtexparser raises a range of types on malformed input, and a
            # half-parsed entry can break while being staged rather than while
            # being read -- keep the other files' progress and leave this one
            # unrecorded so the next run retries it.
            logger.warning("_load_bib_dir: failed to ingest %r", stored_path, exc_info=True)
            session.rollback()
            failed.append(stored_path)
            continue

        # Recorded only now that the file parsed and its rows are staged.
        record_source_file(session, bib_path, source=source, kind="bib", sha=sha)
        session.commit()
        written += file_entries

    return written, failed, blocks_failed


def load_bib_entries(session: Session) -> dict:
    """Parse both sources' .bib files.

    Returns `{"entries", "failed_files", "failed_blocks"}`. A file that can't be
    ingested at all is reported in `failed_files` rather than aborting the other
    source's load; `failed_blocks` counts individual entries a readable file
    still lost, which bibtexparser reports instead of raising.
    """
    ieee_written, ieee_failed, ieee_blocks = _load_bib_dir(session, "ieee", IEEE_DIR)
    els_written, els_failed, els_blocks = _load_bib_dir(session, "elsevier", ELSEVIER_DIR)
    return {
        "entries": ieee_written + els_written,
        "failed_files": ieee_failed + els_failed,
        "failed_blocks": ieee_blocks + els_blocks,
    }
