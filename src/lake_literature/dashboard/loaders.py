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

from lake_literature.dashboard import qualis
from lake_literature.dashboard.data import (
    bronze_doi_dropped_counts,
    layer_row_counts,
    load_articles_all_layers,
    load_chunk_search_data,
    load_chunks,
    load_duplicate_pairs,
    load_search_configs,
    load_semantics,
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


def filter_signature() -> tuple:
    """Cheap, stable key for the current global filter state.

    Page-level `@st.cache_data` helpers that derive from `filtered_articles()`
    take this as their argument instead of the frame itself: hashing three
    small tuples costs nothing, while hashing the frame meant serializing it
    (~3.5MB, ~20ms) on every cache *lookup*, several times per rerun.
    """
    return (
        st.session_state.get("global_year_range"),
        tuple(st.session_state.get("global_sources", ())),
        tuple(st.session_state.get("global_venues", ())),
        st.session_state.get("global_min_margin"),
    )


@st.cache_data(ttl=60)
def row_counts() -> pd.DataFrame:
    return layer_row_counts()


@st.cache_data(ttl=60)
def chunks() -> pd.DataFrame:
    return load_chunks()


@st.cache_data(ttl=60)
def chunk_search_data() -> pd.DataFrame:
    """Full chunk rows (`text` + `embedding`) for the on-demand search box in
    `pages/quality.py` -- callers should only invoke this once a query is
    actually submitted, not on a plain page render (see `data.load_chunk_search_data`).
    """
    return load_chunk_search_data()


@st.cache_data(ttl=60)
def search_configs() -> pd.DataFrame:
    return load_search_configs()


@st.cache_data(ttl=60)
def semantics() -> pd.DataFrame:
    """Per-article semantic signals, keyed by DOI.

    Lives in gold while the rest of the dashboard usually reads silver (see
    `pick_best_articles_layer`), so callers join it on `doi` rather than
    expecting it as a column of the active layer.
    """
    return load_semantics()


@st.cache_data(ttl=60)
def duplicate_pairs() -> pd.DataFrame:
    return load_duplicate_pairs()


def with_semantics(df: pd.DataFrame) -> pd.DataFrame:
    """Left-join the semantic signals onto an article frame, by DOI.

    Returns `df` untouched when the `semantic` stage has never run, so every
    page keeps working on a database that only has the older stages.
    """
    signals = semantics()
    if df.empty or signals.empty or "doi" not in df.columns:
        return df
    columns = ["doi", "relevance_score", "theme_id", "theme_label", "map_x", "map_y"]
    if "offtopic_score" in signals.columns:
        columns.append("offtopic_score")
    merged = df.merge(signals[columns], on="doi", how="left")
    if "offtopic_score" in merged.columns:
        # The screening signal, derived once here so no page repeats the
        # subtraction: how much closer an abstract sits to the review's topic
        # than to the logistics reading of the same query. Zero is the
        # meaningful threshold -- see transform/semantics.py.
        merged["relevance_margin"] = merged["relevance_score"] - merged["offtopic_score"]
    return merged


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

        bronze_n = (
            int((bronze_df["source"] == source).sum()) if "source" in bronze_df.columns else 0
        )
        silver_n = (
            int(silver_df["sources"].apply(lambda s, source=source: source in s).sum())
            if "sources" in silver_df.columns
            else 0
        )
        gold_n = (
            int(gold_df["sources"].apply(lambda s, source=source: source in s).sum())
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


@st.cache_data(ttl=60)
def filter_articles(
    year_range: tuple[int, int] | None = None,
    sources: tuple[str, ...] = (),
    venues: tuple[str, ...] = (),
    min_margin: float | None = None,
) -> pd.DataFrame:
    """Apply the dashboard-wide filters to the best article layer.

    The filter is cached separately from the database read so changing a
    widget never causes another MySQL round-trip. Empty source/venue tuples
    mean "all", which also keeps the state valid when a partial layer lacks a
    column. The source frame is read from `articles()` (itself cached) rather
    than taken as an argument, so the cache key stays a few small values
    instead of a serialized copy of the whole frame.

    `min_margin` drops articles that sit closer to the logistics reading of
    "distribution system planning" than to the review's own topic -- the
    contrastive margin from `transform/semantics.py`, where 0 is the natural
    cut. Articles with no score yet are always kept: a missing signal must
    never silently shrink the corpus.
    """
    _, df = articles()
    if df.empty:
        return df
    if min_margin is not None:
        scored = with_semantics(df)
        # `relevance_margin` needs `offtopic_score`, which a database whose
        # last `semantic` run predates the contrastive anchor doesn't have.
        column = "relevance_margin" if "relevance_margin" in scored.columns else "relevance_score"
        if column in scored.columns:
            df = scored[scored[column].isna() | scored[column].ge(min_margin)]
    filtered = df.copy()
    if year_range and "year" in filtered.columns:
        if isinstance(year_range, (int, float)):
            year_range = (int(year_range), int(year_range))
        years = pd.to_numeric(filtered["year"], errors="coerce")
        filtered = filtered.loc[years.ge(year_range[0]) & years.le(year_range[1])]
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
    return layer, filter_articles(*filter_signature())


@st.cache_data(ttl=60)
def filter_chunks(dois: tuple[str, ...]) -> pd.DataFrame:
    """Keep RAG chunks belonging to the currently filtered article set."""
    chunks_df = chunks()
    if chunks_df.empty or "doi" not in chunks_df.columns or not dois:
        return chunks_df.iloc[0:0].copy() if not dois else chunks_df.copy()
    return chunks_df[chunks_df["doi"].isin(dois)].reset_index(drop=True)


def filtered_chunks() -> pd.DataFrame:
    """Return chunks scoped to the globally filtered article DOI set."""
    _, article_df = filtered_articles()
    if article_df.empty or "doi" not in article_df.columns:
        return chunks().iloc[0:0].copy()
    dois = tuple(article_df["doi"].dropna().astype(str).unique())
    return filter_chunks(dois)


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


@st.cache_data(ttl=None)
def _qualis_reference() -> pd.DataFrame:
    """Cached wrapper over `qualis.load_qualis_reference()`.

    Parsing the national CAPES xlsx (171k rows across every evaluation area,
    filtered down to ENGENHARIAS IV) takes ~9s via openpyxl; without this it
    reran on every `venue_qualis_map` cache miss, since that cache is keyed
    by the venues tuple rather than by this file.
    """
    return qualis.load_qualis_reference()


@st.cache_data(ttl=None)
def venue_qualis_map(venues: tuple[str, ...]) -> pd.DataFrame:
    """CAPES/Qualis (ENGENHARIAS IV) classification for each of `venues`.

    Cached indefinitely (the reference file doesn't change during a session) --
    see `dashboard.qualis` for the fuzzy-matching rationale. Prefer
    `all_venue_qualis_map()` from page code: matching against the full corpus
    once means toggling a global filter never re-triggers rapidfuzz matching.
    """
    return qualis.match_venues_to_qualis(list(venues), _qualis_reference())


@st.cache_data(ttl=60)
def all_venue_qualis_map() -> pd.DataFrame:
    """CAPES/Qualis classification for every venue in the (unfiltered) best
    article layer.

    Matching against the full corpus's venues once, rather than whatever
    subset survives the current global filters, means switching a
    year/source/venue filter never re-triggers `venue_qualis_map`'s fuzzy
    matching -- callers should filter the result by venue membership locally
    instead of calling `venue_qualis_map` with a filtered venue tuple.
    """
    _, df = articles()
    if df.empty or "venue" not in df.columns:
        return pd.DataFrame(columns=["venue", "matched_title", "estrato", "score"])
    venues = tuple(sorted(df["venue"].dropna().unique()))
    return venue_qualis_map(venues)
