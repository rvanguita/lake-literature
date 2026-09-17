"""GOLD layer models (lit_gold database) -- curated, RAG-ready.

`articles` is the table a human or agent scans to decide which paper to cite.
`chunks` is the RAG ingestion unit: one row per passage of text. `embedding`/
`embed_model` are filled in by the `embed` pipeline stage
(`transform/embeddings.py`, via `fastembed`) -- they stay NULL only until
that stage has been run at least once for a given chunk.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from lake_literature.db import utcnow


class Base(DeclarativeBase):
    pass


class Article(Base):
    __tablename__ = "lit_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    doi: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    sources: Mapped[list] = mapped_column(JSON, default=list)  # ['ieee'] / ['elsevier'] / both
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    authors: Mapped[list] = mapped_column(JSON, default=list)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    citation_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reference_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # IEEE-only (see bronze_models).
    countries: Mapped[list] = mapped_column(JSON, default=list)
    online_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    license: Mapped[str | None] = mapped_column(String(64), nullable=True)

    has_pdf: Mapped[bool] = mapped_column(Boolean, default=False)
    pdf_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    silver_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class Chunk(Base):
    __tablename__ = "lit_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    doi: Mapped[str] = mapped_column(String(255), index=True)  # value-FK to lit_articles.doi
    seq: Mapped[int] = mapped_column(Integer)
    chunk_type: Mapped[str] = mapped_column(String(32))  # 'abstract' | 'fulltext'
    text: Mapped[str] = mapped_column(Text)
    char_len: Mapped[int] = mapped_column(Integer)

    embedding: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # filled by --stage embed
    embed_model: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class Semantics(Base):
    """Per-article signals derived from the abstract embedding, by `--stage semantic`.

    Kept in its own table rather than as columns on `Article` so the semantic
    stage can truncate and rebuild everything it owns without touching the
    curated article rows.
    """

    __tablename__ = "lit_semantics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    doi: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    # Cosine similarity to the topic anchor (see transform/semantics.py). Both
    # vectors are L2-normalized, so this is in [-1, 1] and in practice ~0.4-0.9.
    relevance_score: Mapped[float] = mapped_column(Float)

    theme_id: Mapped[int] = mapped_column(Integer, index=True)
    theme_label: Mapped[str] = mapped_column(String(255))

    # 2D projection for the semantic map -- only meaningful relative to the
    # other rows of the same run, never as an absolute coordinate.
    map_x: Mapped[float] = mapped_column(Float)
    map_y: Mapped[float] = mapped_column(Float)

    embed_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class DuplicatePair(Base):
    """Near-identical abstracts that survived DOI deduplication as separate rows.

    DOI is this corpus's only reliable dedup key (see CLAUDE.md), so two
    printings of the same work under different DOIs stay separate. This table
    flags those for human review -- it never merges anything on its own.
    """

    __tablename__ = "lit_duplicate_pairs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    doi_a: Mapped[str] = mapped_column(String(255), index=True)
    doi_b: Mapped[str] = mapped_column(String(255), index=True)
    similarity: Mapped[float] = mapped_column(Float)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
