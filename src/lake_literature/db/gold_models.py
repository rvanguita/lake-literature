"""GOLD layer models (lit_gold database) -- curated, RAG-ready.

`articles` is the table a human or agent scans to decide which paper to cite.
`chunks` is the RAG ingestion unit: one row per passage of text. `embedding`/
`embed_model` are filled in by the `embed` pipeline stage
(`transform/embeddings.py`, via `fastembed`) -- they stay NULL only until
that stage has been run at least once for a given chunk.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Article(Base):
    __tablename__ = "lit_articles_gold"

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

    has_pdf: Mapped[bool] = mapped_column(Boolean, default=False)
    pdf_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    silver_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class Chunk(Base):
    __tablename__ = "lit_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    doi: Mapped[str] = mapped_column(String(255), index=True)  # value-FK to lit_articles_gold.doi
    seq: Mapped[int] = mapped_column(Integer)
    chunk_type: Mapped[str] = mapped_column(String(32))  # 'abstract' | 'fulltext'
    text: Mapped[str] = mapped_column(Text)
    char_len: Mapped[int] = mapped_column(Integer)

    embedding: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # filled by --stage embed
    embed_model: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
