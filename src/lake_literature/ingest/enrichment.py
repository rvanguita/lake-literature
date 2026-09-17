"""Citation/reference-count backfill for records the pipeline can't derive
these numbers for on its own (Elsevier bib entries carry neither field).

Values come from `raw.lit_enrichment`, filled by the `enrich` stage
(`ingest/enrichment_api.py`) from OpenAlex/Crossref. `data/enrichment_cache.json`
-- a hand-maintained `{doi: {citation_count, reference_count}}` file, built
out-of-band for one corpus snapshot -- is still read as a fallback so nothing
that was assembled by hand is lost; the fetched values win where both exist. Without this module, re-running `--stage bronze` wipes
every citation/reference count the cache supplied, because
`_build_elsevier_records` writes `citation_count=None`/`reference_count=None`
literally and `_upsert` overwrites field by field. This module makes that
backfill a first-class, idempotent step of the bronze build instead of a
one-off manual patch.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from lake_literature.config import DATA_DIR
from lake_literature.db.raw_models import Enrichment

logger = logging.getLogger(__name__)

ENRICHMENT_CACHE_PATH = DATA_DIR / "enrichment_cache.json"


def _normalize_doi(doi: str | None) -> str | None:
    """Same normalization as transform.bronze_articles.normalize_doi.

    Duplicated (rather than imported) to avoid a circular import --
    bronze_articles imports this module to run the enrichment step.
    """
    if not doi:
        return None
    doi = doi.strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    return doi.strip().casefold() or None


def load_enrichment_cache(
    session: Session | None = None, path: Path | None = None
) -> dict[str, dict[str, int | None]]:
    """DOI -> {citation_count, reference_count}, from the DB and the legacy file.

    With a raw-layer `session`, `lit_enrichment` (filled by the `enrich` stage)
    is layered on top of the hand-built JSON file, so fetched values win and
    hand-assembled ones survive for DOIs the APIs don't know.

    Tolerates a missing file -- `data/` is gitignored and won't exist on a
    fresh checkout -- by returning what it has rather than raising.
    """
    cache_path = path or ENRICHMENT_CACHE_PATH
    if not cache_path.exists():
        return {}
    try:
        raw = json.loads(cache_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}

    normalized: dict[str, dict[str, int | None]] = {}
    for doi, values in raw.items():
        key = _normalize_doi(doi)
        if not key or not isinstance(values, dict):
            continue
        normalized[key] = {
            "citation_count": values.get("citation_count"),
            "reference_count": values.get("reference_count"),
        }

    if session is not None:
        normalized.update(_load_from_db(session))
    return normalized


def _load_from_db(session: Session) -> dict[str, dict[str, int | None]]:
    """The `enrich` stage's own table, tolerating a database that lacks it yet."""
    try:
        rows = session.execute(
            select(Enrichment.doi, Enrichment.citation_count, Enrichment.reference_count)
        ).all()
    except SQLAlchemyError:
        logger.warning("load_enrichment_cache: lit_enrichment unavailable", exc_info=True)
        session.rollback()
        return {}
    return {
        doi: {"citation_count": citation_count, "reference_count": reference_count}
        for doi, citation_count, reference_count in rows
    }
