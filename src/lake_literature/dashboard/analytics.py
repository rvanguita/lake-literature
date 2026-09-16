"""Pure pandas aggregations shared by every dashboard page.

No `streamlit` import here on purpose -- these functions are plain data
transforms and can be exercised/cached independently of the UI layer. Pages
call these instead of open-coding a `groupby`/`explode`, so the same year
window, the same "count by source" shape, and the same author-name
normalization are used everywhere.
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

OTHERS_LABEL = "Outros"

# Shared "recent activity" window used by both the Visão Geral and
# Pesquisadores pages, so "recent" means the same thing (last 5 publication
# years, inclusive of the latest) everywhere it's shown.
RECENT_WINDOW_YEARS = 5


def valid_years(df: pd.DataFrame, lo: int = 1950, hi: int = 2026) -> pd.Series:
    """Coerce `year` to numeric and drop rows outside a plausible window.

    The corpus spans 1926-2027 (in-press records included), but a handful of
    very old or future-dated rows would otherwise dominate any rate/trend
    calculation. Returns a Series aligned to `df`'s index (NaN where invalid),
    matching `pd.to_numeric(..., errors="coerce")` semantics -- callers that
    need only valid rows should `.dropna()` the result themselves.
    """
    years = pd.to_numeric(df.get("year"), errors="coerce")
    return years.where(years.between(lo, hi))


def source_counts_by(df: pd.DataFrame, index_col: str) -> pd.DataFrame:
    """Count rows per `index_col`, broken into ieee / elsevier / total columns.

    This is the "3 real series" shape every source-comparison chart in the
    refactored dashboard consumes -- replacing the dotted reference lines
    that used to carry the Total dimension.
    """
    if df.empty or index_col not in df.columns:
        return pd.DataFrame(columns=[index_col, "ieee", "elsevier", "total"])

    has_source = "source" in df.columns
    if has_source:
        pivot = df.groupby([index_col, "source"]).size().unstack(fill_value=0)
        for src in ("ieee", "elsevier"):
            if src not in pivot.columns:
                pivot[src] = 0
        pivot = pivot[["ieee", "elsevier"]]
    else:
        pivot = pd.DataFrame(index=df[index_col].dropna().unique())
        pivot["ieee"] = 0
        pivot["elsevier"] = 0

    pivot["total"] = df.groupby(index_col).size().reindex(pivot.index, fill_value=0)
    return pivot.reset_index().rename(columns={"index": index_col})


def cumulative_by_source(df: pd.DataFrame) -> pd.DataFrame:
    """Cumulative article count per year, split ieee / elsevier / total."""
    working = df.copy()
    working["year"] = valid_years(working)
    working = working.dropna(subset=["year"])
    if working.empty:
        return pd.DataFrame(columns=["year", "ieee", "elsevier", "total"])
    working["year"] = working["year"].astype(int)

    counts = source_counts_by(working, "year").sort_values("year")
    for col in ("ieee", "elsevier", "total"):
        counts[col] = counts[col].cumsum()
    return counts.reset_index(drop=True)


def cumulative_by_venue(df: pd.DataFrame, top_n: int = 10, scope: str = "total") -> pd.DataFrame:
    """Cumulative publications per year for the top venues (+ an Outros bucket).

    `scope` restricts the underlying rows to "ieee", "elsevier", or "total"
    (all rows) before ranking venues and accumulating -- lets one chart answer
    "top venues overall" vs. "top venues within IEEE" without recomputing.
    """
    working = df.copy()
    if scope in ("ieee", "elsevier") and "source" in working.columns:
        working = working[working["source"] == scope]
    working["year"] = valid_years(working)
    working = working.dropna(subset=["year", "venue"])
    if working.empty:
        return pd.DataFrame(columns=["year", "venue", "cumulative"])
    working["year"] = working["year"].astype(int)

    top_venues = working["venue"].value_counts().head(top_n).index.tolist()
    working["venue_bucket"] = working["venue"].where(
        working["venue"].isin(top_venues), OTHERS_LABEL
    )

    by_year_venue = working.groupby(["year", "venue_bucket"]).size().rename("count").reset_index()
    years = sorted(by_year_venue["year"].unique())
    venues = list(by_year_venue["venue_bucket"].unique())
    full_index = pd.MultiIndex.from_product([years, venues], names=["year", "venue_bucket"])
    filled = (
        by_year_venue.set_index(["year", "venue_bucket"])["count"]
        .reindex(full_index, fill_value=0)
        .reset_index()
    )
    filled["cumulative"] = filled.groupby("venue_bucket")["count"].cumsum()
    return filled.rename(columns={"venue_bucket": "venue"})


def source_means(df: pd.DataFrame, col: str) -> dict[str, float | None]:
    """Mean of `col` for ieee / elsevier / total, or None where unavailable.

    Replaces the `ieee_sub = df[df["source"] == "ieee"]; ... .mean()` pattern
    that used to feed the removed reference-line helper.
    """
    result: dict[str, float | None] = {"ieee": None, "elsevier": None, "total": None}
    if df.empty or col not in df.columns:
        return result
    if "source" in df.columns:
        for src in ("ieee", "elsevier"):
            sub = df[df["source"] == src]
            if not sub.empty:
                val = sub[col].mean()
                result[src] = float(val) if val == val else None
    total_val = df[col].mean()
    result["total"] = float(total_val) if total_val == total_val else None
    return result


def author_count_series(df: pd.DataFrame) -> pd.Series:
    """Authors per row, from the `authors` list column.

    A list counts by its length; a non-null non-list scalar (a defensive
    fallback for a stray single-author value that never got wrapped in a
    list) counts as 1; null counts as 0. Shared by every page that needs an
    "authors per article" distribution or mean, so this edge case is handled
    the same way everywhere instead of drifting between pages.
    """
    if "authors" not in df.columns:
        return pd.Series(0, index=df.index, dtype="int64")
    return df["authors"].apply(
        lambda a: len(a) if isinstance(a, list) else (1 if pd.notna(a) else 0)
    )


def explode_authors(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (article, author), keeping year/source/citation_count/venue."""
    if df.empty or "authors" not in df.columns:
        return pd.DataFrame(columns=["author", "year", "source", "venue", "doi"])
    keep = [c for c in ("year", "source", "venue", "doi", "citation_count") if c in df.columns]
    working = df[["authors", *keep]].copy()
    working = working.explode("authors").rename(columns={"authors": "author"})
    working = working[working["author"].notna() & (working["author"].astype(str).str.strip() != "")]
    return working.reset_index(drop=True)


def explode_keywords(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (article, keyword), keeping year/source/venue/doi."""
    if df.empty or "keywords" not in df.columns:
        return pd.DataFrame(columns=["keyword", "year", "source", "venue", "doi"])
    keep = [c for c in ("year", "source", "venue", "doi") if c in df.columns]
    working = df[["keywords", *keep]].copy()
    working = working.explode("keywords").rename(columns={"keywords": "keyword"})
    working = working[
        working["keyword"].notna() & (working["keyword"].astype(str).str.strip() != "")
    ]
    working["keyword"] = working["keyword"].astype(str).str.strip().str.lower()
    return working.reset_index(drop=True)


_INITIAL_RE = re.compile(r"^[A-Za-z]\.?$")


def canonical_author(name: str) -> str:
    """Fold an author name to a rough identity key: "initial surname", lowercase.

    Handles the three formats present in the corpus: "M. Parvania" (IEEE
    CSV/bib), "Fernando Postigo" (Elsevier, full first name), and
    "Liu, Junyong" (IEEE bib, "Last, First"). This deliberately merges
    "Junyong Liu" and "J. Liu" into the same key -- a real simplification,
    not an identity match. Pages using this must say so: it can also merge
    distinct people who share an initial and surname.
    """
    if not name or not isinstance(name, str):
        return ""
    cleaned = name.strip().strip(".")
    if not cleaned:
        return ""

    if "," in cleaned:
        last, _, first = cleaned.partition(",")
        parts = [first.strip(), last.strip()]
    else:
        parts = cleaned.split()

    parts = [p for p in parts if p]
    if not parts:
        return ""
    if len(parts) == 1:
        surname = parts[0]
        initial = ""
    else:
        surname = parts[-1]
        first_token = parts[0]
        initial = first_token[0] if first_token else ""

    def strip_accents(text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text)
        return "".join(c for c in normalized if not unicodedata.combining(c))

    surname = strip_accents(surname).lower()
    initial = strip_accents(initial).lower()
    return f"{initial} {surname}".strip()


def author_display_name(names: pd.Series) -> str:
    """Pick the most informative spelling among variants that share a key."""
    if names.empty:
        return ""
    return max(names.unique(), key=len)


LAYER_ORDER = ("raw", "bronze", "silver", "gold")
LAYER_LABELS = {"raw": "Raw", "bronze": "Bronze", "silver": "Silver", "gold": "Gold"}


def layer_source_counts(
    bronze_df: pd.DataFrame, silver_df: pd.DataFrame, gold_df: pd.DataFrame
) -> pd.DataFrame:
    """IEEE / Elsevier / total article counts for bronze, silver, and gold.

    Bronze has a scalar `source`; silver/gold only carry a `sources` list --
    normalize both to the same ieee/elsevier/total shape so the funnel chart
    can compare layers directly.
    """
    rows = []
    for layer, frame, col in (
        ("bronze", bronze_df, "source"),
        ("silver", silver_df, "sources"),
        ("gold", gold_df, "sources"),
    ):
        if frame.empty:
            rows.append({"layer": layer, "ieee": 0, "elsevier": 0, "total": 0})
            continue
        if col == "source":
            ieee = int((frame["source"] == "ieee").sum())
            elsevier = int((frame["source"] == "elsevier").sum())
        else:
            src_lists = frame[col] if col in frame.columns else pd.Series([[]] * len(frame))
            ieee = int(src_lists.apply(lambda s: isinstance(s, list) and "ieee" in s).sum())
            elsevier = int(src_lists.apply(lambda s: isinstance(s, list) and "elsevier" in s).sum())
        rows.append({"layer": layer, "ieee": ieee, "elsevier": elsevier, "total": len(frame)})
    return pd.DataFrame(rows)
