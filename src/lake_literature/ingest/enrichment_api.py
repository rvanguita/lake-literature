"""Fetch citation/reference counts per DOI from public metadata APIs.

Runs as the `enrich` stage, between `raw` and `bronze`, and writes
`raw.lit_enrichment` -- which `ingest/enrichment.py` then feeds into the bronze
build. It exists because the corpus's own exports don't carry these numbers:
Elsevier's `.bib` has neither count, and the IEEE CSV only covers IEEE records,
so roughly five sixths of the corpus had no impact data except what a person
had assembled by hand into `data/enrichment_cache.json` for one snapshot.

OpenAlex is queried first, in batches (its `filter=doi:a|b|c` takes many DOIs
per request); Crossref is the per-DOI fallback for what OpenAlex doesn't know.
Both are free and keyless. Neither count means the same thing as IEEE Xplore's
own -- different corpora, different counting windows -- which is why the bronze
step only ever *fills* a NULL and never overwrites a publisher-provided value
(see `transform/bronze_articles.py::_enrich_citation_counts`).
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import time

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from lake_literature.db import utcnow
from lake_literature.db.raw_models import BibEntry, Enrichment, IeeeCsvRow
from lake_literature.ingest.enrichment import _normalize_doi

logger = logging.getLogger(__name__)

OPENALEX_URL = "https://api.openalex.org/works"
CROSSREF_URL = "https://api.crossref.org/works/{doi}"

# OpenAlex accepts up to 50 values in one `filter=doi:a|b|c` request, which
# turns the whole corpus into a few dozen calls instead of a few thousand.
OPENALEX_BATCH_SIZE = 50
REQUEST_TIMEOUT = 20  # seconds
COURTESY_DELAY = 0.2  # seconds between requests -- both APIs ask for restraint
# Counts change slowly; anything fetched more recently than this is left alone,
# which is what makes re-running the stage cheap.
REFRESH_AFTER_DAYS = 30
# How many unknown DOIs to chase individually on Crossref in one run, so a
# corpus full of un-indexed DOIs can't turn into thousands of requests.
MAX_CROSSREF_LOOKUPS = 200


def _mailto() -> str | None:
    """Contact address for the APIs' "polite pool", from `ENRICHMENT_MAILTO`.

    Deliberately not hardcoded: it is a personal address that gets sent to a
    third party on every request, so it stays an opt-in setting in `.env`.
    Without it both APIs still answer, just from the shared anonymous pool.
    """
    return os.environ.get("ENRICHMENT_MAILTO") or None


def _params(extra: dict) -> dict:
    mailto = _mailto()
    return {**extra, "mailto": mailto} if mailto else extra


def parse_openalex_work(work: dict) -> dict | None:
    """`{doi, citation_count, reference_count}` from one OpenAlex work."""
    doi = _normalize_doi(work.get("doi"))
    if not doi:
        return None
    referenced = work.get("referenced_works") or []
    return {
        "doi": doi,
        "citation_count": work.get("cited_by_count"),
        # OpenAlex has no reference *count* field -- the list of referenced
        # works is the count, and an empty list genuinely means "none indexed".
        "reference_count": len(referenced),
    }


def parse_crossref_message(message: dict) -> dict | None:
    """`{doi, citation_count, reference_count}` from one Crossref message."""
    doi = _normalize_doi(message.get("DOI"))
    if not doi:
        return None
    return {
        "doi": doi,
        "citation_count": message.get("is-referenced-by-count"),
        "reference_count": message.get("reference-count"),
    }


def fetch_openalex(dois: list[str]) -> dict[str, dict]:
    """Look up a batch of DOIs on OpenAlex. Returns `{doi: values}`."""
    if not dois:
        return {}
    params = _params(
        {
            "filter": "doi:" + "|".join(dois),
            "per-page": str(len(dois)),
            "select": "doi,cited_by_count,referenced_works",
        }
    )
    try:
        resp = requests.get(OPENALEX_URL, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except (requests.RequestException, ValueError):
        # Network error, rate limit, or a non-JSON body: this stage is a
        # best-effort top-up, never a reason to fail the pipeline.
        logger.warning("fetch_openalex: batch of %d DOIs failed", len(dois), exc_info=True)
        return {}

    found = {}
    for work in results:
        parsed = parse_openalex_work(work)
        if parsed:
            found[parsed["doi"]] = parsed
    return found


def fetch_crossref(doi: str) -> dict | None:
    """Look up a single DOI on Crossref, for what OpenAlex didn't have."""
    try:
        resp = requests.get(
            CROSSREF_URL.format(doi=doi), params=_params({}), timeout=REQUEST_TIMEOUT
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        message = resp.json().get("message", {})
    except (requests.RequestException, ValueError):
        logger.warning("fetch_crossref: %r failed", doi, exc_info=True)
        return None
    return parse_crossref_message(message)


def _target_dois(raw_session: Session) -> set[str]:
    """Every DOI the raw layer knows about, normalized."""
    dois = set()
    for (doi,) in raw_session.execute(select(BibEntry.doi).where(BibEntry.doi.is_not(None))):
        normalized = _normalize_doi(doi)
        if normalized:
            dois.add(normalized)
    for (doi,) in raw_session.execute(select(IeeeCsvRow.doi).where(IeeeCsvRow.doi.is_not(None))):
        normalized = _normalize_doi(doi)
        if normalized:
            dois.add(normalized)
    return dois


def _stale_cutoff() -> dt.datetime:
    return utcnow() - dt.timedelta(days=REFRESH_AFTER_DAYS)


def pending_dois(raw_session: Session) -> list[str]:
    """DOIs with no enrichment row yet, or one older than `REFRESH_AFTER_DAYS`."""
    fresh = {
        doi
        for (doi,) in raw_session.execute(
            select(Enrichment.doi).where(Enrichment.fetched_at >= _stale_cutoff())
        )
    }
    return sorted(_target_dois(raw_session) - fresh)


def _upsert(raw_session: Session, values: dict, source_api: str) -> None:
    existing = raw_session.scalar(select(Enrichment).where(Enrichment.doi == values["doi"]))
    if existing is None:
        raw_session.add(
            Enrichment(
                doi=values["doi"],
                citation_count=values["citation_count"],
                reference_count=values["reference_count"],
                source_api=source_api,
            )
        )
        return
    existing.citation_count = values["citation_count"]
    existing.reference_count = values["reference_count"]
    existing.source_api = source_api
    existing.fetched_at = utcnow()


def build_enrichment(raw_session: Session, limit: int | None = None) -> dict:
    """Fetch and store counts for every DOI that needs them.

    Idempotent by design: a second run right after the first finds nothing
    pending and makes no requests at all.
    """
    pending = pending_dois(raw_session)
    if limit is not None:
        pending = pending[:limit]
    if not pending:
        return {"pending": 0, "openalex": 0, "crossref": 0, "not_found": 0}

    from_openalex = 0
    for start in range(0, len(pending), OPENALEX_BATCH_SIZE):
        batch = pending[start : start + OPENALEX_BATCH_SIZE]
        for values in fetch_openalex(batch).values():
            _upsert(raw_session, values, "openalex")
            from_openalex += 1
        raw_session.commit()
        time.sleep(COURTESY_DELAY)

    known = {
        doi
        for (doi,) in raw_session.execute(select(Enrichment.doi).where(Enrichment.doi.in_(pending)))
    }
    missing = [doi for doi in pending if doi not in known][:MAX_CROSSREF_LOOKUPS]

    from_crossref = 0
    for doi in missing:
        values = fetch_crossref(doi)
        time.sleep(COURTESY_DELAY)
        if values is None:
            continue
        _upsert(raw_session, values, "crossref")
        from_crossref += 1
    raw_session.commit()

    return {
        "pending": len(pending),
        "openalex": from_openalex,
        "crossref": from_crossref,
        "not_found": len(pending) - from_openalex - from_crossref,
    }
