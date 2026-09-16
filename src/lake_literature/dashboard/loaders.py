"""Cached data access for the dashboard pages.

Every page calls these instead of touching `data.py` directly, so the MySQL
round-trips are shared across pages through Streamlit's global cache, and the
normalization each page depends on (list columns, scalar `source`) happens in
exactly one place.
"""

from __future__ import annotations

import ast
import json

import pandas as pd
import streamlit as st

from lake_literature.dashboard.data import (
    bronze_doi_dropped_counts,
    layer_row_counts,
    load_articles_all_layers,
    load_chunks,
    load_search_configs,
    pick_best_articles_layer,
    raw_funnel_counts,
)


def _to_list(value):
    """Normalize a JSON/list-ish column value into a python list."""
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        for loader in (json.loads, ast.literal_eval):
            try:
                parsed = loader(value)
                if isinstance(parsed, list):
                    return parsed
            except (ValueError, SyntaxError, TypeError):
                continue
    return []


def _dataframe_cache_key(value: pd.DataFrame) -> str:
    """Stable cache key for frames containing JSON/list columns."""
    return value.to_json(orient="split", date_format="iso", default_handler=str)


@st.cache_data(ttl=60)
def row_counts() -> pd.DataFrame:
    return layer_row_counts()


@st.cache_data(ttl=60)
def chunks() -> pd.DataFrame:
    return load_chunks()


@st.cache_data(ttl=60)
def search_configs() -> pd.DataFrame:
    return load_search_configs()


def _normalize_article_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    for col in ("authors", "keywords", "sources"):
        if col in df.columns:
            df[col] = df[col].apply(_to_list)
    if "source" not in df.columns and "sources" in df.columns:
        df["source"] = df["sources"].apply(lambda s: s[0] if s else "unknown")
    return df


@st.cache_data(ttl=60)
def articles_by_layer() -> dict[str, pd.DataFrame]:
    """Bronze/silver/gold `articles`, each normalized the same way as `articles()`.

    Used by the pipeline/layers page to compare stages directly, rather than
    only seeing the single "best" layer the rest of the dashboard reads.
    """
    return {layer: _normalize_article_frame(df) for layer, df in load_articles_all_layers().items()}


@st.cache_data(ttl=60)
def layer_funnel() -> pd.DataFrame:
    """Raw -> bronze -> silver -> gold article counts, split by source.

    One row per (layer, source) with a `total` row per layer too -- shaped
    for the pipeline/layers funnel chart.
    """
    raw_counts = raw_funnel_counts()
    dropped = bronze_doi_dropped_counts()
    by_layer = articles_by_layer()

    rows = []
    for source in ("ieee", "elsevier"):
        raw_n = raw_counts.get(source, {}).get("csv_rows", 0) or raw_counts.get(source, {}).get(
            "bib_entries", 0
        )
        # IEEE raw volume is CSV-row-driven (the authoritative record list);
        # Elsevier has no CSV, so its raw count is bib entries.
        if source == "ieee":
            raw_n = raw_counts.get("ieee", {}).get("csv_rows", 0)
        else:
            raw_n = raw_counts.get("elsevier", {}).get("bib_entries", 0)

        bronze_df = by_layer.get("bronze", pd.DataFrame())
        silver_df = by_layer.get("silver", pd.DataFrame())
        gold_df = by_layer.get("gold", pd.DataFrame())

        bronze_n = int((bronze_df["source"] == source).sum()) if "source" in bronze_df.columns else 0
        silver_n = (
            int(silver_df["sources"].apply(lambda s: source in s).sum())
            if "sources" in silver_df.columns
            else 0
        )
        gold_n = (
            int(gold_df["sources"].apply(lambda s: source in s).sum())
            if "sources" in gold_df.columns
            else 0
        )
        rows.append(
            {
                "source": source,
                "raw": raw_n,
                "bronze": bronze_n,
                "dropped_no_doi": dropped.get(source, 0),
                "silver": silver_n,
                "gold": gold_n,
            }
        )
    return pd.DataFrame(rows)


@st.cache_data(ttl=60)
def articles() -> tuple[str, pd.DataFrame]:
    """Best available articles layer, with the normalization every page needs."""
    layer, df = pick_best_articles_layer()
    if df.empty:
        return layer, df

    df = df.copy()
    for col in ("authors", "keywords", "sources"):
        if col in df.columns:
            df[col] = df[col].apply(_to_list)

    # Charts that break down by source need a single scalar `source` column
    # regardless of which layer is active -- bronze has it already, silver only
    # has the plural `sources` list (there's no cross-source overlap in this
    # corpus, so the first entry is always the article's one true source).
    if "source" not in df.columns and "sources" in df.columns:
        df["source"] = df["sources"].apply(lambda s: s[0] if s else "unknown")

    return layer, df


@st.cache_data(ttl=60, hash_funcs={pd.DataFrame: _dataframe_cache_key})
def filter_articles(
    df: pd.DataFrame,
    year_range: tuple[int, int] | None = None,
    sources: tuple[str, ...] = (),
    venues: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Apply the dashboard-wide filters to a normalized article frame.

    The filter is cached separately from the database read so changing a
    widget never causes another MySQL round-trip. Empty source/venue tuples
    mean "all", which also keeps the state valid when a partial layer lacks a
    column.
    """
    filtered = df.copy()
    if year_range and "year" in filtered.columns:
        if isinstance(year_range, (int, float)):
            year_range = (int(year_range), int(year_range))
        years = pd.to_numeric(filtered["year"], errors="coerce")
        filtered = filtered.loc[
            years.ge(year_range[0]) & years.le(year_range[1])
        ]
    if sources and "source" in filtered.columns:
        filtered = filtered[filtered["source"].isin(sources)]
    if venues and "venue" in filtered.columns:
        filtered = filtered[filtered["venue"].isin(venues)]
    return filtered.reset_index(drop=True)


def filtered_articles() -> tuple[str, pd.DataFrame]:
    """Return the best available article layer after global sidebar filters."""
    layer, df = articles()
    if df.empty:
        return layer, df
    year_range = st.session_state.get("global_year_range")
    sources = tuple(st.session_state.get("global_sources", ()))
    venues = tuple(st.session_state.get("global_venues", ()))
    return layer, filter_articles(df, year_range, sources, venues)


@st.cache_data(ttl=60, hash_funcs={pd.DataFrame: _dataframe_cache_key})
def filter_chunks(chunks_df: pd.DataFrame, dois: tuple[str, ...]) -> pd.DataFrame:
    """Keep RAG chunks belonging to the currently filtered article set."""
    if chunks_df.empty or "doi" not in chunks_df.columns or not dois:
        return chunks_df.iloc[0:0].copy() if not dois else chunks_df.copy()
    return chunks_df[chunks_df["doi"].isin(dois)].reset_index(drop=True)


def filtered_chunks() -> pd.DataFrame:
    """Return chunks scoped to the globally filtered article DOI set."""
    chunks_df = chunks()
    _, article_df = filtered_articles()
    if article_df.empty or "doi" not in article_df.columns:
        return chunks_df.iloc[0:0].copy()
    dois = tuple(article_df["doi"].dropna().astype(str).unique())
    return filter_chunks(chunks_df, dois)


def require_articles() -> pd.DataFrame:
    """Return the articles frame, or render the empty state and stop the page."""
    _, all_articles = articles()
    if all_articles.empty:
        st.warning(
            "Nenhum dado encontrado nas camadas `lit_bronze`, `lit_silver` ou `lit_gold` ainda.\n\n"
            "Execute o pipeline (botões na barra lateral ou "
            "`uv run lake-literature --stage all`) e recarregue esta página."
        )
        st.stop()
    _, df = filtered_articles()
    if df.empty:
        st.warning(
            "Nenhum artigo corresponde aos filtros globais. "
            "Amplie o ano, a fonte ou o periódico na barra lateral."
        )
        st.stop()
    return df
