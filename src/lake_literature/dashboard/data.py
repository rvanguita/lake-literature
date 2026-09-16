"""Data-loading helpers for the Streamlit dashboard.

Reads directly from the medallion MySQL databases (via the same per-layer
engines the pipeline uses) and returns plain pandas DataFrames. Every
function tolerates a layer/table that doesn't exist yet -- the dashboard is
meant to be usable even before the pipeline has been run end to end.
"""

from __future__ import annotations

import logging

import pandas as pd
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from lake_literature.db.engines import get_engine

logger = logging.getLogger(__name__)

LAYER_TABLES = {
    "raw": [
        "lit_source_files",
        "lit_config",
        "lit_ieee_csv_rows",
        "lit_bib_entries",
        "lit_pdf_files",
    ],
    "bronze": ["lit_articles"],
    "silver": ["lit_articles"],
    "gold": ["lit_articles", "lit_chunks"],
}


def table_exists(layer: str, table: str) -> bool:
    try:
        engine = get_engine(layer)
        return inspect(engine).has_table(table)
    except SQLAlchemyError:
        logger.warning("table_exists(%r, %r): database unreachable", layer, table, exc_info=True)
        return False


def layer_row_counts() -> pd.DataFrame:
    """One row per (layer, table) with its row count, or an error note."""
    rows = []
    for layer, tables in LAYER_TABLES.items():
        for table in tables:
            count = None
            status = "ok"
            try:
                engine = get_engine(layer)
                if inspect(engine).has_table(table):
                    with engine.connect() as conn:
                        count = conn.execute(text(f"SELECT COUNT(*) FROM `{table}`")).scalar()
                else:
                    count = 0
                    status = "no table yet"
            except SQLAlchemyError as exc:
                logger.warning(
                    "layer_row_counts(%r, %r): database unreachable", layer, table, exc_info=True
                )
                status = f"unreachable ({type(exc).__name__})"
            rows.append({"layer": layer, "table": table, "rows": count, "status": status})
    return pd.DataFrame(rows)


def load_articles(layer: str) -> pd.DataFrame:
    if not table_exists(layer, "lit_articles"):
        return pd.DataFrame()
    engine = get_engine(layer)
    return pd.read_sql_table("lit_articles", engine)


def load_search_configs() -> pd.DataFrame:
    """Per-source search provenance from `raw.lit_config` (query, filters, year range, URL)."""
    if not table_exists("raw", "lit_config"):
        return pd.DataFrame()
    engine = get_engine("raw")
    return pd.read_sql_table("lit_config", engine)


def pick_best_articles_layer() -> tuple[str, pd.DataFrame]:
    """Prefer silver (cleanest + quality flags), then bronze, then gold."""
    for layer in ("silver", "bronze", "gold"):
        df = load_articles(layer)
        if not df.empty:
            return layer, df
    return "none", pd.DataFrame()


def load_articles_all_layers() -> dict[str, pd.DataFrame]:
    """Load `articles` from bronze, silver, and gold in one call.

    Used by the pipeline/layers page to compare the medallion stages
    directly instead of only seeing the single "best" layer the rest of the
    dashboard uses.
    """
    return {layer: load_articles(layer) for layer in ("bronze", "silver", "gold")}


def load_chunks() -> pd.DataFrame:
    if not table_exists("gold", "lit_chunks"):
        return pd.DataFrame()
    engine = get_engine("gold")
    return pd.read_sql_table("lit_chunks", engine)


def raw_funnel_counts() -> dict[str, dict[str, int]]:
    """Per-source row counts for the raw-layer tables that feed bronze.

    Used by the pipeline/layers page's funnel chart -- `ieee_csv_rows` has no
    `source` column of its own (the CSV is IEEE-only), so it's reported as a
    single IEEE bucket alongside the two `bib_entries` sources.
    """
    counts = {
        "ieee": {"csv_rows": 0, "bib_entries": 0},
        "elsevier": {"csv_rows": 0, "bib_entries": 0},
    }
    try:
        engine = get_engine("raw")
        with engine.connect() as conn:
            if inspect(engine).has_table("lit_ieee_csv_rows"):
                counts["ieee"]["csv_rows"] = (
                    conn.execute(text("SELECT COUNT(*) FROM `lit_ieee_csv_rows`")).scalar() or 0
                )
            if inspect(engine).has_table("lit_bib_entries"):
                for source, n in conn.execute(
                    text("SELECT source, COUNT(*) FROM `lit_bib_entries` GROUP BY source")
                ):
                    counts.setdefault(source, {"csv_rows": 0, "bib_entries": 0})
                    counts[source]["bib_entries"] = n
    except SQLAlchemyError:
        logger.warning("raw_funnel_counts: database unreachable", exc_info=True)
    return counts


def bronze_doi_dropped_counts() -> dict[str, int]:
    """Bronze rows with no DOI, per source -- these never make it into silver.

    `silver_articles.py` counts this drop as `skipped_no_doi` but only prints
    it; this reconstructs the per-source breakdown live from bronze, which is
    never truncated.
    """
    result = {"ieee": 0, "elsevier": 0}
    try:
        engine = get_engine("bronze")
        if not inspect(engine).has_table("lit_articles"):
            return result
        with engine.connect() as conn:
            for source, n in conn.execute(
                text(
                    "SELECT source, COUNT(*) FROM `lit_articles` WHERE doi IS NULL GROUP BY source"
                )
            ):
                result[source] = n
    except SQLAlchemyError:
        logger.warning("bronze_doi_dropped_counts: database unreachable", exc_info=True)
    return result
