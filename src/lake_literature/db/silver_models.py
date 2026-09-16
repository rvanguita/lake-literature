"""SILVER layer models (lit_silver database) -- cleaned, conformed and
deduplicated. One row per normalized DOI (the reliable cross-source join
key -- see CLAUDE.md), with quality flags and a fuzzy-matched link to a PDF
in data/articles/ where one exists.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    doi: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    sources: Mapped[list] = mapped_column(JSON, default=list)  # ['ieee'] | ['elsevier'] | both
    record_type: Mapped[str] = mapped_column(String(32))

    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    authors: Mapped[list] = mapped_column(JSON, default=list)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(Text, nullable=True)
    volume: Mapped[str | None] = mapped_column(String(64), nullable=True)
    issue: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pages: Mapped[str | None] = mapped_column(String(64), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    citation_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reference_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # quality flags
    has_abstract: Mapped[bool] = mapped_column(Boolean, default=False)
    has_doi: Mapped[bool] = mapped_column(Boolean, default=True)
    is_duplicate_merge: Mapped[bool] = mapped_column(Boolean, default=False)

    # PDF link (fuzzy title match against data/articles/*.pdf)
    has_pdf: Mapped[bool] = mapped_column(Boolean, default=False)
    pdf_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_match_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    bronze_ids: Mapped[list] = mapped_column(JSON, default=list)  # source bronze.articles ids merged

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow
    )
