"""Build lit_bronze.articles from lit_raw -- this is where cross-source
consolidation begins (IEEE CSV + IEEE .bib + Elsevier .bib all become one
common schema). No cross-source dedup or quality filtering yet (silver's
job); pure pagination duplicates within a source collapse naturally via the
`(source, source_id)` unique key.

IEEE reconciliation: the CSV (304 rows / 301 DOIs) is the authoritative
record list; the paginated .bib files only cover ~275 entries and are mostly
a subset. Bronze builds one record per CSV row (enriched with the matching
.bib abstract/keywords when present), plus one record per .bib entry whose
DOI never appears in the CSV -- see CLAUDE.md "counts don't line up".
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from lake_literature.db.bronze_models import Article as BronzeArticle
from lake_literature.db.raw_models import BibEntry, IeeeCsvRow
from lake_literature.ingest.enrichment import load_enrichment_cache


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    doi = doi.strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    return doi.strip().casefold() or None


def _strip_braces(text: str) -> str:
    return text.replace("{", "").replace("}", "")


def _split_bibtex_authors(author_field: str | None) -> list[str]:
    if not author_field:
        return []
    return [_strip_braces(a).strip() for a in author_field.split(" and ") if a.strip()]


def _split_ieee_csv_authors(author_field) -> list[str]:
    if not isinstance(author_field, str) or not author_field.strip():
        return []
    return [a.strip() for a in author_field.split(";") if a.strip()]


def _split_keywords(text: str | None, sep: str) -> list[str]:
    if not text:
        return []
    return [k.strip() for k in text.split(sep) if k.strip()]


def _to_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _upsert(session: Session, source: str, source_id: str, **fields) -> None:
    existing = session.scalar(
        select(BronzeArticle).where(
            BronzeArticle.source == source, BronzeArticle.source_id == source_id
        )
    )
    if existing is None:
        session.add(BronzeArticle(source=source, source_id=source_id, **fields))
    else:
        for key, value in fields.items():
            setattr(existing, key, value)


def _build_ieee_records(raw_session: Session, bronze_session: Session) -> int:
    csv_rows = raw_session.scalars(select(IeeeCsvRow)).all()
    bib_entries = raw_session.scalars(
        select(BibEntry).where(BibEntry.source == "ieee")
    ).all()

    bib_by_doi: dict[str, BibEntry] = {}
    for entry in bib_entries:
        doi = normalize_doi(entry.doi)
        if doi:
            bib_by_doi[doi] = entry

    csv_dois: set[str] = set()
    written = 0

    for row in csv_rows:
        f = row.fields
        doi = normalize_doi(f.get("DOI"))
        if doi:
            csv_dois.add(doi)
        matching_bib = bib_by_doi.get(doi) if doi else None

        keywords = _split_keywords(f.get("Author Keywords"), ";") + _split_keywords(
            f.get("IEEE Terms"), ";"
        )
        abstract = f.get("Abstract")
        if not abstract and matching_bib:
            abstract = matching_bib.fields.get("abstract")
        if not keywords and matching_bib:
            keywords = _split_keywords(matching_bib.fields.get("keywords"), ";")

        start_page = f.get("Start Page")
        end_page = f.get("End Page")
        pages = None
        if start_page and end_page:
            pages = f"{start_page}-{end_page}"
        elif start_page:
            pages = str(start_page)

        _upsert(
            bronze_session,
            source="ieee",
            source_id=f"csv:{row.row_index}",
            record_type="article",
            doi=doi,
            title=f.get("Document Title"),
            authors=_split_ieee_csv_authors(f.get("Authors")),
            year=_to_int(f.get("Publication Year")),
            venue=f.get("Publication Title"),
            volume=str(f.get("Volume")) if f.get("Volume") is not None else None,
            issue=str(f.get("Issue")) if f.get("Issue") is not None else None,
            pages=pages,
            issn=f.get("ISSN"),
            url=f.get("PDF Link"),
            abstract=abstract,
            keywords=keywords,
            citation_count=_to_int(f.get("Article Citation Count")),
            reference_count=_to_int(f.get("Reference Count")),
            raw_csv_id=row.id,
            raw_bib_id=matching_bib.id if matching_bib else None,
        )
        written += 1

    # .bib entries whose DOI never showed up in the CSV -- CLAUDE.md notes the
    # counts genuinely don't line up; keep them rather than silently dropping.
    for entry in bib_entries:
        doi = normalize_doi(entry.doi)
        if doi and doi in csv_dois:
            continue
        f = entry.fields
        _upsert(
            bronze_session,
            source="ieee",
            source_id=f"bib:{entry.bib_key}",
            record_type=entry.entry_type.lower(),
            doi=doi,
            title=f.get("title"),
            authors=_split_bibtex_authors(f.get("author")),
            year=_to_int(f.get("year")),
            venue=f.get("journal") or f.get("booktitle"),
            volume=f.get("volume"),
            issue=f.get("number"),
            pages=f.get("pages"),
            issn=f.get("ISSN") or f.get("issn"),
            url=f.get("url"),
            abstract=f.get("abstract"),
            keywords=_split_keywords(f.get("keywords"), ";"),
            citation_count=None,
            reference_count=None,
            raw_csv_id=None,
            raw_bib_id=entry.id,
        )
        written += 1

    return written


def _build_elsevier_records(raw_session: Session, bronze_session: Session) -> int:
    bib_entries = raw_session.scalars(
        select(BibEntry).where(BibEntry.source == "elsevier")
    ).all()
    written = 0
    for entry in bib_entries:
        f = entry.fields
        doi = normalize_doi(entry.doi)

        _upsert(
            bronze_session,
            source="elsevier",
            source_id=f"bib:{entry.bib_key}",
            record_type=entry.entry_type.lower(),
            doi=doi,
            title=f.get("title"),
            authors=_split_bibtex_authors(f.get("author")),
            year=_to_int(f.get("year")),
            venue=f.get("journal") or f.get("booktitle"),
            volume=f.get("volume"),
            issue=f.get("number"),
            pages=f.get("pages"),
            issn=f.get("issn"),
            url=f.get("url"),
            abstract=f.get("abstract"),
            keywords=_split_keywords(f.get("keywords"), ","),
            citation_count=None,
            reference_count=None,
            raw_csv_id=None,
            raw_bib_id=entry.id,
        )
        written += 1

    return written


def _enrich_citation_counts(bronze_session: Session) -> int:
    """Backfill citation_count/reference_count from the enrichment cache.

    Only fills a field that is currently NULL -- the IEEE CSV's own counts
    are the authoritative source where they exist and must never be
    overwritten by the cache.
    """
    cache = load_enrichment_cache()
    if not cache:
        return 0

    enriched = 0
    articles = bronze_session.scalars(
        select(BronzeArticle).where(BronzeArticle.doi.in_(cache.keys()))
    ).all()
    for article in articles:
        values = cache.get(article.doi)
        if not values:
            continue
        changed = False
        if article.citation_count is None and values.get("citation_count") is not None:
            article.citation_count = values["citation_count"]
            changed = True
        if article.reference_count is None and values.get("reference_count") is not None:
            article.reference_count = values["reference_count"]
            changed = True
        if changed:
            enriched += 1

    return enriched


def build_bronze_articles(raw_session: Session, bronze_session: Session) -> dict[str, int]:
    written = _build_ieee_records(raw_session, bronze_session)
    written += _build_elsevier_records(raw_session, bronze_session)
    bronze_session.flush()
    enriched = _enrich_citation_counts(bronze_session)
    bronze_session.commit()
    return {"written": written, "enriched": enriched}
