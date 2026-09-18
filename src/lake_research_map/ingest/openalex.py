"""OpenAlex REST API client for automated citation & reference count enrichment.

Provides free, public bibliographic enrichment without requiring an API key.
OpenAlex allows up to 10 requests/second without authentication (polite pool
when including an email in headers or query params).

Touches `data/enrichment_cache.json` to store enriched counts incrementally.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from urllib.parse import quote

import requests

from lake_research_map.ingest.enrichment import ENRICHMENT_CACHE_PATH, _normalize_doi

logger = logging.getLogger(__name__)

OPENALEX_BASE_URL = "https://api.openalex.org/works"
DEFAULT_USER_AGENT = "lake-research-map/1.0 (https://github.com/rvanguita/lake-research-map; mailto:researcher@example.com)"


def fetch_openalex_work(
    doi: str,
    *,
    timeout: float = 8.0,
    email: str | None = None,
) -> dict[str, int | None] | None:
    """Fetch citation count and reference count from OpenAlex for a given DOI.

    Returns dict with 'citation_count' and 'reference_count', or None if not found/failed.
    """
    clean_doi = _normalize_doi(doi)
    if not clean_doi:
        return None

    url = f"{OPENALEX_BASE_URL}/https://doi.org/{quote(clean_doi, safe='')}"
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    params = {"mailto": email} if email else {}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=timeout)
        if response.status_code == 404:
            logger.debug("OpenAlex: DOI %s not found", clean_doi)
            return None
        response.raise_for_status()
        data = response.json()
        cited_by = data.get("cited_by_count")
        ref_count = len(data.get("referenced_works", []))

        return {
            "citation_count": int(cited_by) if cited_by is not None else None,
            "reference_count": int(ref_count) if ref_count is not None else None,
        }
    except requests.RequestException as e:
        logger.warning("OpenAlex request failed for %s: %s", clean_doi, e)
        return None


def enrich_cache_from_openalex(
    dois: list[str],
    *,
    cache_path: Path | None = None,
    max_fetch: int = 50,
    delay: float = 0.1,
    email: str | None = None,
) -> dict:
    """Enrich missing entries in `data/enrichment_cache.json` using OpenAlex.

    Operates incrementally: skips DOIs already present with non-null citation_count.
    Writes back to the cache file after completion.
    """
    path = cache_path or ENRICHMENT_CACHE_PATH
    cache: dict[str, dict[str, int | None]] = {}
    if path.exists():
        try:
            cache = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            cache = {}

    to_fetch: list[str] = []
    for raw_doi in dois:
        norm = _normalize_doi(raw_doi)
        if not norm:
            continue
        existing = cache.get(norm)
        if existing is None or existing.get("citation_count") is None:
            to_fetch.append(norm)

    fetched_count = 0
    updated_count = 0

    for doi in to_fetch[:max_fetch]:
        result = fetch_openalex_work(doi, email=email)
        fetched_count += 1
        if result and (
            result["citation_count"] is not None or result["reference_count"] is not None
        ):
            cache[doi] = result
            updated_count += 1
        if delay > 0:
            time.sleep(delay)

    if updated_count > 0:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, indent=2, sort_keys=True))

    return {
        "requested": len(dois),
        "pending": len(to_fetch),
        "fetched": fetched_count,
        "updated": updated_count,
        "total_cache_entries": len(cache),
    }
