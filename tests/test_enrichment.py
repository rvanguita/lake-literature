"""Tests for the citation/reference-count cache loader (ingest/enrichment.py).

This function stands between a hand-maintained JSON file and the bronze build,
so anything it fails to tolerate becomes a pipeline crash.
"""

from __future__ import annotations

import json

from lake_literature.ingest.enrichment import load_enrichment_cache


def test_missing_file_is_not_an_error(tmp_path):
    # `data/` is gitignored, so a fresh checkout has no cache file at all.
    assert load_enrichment_cache(path=tmp_path / "absent.json") == {}


def test_malformed_json_returns_empty_instead_of_raising(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text("{not valid json", encoding="utf-8")
    assert load_enrichment_cache(path=path) == {}


def test_non_dict_payload_returns_empty(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert load_enrichment_cache(path=path) == {}


def test_dois_are_normalized_the_same_way_bronze_normalizes_them(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text(
        json.dumps(
            {
                "https://doi.org/10.1016/J.IJEPES.2020.106042": {
                    "citation_count": 7,
                    "reference_count": 41,
                }
            }
        ),
        encoding="utf-8",
    )

    cache = load_enrichment_cache(path=path)

    # Keyed by bare, casefolded DOI -- otherwise the bronze lookup never hits.
    assert cache == {"10.1016/j.ijepes.2020.106042": {"citation_count": 7, "reference_count": 41}}


def test_entries_with_a_non_dict_value_are_skipped(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text(
        json.dumps({"10.1109/good": {"citation_count": 1}, "10.1109/bad": "oops"}),
        encoding="utf-8",
    )

    cache = load_enrichment_cache(path=path)

    assert set(cache) == {"10.1109/good"}
    assert cache["10.1109/good"]["reference_count"] is None


def test_fetched_values_win_over_the_hand_built_file(raw_session, tmp_path):
    from lake_literature.db.raw_models import Enrichment

    path = tmp_path / "cache.json"
    path.write_text(
        json.dumps(
            {
                "10.1109/fetched": {"citation_count": 1, "reference_count": 1},
                "10.1109/handmade": {"citation_count": 99, "reference_count": 42},
            }
        ),
        encoding="utf-8",
    )
    raw_session.add(
        Enrichment(
            doi="10.1109/fetched", citation_count=50, reference_count=30, source_api="openalex"
        )
    )
    raw_session.commit()

    cache = load_enrichment_cache(raw_session, path=path)

    # The API value supersedes the file...
    assert cache["10.1109/fetched"] == {"citation_count": 50, "reference_count": 30}
    # ...but a DOI only the hand-built file knows about is not lost.
    assert cache["10.1109/handmade"] == {"citation_count": 99, "reference_count": 42}
