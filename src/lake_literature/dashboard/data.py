"""Data-loading helpers for the Streamlit dashboard.

Reads directly from the medallion MySQL databases (via the same per-layer
engines the pipeline uses) and returns plain pandas DataFrames. Every
function tolerates a layer/table that doesn't exist yet -- the dashboard is
meant to be usable even before the pipeline has been run end to end.
"""

from __future__ import annotations

import logging

import pandas as pd
from sqlalchemy import MetaData, Table, inspect, select, text
from sqlalchemy.exc import SQLAlchemyError

from lake_literature.db.engines import get_engine

logger = logging.getLogger(__name__)

LAYER_TABLES = {
    "raw": [
        "lit_pipeline_runs",
        "lit_source_files",
        "lit_config",
        "lit_ieee_csv_rows",
        "lit_bib_entries",
        "lit_pdf_files",
    ],
    "bronze": ["lit_articles"],
    "silver": ["lit_articles"],
    "gold": ["lit_articles", "lit_chunks", "lit_semantics", "lit_duplicate_pairs"],
}


def table_exists(layer: str, table: str) -> bool:
    try:
        engine = get_engine(layer)
        return inspect(engine).has_table(table)
    except SQLAlchemyError as exc:
        logger.warning("table_exists(%r, %r): database unreachable (%s)", layer, table, exc)
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
                    "layer_row_counts(%r, %r): database unreachable (%s)", layer, table, exc
                )
                status = f"unreachable ({type(exc).__name__})"
            rows.append({"layer": layer, "table": table, "rows": count, "status": status})
    return pd.DataFrame(rows)


def load_articles(layer: str) -> pd.DataFrame:
    if not table_exists(layer, "lit_articles"):
        return pd.DataFrame()
    engine = get_engine(layer)
    return pd.read_sql_table("lit_articles", engine)


def load_pipeline_runs(limit: int = 50) -> pd.DataFrame:
    """Most recent stage executions from `raw.lit_pipeline_runs`, newest first.

    Written by `pipeline.py`'s `_recorded` wrapper, so it covers runs started
    from the CLI as well as from Airflow (whose tasks shell out to that CLI) --
    unlike Airflow's own history, which only sees what it triggered.
    """
    if not table_exists("raw", "lit_pipeline_runs"):
        return pd.DataFrame()
    engine = get_engine("raw")
    return pd.read_sql_query(
        text(
            "SELECT stage, started_at, finished_at, status, stats, error "
            "FROM `lit_pipeline_runs` ORDER BY started_at DESC LIMIT :limit"
        ),
        engine,
        params={"limit": limit},
    )


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


_CHUNK_LIGHT_COLUMNS = ("id", "doi", "seq", "chunk_type", "char_len", "embed_model", "created_at")


def load_chunks() -> pd.DataFrame:
    """Lightweight chunk metadata from `gold.lit_chunks`: everything the
    dashboard's aggregate stats/charts need, without the `text` and
    `embedding` columns. Both are large per row -- `embedding` is a ~768-float
    JSON vector -- and unused outside the on-demand search box in
    `pages/quality.py`, which pulls them separately via
    `load_chunk_search_data` only once a query is actually submitted.
    Deserializing them here for every row dominated render time on every page
    that touches chunk counts (~7s for ~6k rows just for this one query).
    """
    if not table_exists("gold", "lit_chunks"):
        return pd.DataFrame()
    engine = get_engine("gold")
    table = Table("lit_chunks", MetaData(), autoload_with=engine)
    columns = [table.c[name] for name in _CHUNK_LIGHT_COLUMNS if name in table.c]
    columns.append(table.c.embedding.is_not(None).label("has_embedding"))
    return pd.read_sql_query(select(*columns), engine)


def load_semantics() -> pd.DataFrame:
    """Per-article semantic signals from `gold.lit_semantics` (`--stage semantic`)."""
    if not table_exists("gold", "lit_semantics"):
        return pd.DataFrame()
    return pd.read_sql_table("lit_semantics", get_engine("gold"))


def semantic_freshness() -> dict:
    """How well `lit_semantics` still matches the embeddings it was derived from.

    `--stage gold` rebuilds the chunks, and a chunk whose text changed loses its
    vector (see `transform/gold_articles.py`). A `semantic` run made before that
    therefore describes a corpus state that may no longer exist -- which is
    exactly what happened in production and was invisible in the UI, because
    every page renders `lit_semantics` without checking whether the embeddings
    behind it are still there.

    `orphaned` counts semantic rows whose article no longer has an embedded
    abstract chunk; `coverage` is how much of the corpus the `embed` stage has
    actually processed.
    """
    result = {
        "available": False,
        "abstract_chunks": 0,
        "embedded_abstract_chunks": 0,
        "coverage": 0.0,
        "semantics_rows": 0,
        "orphaned": 0,
        "is_stale": False,
    }
    if not table_exists("gold", "lit_chunks"):
        return result

    try:
        engine = get_engine("gold")
        with engine.connect() as conn:
            total, embedded = conn.execute(
                text(
                    "SELECT COUNT(*), SUM(embedding IS NOT NULL) FROM `lit_chunks` "
                    "WHERE chunk_type = 'abstract'"
                )
            ).one()
            result["abstract_chunks"] = int(total or 0)
            result["embedded_abstract_chunks"] = int(embedded or 0)
            result["coverage"] = (
                result["embedded_abstract_chunks"] / result["abstract_chunks"]
                if result["abstract_chunks"]
                else 0.0
            )

            if inspect(engine).has_table("lit_semantics"):
                result["semantics_rows"] = (
                    conn.execute(text("SELECT COUNT(*) FROM `lit_semantics`")).scalar() or 0
                )
                result["orphaned"] = (
                    conn.execute(
                        text(
                            "SELECT COUNT(*) FROM `lit_semantics` s WHERE NOT EXISTS ("
                            "SELECT 1 FROM `lit_chunks` c WHERE c.doi = s.doi "
                            "AND c.chunk_type = 'abstract' AND c.embedding IS NOT NULL)"
                        )
                    ).scalar()
                    or 0
                )
        result["available"] = True
    except SQLAlchemyError as exc:
        logger.warning("semantic_freshness: database unreachable (%s)", exc)
        return result

    result["is_stale"] = result["semantics_rows"] > 0 and (
        result["orphaned"] > 0 or result["coverage"] < 1.0
    )
    return result


def load_duplicate_pairs() -> pd.DataFrame:
    """Near-duplicate abstract pairs flagged by `--stage semantic`."""
    if not table_exists("gold", "lit_duplicate_pairs"):
        return pd.DataFrame()
    return pd.read_sql_table("lit_duplicate_pairs", get_engine("gold"))


def load_chunk_search_data() -> pd.DataFrame:
    """Full chunk rows (`text` + `embedding`), for the search box in
    `pages/quality.py` -- loaded lazily, only once a query is actually
    submitted, never on a plain page render.
    """
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
    except SQLAlchemyError as exc:
        logger.warning("raw_funnel_counts: database unreachable (%s)", exc)
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
    except SQLAlchemyError as exc:
        logger.warning("bronze_doi_dropped_counts: database unreachable (%s)", exc)
    return result
