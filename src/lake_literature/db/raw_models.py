"""RAW layer models (lit_raw database) -- verbatim ingestion, one table per
source artifact type. Nothing here is normalized or deduplicated; it exists
so every downstream layer can be rebuilt without re-touching the filesystem.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from lake_literature.db import utcnow


class Base(DeclarativeBase):
    pass


class SourceFile(Base):
    """Manifest of every file ingested, for idempotent re-runs."""

    __tablename__ = "lit_source_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 512 chars * 4 bytes (utf8mb4) = 2048 bytes, under MySQL's 3072-byte max key
    # length; real corpus paths top out at ~220 chars, so there's ample headroom.
    path: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(32))  # 'ieee' | 'elsevier' | 'articles'
    kind: Mapped[str] = mapped_column(String(32))  # 'csv' | 'bib' | 'pdf' | 'config'
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    mtime: Mapped[dt.datetime] = mapped_column(DateTime)
    ingested_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class PipelineRun(Base):
    """One row per stage execution, however the stage was started.

    Airflow keeps run history, but only for runs triggered through Airflow -- a
    `uv run lake-literature --stage ...` from a terminal left no trace at all,
    and the dashboard had to infer what had run from live row counts. This is
    the durable record of what ran, when, and with what result.
    """

    __tablename__ = "lit_pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stage: Mapped[str] = mapped_column(String(32), index=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16))  # 'running' | 'success' | 'error'
    stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Config(Base):
    """Parsed provenance from data/{ieee,elsevier}/config.csv (free text)."""

    __tablename__ = "lit_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), unique=True)
    query_string: Mapped[str | None] = mapped_column(Text, nullable=True)
    filters: Mapped[str | None] = mapped_column(Text, nullable=True)
    year_range: Mapped[str | None] = mapped_column(String(64), nullable=True)
    search_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text: Mapped[str] = mapped_column(Text)
    source_file: Mapped[str] = mapped_column(String(512))


class Enrichment(Base):
    """Citation/reference counts fetched per DOI from a public metadata API.

    Elsevier's .bib carries neither count and the IEEE CSV only covers its own
    records, so most of the corpus has no impact data of its own. This replaces
    `data/enrichment_cache.json`, which was hand-built for one corpus snapshot
    and therefore left every newly added record empty forever.
    """

    __tablename__ = "lit_enrichment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doi: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    citation_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reference_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_api: Mapped[str] = mapped_column(String(32))  # 'openalex' | 'crossref'
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class IeeeCsvRow(Base):
    """One row per line of data/ieee/export*.csv, columns kept as text."""

    __tablename__ = "lit_ieee_csv_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    row_index: Mapped[int] = mapped_column(Integer)
    # part of a 2-column unique key below -- 512*4 = 2048 bytes, under the 3072 cap
    source_file: Mapped[str] = mapped_column(String(512))
    fields: Mapped[dict] = mapped_column(JSON)  # {csv column name: value}
    doi: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)

    __table_args__ = (UniqueConstraint("source_file", "row_index"),)


class BibEntry(Base):
    """One row per BibTeX entry, either source, fields kept as raw JSON."""

    __tablename__ = "lit_bib_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), index=True)  # 'ieee' | 'elsevier'
    bib_key: Mapped[str] = mapped_column(String(255), index=True)
    entry_type: Mapped[str] = mapped_column(String(32))  # article, incollection, book...
    # part of a 3-column unique key below -- (32+255+255)*4 = 2168 bytes, under 3072
    source_file: Mapped[str] = mapped_column(String(255))
    fields: Mapped[dict] = mapped_column(JSON)  # {bibtex field name: value}
    doi: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)

    __table_args__ = (UniqueConstraint("source", "bib_key", "source_file"),)


class PdfFile(Base):
    """Inventory of data/articles/*.pdf."""

    __tablename__ = "lit_pdf_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255), unique=True)  # 255*4=1020 bytes
    path: Mapped[str] = mapped_column(String(512))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
