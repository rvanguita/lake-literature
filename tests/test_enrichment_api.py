"""Tests for the OpenAlex/Crossref enrichment client (ingest/enrichment_api.py).

Only the pure response-shaping and the "what still needs fetching" logic are
exercised -- no HTTP is performed, matching the repo's no-mocking convention:
the request functions are thin wrappers whose interesting part is the parsing
they delegate to.
"""

from __future__ import annotations

import datetime as dt

from lake_literature.db import utcnow
from lake_literature.db.raw_models import BibEntry, Enrichment
from lake_literature.ingest.enrichment_api import (
    parse_crossref_message,
    parse_openalex_work,
    pending_dois,
)


def test_parse_openalex_work_normalizes_the_doi_and_counts_references():
    parsed = parse_openalex_work(
        {
            "doi": "https://doi.org/10.1016/J.IJEPES.2020.106042",
            "cited_by_count": 12,
            "referenced_works": ["W1", "W2", "W3"],
        }
    )

    # OpenAlex returns the DOI as a URL in mixed case; bronze looks it up bare
    # and casefolded, so it has to be normalized here or the join never hits.
    assert parsed["doi"] == "10.1016/j.ijepes.2020.106042"
    assert parsed["citation_count"] == 12
    # OpenAlex has no reference-count field -- the list length is the count.
    assert parsed["reference_count"] == 3


def test_parse_openalex_work_without_a_doi_is_skipped():
    assert parse_openalex_work({"cited_by_count": 5}) is None


def test_parse_openalex_work_with_no_referenced_works_counts_zero():
    parsed = parse_openalex_work({"doi": "10.1109/x", "cited_by_count": 0})
    assert parsed["reference_count"] == 0


def test_parse_crossref_message_maps_its_own_field_names():
    parsed = parse_crossref_message(
        {"DOI": "10.1109/TPWRS.2024.3418651", "is-referenced-by-count": 4, "reference-count": 30}
    )

    assert parsed["doi"] == "10.1109/tpwrs.2024.3418651"
    assert parsed["citation_count"] == 4
    assert parsed["reference_count"] == 30


def _bib(raw_session, doi: str, key: str) -> None:
    raw_session.add(
        BibEntry(
            source="elsevier",
            bib_key=key,
            entry_type="article",
            source_file="data/elsevier/x.bib",
            fields={},
            doi=doi,
        )
    )


def test_pending_dois_lists_every_known_doi_normalized(raw_session):
    _bib(raw_session, "https://doi.org/10.1016/J.ONE", "a")
    _bib(raw_session, "10.1109/two", "b")
    raw_session.commit()

    assert pending_dois(raw_session) == ["10.1016/j.one", "10.1109/two"]


def test_recently_fetched_dois_are_not_pending_again(raw_session):
    _bib(raw_session, "10.1016/j.one", "a")
    _bib(raw_session, "10.1109/two", "b")
    raw_session.add(
        Enrichment(doi="10.1016/j.one", citation_count=3, reference_count=9, source_api="openalex")
    )
    raw_session.commit()

    # This is what makes re-running the stage cheap instead of re-querying the
    # whole corpus every time.
    assert pending_dois(raw_session) == ["10.1109/two"]


def test_a_stale_enrichment_becomes_pending_again(raw_session):
    _bib(raw_session, "10.1016/j.one", "a")
    raw_session.add(
        Enrichment(
            doi="10.1016/j.one",
            citation_count=3,
            reference_count=9,
            source_api="openalex",
            fetched_at=utcnow() - dt.timedelta(days=400),
        )
    )
    raw_session.commit()

    assert pending_dois(raw_session) == ["10.1016/j.one"]
