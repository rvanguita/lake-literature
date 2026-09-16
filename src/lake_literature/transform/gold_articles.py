"""Build lit_gold.articles + lit_gold.chunks from lit_silver.articles.

`articles` is the curated table a human/agent scans to pick a reference.
`chunks` is the RAG ingestion unit: every article gets an 'abstract' chunk
(title + abstract + keywords), and articles with a linked PDF (has_pdf) also
get 'fulltext' chunks extracted via pypdf and split into fixed-size windows.
`embedding`/`embed_model` stay NULL here -- `transform/embeddings.py` (the
`embed` pipeline stage, run after this one) fills them in separately.
"""

from __future__ import annotations

import re

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from lake_literature.config import absolute_path
from lake_literature.db.gold_models import Article as GoldArticle
from lake_literature.db.gold_models import Chunk
from lake_literature.db.silver_models import Article as SilverArticle

CHUNK_MAX_CHARS = 1500
CHUNK_OVERLAP_CHARS = 200


def _build_abstract_text(row: SilverArticle) -> str:
    parts = [row.title or ""]
    if row.keywords:
        parts.append("Keywords: " + ", ".join(row.keywords))
    if row.abstract:
        parts.append(row.abstract)
    return "\n\n".join(p for p in parts if p).strip()


def _extract_pdf_text(pdf_path: str) -> str:
    # Paths are stored relative to the repo root (so the same file has the same
    # identity on the host and inside the Airflow container) -- resolve back to
    # an absolute path before actually opening it.
    try:
        reader = PdfReader(absolute_path(pdf_path))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception:
        return ""
    text = "\n\n".join(pages)
    return re.sub(r"[ \t]+", " ", text).strip()


def _chunk_text(text: str, max_chars: int = CHUNK_MAX_CHARS, overlap: int = CHUNK_OVERLAP_CHARS) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0
    min_boundary = max_chars // 2  # don't accept a break point too close to `start`
    while start < len(text):
        end = min(start + max_chars, len(text))
        # try to break on a paragraph/sentence boundary rather than mid-word,
        # but only if that boundary is reasonably close to the target size --
        # otherwise a break right after `start` would produce tiny chunks.
        if end < len(text):
            boundary = text.rfind("\n\n", start, end)
            if boundary == -1 or boundary - start < min_boundary:
                boundary = text.rfind(". ", start, end)
            if boundary != -1 and boundary - start >= min_boundary:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def build_gold_articles(silver_session: Session, gold_session: Session) -> dict:
    silver_rows = silver_session.scalars(select(SilverArticle)).all()

    gold_session.query(Chunk).delete()
    gold_session.query(GoldArticle).delete()

    n_articles = 0
    n_abstract_chunks = 0
    n_fulltext_chunks = 0

    for row in silver_rows:
        gold_article = GoldArticle(
            doi=row.doi,
            sources=row.sources or [],
            title=row.title,
            authors=row.authors or [],
            year=row.year,
            venue=row.venue,
            keywords=row.keywords or [],
            abstract=row.abstract,
            citation_count=row.citation_count,
            reference_count=row.reference_count,
            url=row.url,
            has_pdf=row.has_pdf,
            pdf_path=row.pdf_path,
            silver_id=row.id,
        )
        gold_session.add(gold_article)
        n_articles += 1

        abstract_text = _build_abstract_text(row)
        if abstract_text:
            gold_session.add(
                Chunk(
                    doi=row.doi,
                    seq=0,
                    chunk_type="abstract",
                    text=abstract_text,
                    char_len=len(abstract_text),
                )
            )
            n_abstract_chunks += 1

        if row.has_pdf and row.pdf_path:
            full_text = _extract_pdf_text(row.pdf_path)
            for seq, chunk in enumerate(_chunk_text(full_text), start=1):
                gold_session.add(
                    Chunk(
                        doi=row.doi,
                        seq=seq,
                        chunk_type="fulltext",
                        text=chunk,
                        char_len=len(chunk),
                    )
                )
                n_fulltext_chunks += 1

    gold_session.commit()

    return {
        "articles": n_articles,
        "abstract_chunks": n_abstract_chunks,
        "fulltext_chunks": n_fulltext_chunks,
    }
