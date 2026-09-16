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

import numpy as np
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


_MATRIX_SUMMARY_COLS = ("total", "ieee_total", "elsevier_total")


def author_year_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """One row per canonical author, one column per valid year, plus source totals.

    Explodes `authors`, folds names via `canonical_author` (see its docstring
    for the "initial surname" identity-merge caveat -- any page showing this
    table must disclose it), and counts distinct articles per author per year
    via `doi` where available (falls back to row count otherwise, since two
    exploded rows for the same article/author pair would otherwise double-count
    a co-authored paper). Sorted descending by `total` per the page's "highest
    to lowest" requirement. Years outside `valid_years`' plausible window are
    dropped before pivoting, same as every other year-based aggregation here.

    `ieee_total`/`elsevier_total` break `total` down by source (0 when a
    `source` column isn't present), using the same distinct-DOI counting rule
    as the year columns -- the "3 real series" convention this dashboard uses
    everywhere else (see `source_counts_by`).
    """
    exploded = explode_authors(df)
    if exploded.empty:
        return pd.DataFrame(columns=["author", *_MATRIX_SUMMARY_COLS])

    exploded["author_key"] = exploded["author"].apply(canonical_author)
    exploded = exploded[exploded["author_key"] != ""]
    exploded["year"] = valid_years(exploded)
    exploded = exploded.dropna(subset=["year"]).astype({"year": int})
    if exploded.empty:
        return pd.DataFrame(columns=["author", *_MATRIX_SUMMARY_COLS])

    display_names = exploded.groupby("author_key")["author"].apply(author_display_name)
    exploded["author_display"] = exploded["author_key"].map(display_names)

    count_col = "doi" if "doi" in exploded.columns else "author"
    agg = "nunique" if count_col == "doi" else "size"
    pivot = (
        exploded.groupby(["author_display", "year"])[count_col]
        .agg(agg)
        .unstack(fill_value=0)
        .astype(int)
    )
    pivot.columns = [str(int(c)) for c in pivot.columns]
    pivot["total"] = pivot.sum(axis=1)

    if "source" in exploded.columns:
        src_pivot = (
            exploded.groupby(["author_display", "source"])[count_col].agg(agg).unstack(fill_value=0)
        )
        for src in ("ieee", "elsevier"):
            if src not in src_pivot.columns:
                src_pivot[src] = 0
        pivot["ieee_total"] = src_pivot["ieee"].reindex(pivot.index, fill_value=0).astype(int)
        pivot["elsevier_total"] = (
            src_pivot["elsevier"].reindex(pivot.index, fill_value=0).astype(int)
        )
    else:
        pivot["ieee_total"] = 0
        pivot["elsevier_total"] = 0

    pivot = pivot.sort_values("total", ascending=False)
    pivot.index.name = "author"
    year_cols = sorted((c for c in pivot.columns if c not in _MATRIX_SUMMARY_COLS), key=int)
    return pivot.reset_index()[["author", *_MATRIX_SUMMARY_COLS, *year_cols]]


def _exploded_author_years(df: pd.DataFrame) -> pd.DataFrame:
    """Shared prep for author-by-year aggregations: explode, canonicalize, valid years only."""
    exploded = explode_authors(df)
    if exploded.empty:
        return exploded
    exploded["author_key"] = exploded["author"].apply(canonical_author)
    exploded = exploded[exploded["author_key"] != ""]
    exploded["year"] = valid_years(exploded)
    return exploded.dropna(subset=["year"]).astype({"year": int})


def researchers_by_year(df: pd.DataFrame) -> pd.DataFrame:
    """Distinct canonical-author count per year, split ieee/elsevier/total.

    Unlike `source_counts_by` (which counts rows), `total` here is counted
    independently as the number of distinct authors active that year
    regardless of source -- an author publishing in both IEEE and Elsevier
    the same year must count once in `total`, not twice. `ieee`/`elsevier`
    default to 0 when a `source` column isn't present.
    """
    exploded = _exploded_author_years(df)
    if exploded.empty:
        return pd.DataFrame(columns=["year", "ieee", "elsevier", "total"])

    years = sorted(exploded["year"].unique())
    result = pd.DataFrame({"year": years})
    has_source = "source" in exploded.columns
    for src in ("ieee", "elsevier"):
        if has_source:
            counts = exploded[exploded["source"] == src].groupby("year")["author_key"].nunique()
            result[src] = result["year"].map(counts).fillna(0).astype(int)
        else:
            result[src] = 0
    total_counts = exploded.groupby("year")["author_key"].nunique()
    result["total"] = result["year"].map(total_counts).fillna(0).astype(int)
    return result


def cumulative_researchers(df: pd.DataFrame) -> pd.DataFrame:
    """Cumulative count of distinct researchers introduced by each year.

    Each canonical author is counted once, in the year of their earliest
    valid-year appearance (within that source, for `ieee`/`elsevier`; across
    all sources, for `total`) -- summing each year's *active* researcher
    count would double-count an author active across multiple years, which
    isn't what a cumulative researcher count should mean. As with every other
    ieee/elsevier/total triple here, `total` isn't required to equal
    `ieee + elsevier` -- an author's first IEEE year and first Elsevier year
    can differ from their first-ever appearance.
    """
    exploded = _exploded_author_years(df)
    if exploded.empty:
        return pd.DataFrame(columns=["year", "ieee", "elsevier", "total"])

    years = sorted(exploded["year"].unique())

    def cumulative_new(sub: pd.DataFrame) -> pd.Series:
        if sub.empty:
            return pd.Series(0, index=years, dtype="int64")
        first_year = sub.groupby("author_key")["year"].min()
        by_year = first_year.value_counts().reindex(years, fill_value=0)
        return by_year.cumsum()

    result = pd.DataFrame({"year": years})
    has_source = "source" in exploded.columns
    for src in ("ieee", "elsevier"):
        sub = exploded[exploded["source"] == src] if has_source else exploded.iloc[0:0]
        result[src] = cumulative_new(sub).to_numpy()
    result["total"] = cumulative_new(exploded).to_numpy()
    return result


def gini_coefficient(values: pd.Series) -> float:
    """Gini coefficient of a distribution of non-negative values (0..1).

    0 = every author has the same output; close to 1 = output is concentrated
    in very few authors. Standard mean-absolute-difference formulation, no
    external stats dependency needed. Returns 0.0 for fewer than 2 authors or
    an all-zero series (nothing to be unequal about).
    """
    arr = pd.to_numeric(pd.Series(values), errors="coerce").dropna().to_numpy(dtype="float64")
    arr = arr[arr >= 0]
    n = arr.size
    if n < 2 or arr.sum() == 0:
        return 0.0
    sorted_arr = pd.Series(arr).sort_values().to_numpy()
    index = pd.Series(range(1, n + 1)).to_numpy(dtype="float64")
    return float((2 * (index * sorted_arr).sum() / (n * sorted_arr.sum())) - (n + 1) / n)


def lorenz_curve(values: pd.Series) -> pd.DataFrame:
    """Cumulative share of output vs. cumulative share of authors, sorted ascending.

    Includes the (0, 0) origin point. `charts.lorenz_chart` plots this against
    the perfect-equality diagonal as a second real trace (never a reference
    line, per the chart contract).
    """
    arr = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    arr = arr[arr >= 0].sort_values().to_numpy(dtype="float64")
    n = arr.size
    if n == 0 or arr.sum() == 0:
        return pd.DataFrame({"share_of_authors": [0.0], "share_of_output": [0.0]})

    cum_output = arr.cumsum() / arr.sum()
    cum_authors = (pd.Series(range(1, n + 1)) / n).to_numpy()
    return pd.DataFrame(
        {
            "share_of_authors": [0.0, *cum_authors.tolist()],
            "share_of_output": [0.0, *cum_output.tolist()],
        }
    )


def author_productivity_trend(matrix: pd.DataFrame, top_n: int) -> pd.DataFrame:
    """Linear-trend classification of yearly output for the top `top_n` authors.

    Fits `count ~ year` with `numpy.polyfit` (degree 1) per author, over that
    author's own active years only (a career that ended in 2015 shouldn't be
    scored against years it has no data for). Classifies the slope as
    "crescendo" / "estável" / "caindo" against a small fixed threshold (0.15
    articles/year) rather than a significance test -- most authors here have
    under 15 active years, too short a series for a p-value to be meaningful
    (the same reasoning `forecasting.py` uses to prefer plain regression over
    a heavier model). Sorted descending by `total`, matching the main table.
    """
    columns = [
        "author",
        "total",
        "first_year",
        "last_year",
        "active_years",
        "slope",
        "trend",
    ]
    if matrix.empty:
        return pd.DataFrame(columns=columns)

    year_cols = [c for c in matrix.columns if c not in ("author", *_MATRIX_SUMMARY_COLS)]
    top = matrix.sort_values("total", ascending=False).head(top_n)

    rows = []
    for _, row in top.iterrows():
        active = [(int(y), row[y]) for y in year_cols if row[y] > 0]
        if len(active) < 2:
            first_year = active[0][0] if active else None
            rows.append(
                {
                    "author": row["author"],
                    "total": int(row["total"]),
                    "first_year": first_year,
                    "last_year": first_year,
                    "active_years": len(active),
                    "slope": 0.0,
                    "trend": "dados insuficientes",
                }
            )
            continue
        years = [y for y, _ in active]
        counts = [c for _, c in active]
        slope = float(_linear_slope(years, counts))
        if slope > 0.15:
            trend = "crescendo"
        elif slope < -0.15:
            trend = "caindo"
        else:
            trend = "estável"
        rows.append(
            {
                "author": row["author"],
                "total": int(row["total"]),
                "first_year": min(years),
                "last_year": max(years),
                "active_years": len(active),
                "slope": round(slope, 3),
                "trend": trend,
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values("total", ascending=False)


def _linear_slope(x: list[int], y: list[int]) -> float:
    """`numpy.polyfit` degree-1 slope, isolated for testability."""
    coeffs = np.polyfit(x, y, 1)
    return float(coeffs[0])


def output_impact_correlation(
    author_rows: pd.DataFrame, impact_col: str = "citation_count"
) -> dict[str, float | int | None]:
    """Pearson and Spearman correlation between an author's total output and
    their mean `impact_col`, plus the sample size actually used.

    Rows with a null `impact_col` are dropped before averaging -- per this
    corpus's documented data pitfall, null means "not collected", not zero
    impact, and must not be averaged in as 0. Returns `None`s when fewer than
    3 authors have usable data (a correlation over 1-2 points is noise).
    """
    result: dict[str, float | int | None] = {"pearson": None, "spearman": None, "n": 0}
    if impact_col not in author_rows.columns or "author_display" not in author_rows.columns:
        return result

    by_author = author_rows.groupby("author_display").agg(
        articles=("author_display", "size"), mean_impact=(impact_col, "mean")
    )
    by_author = by_author.dropna(subset=["mean_impact"])
    result["n"] = int(len(by_author))
    if len(by_author) < 3:
        return result

    result["pearson"] = float(
        by_author["articles"].corr(by_author["mean_impact"], method="pearson")
    )
    result["spearman"] = float(
        by_author["articles"].corr(by_author["mean_impact"], method="spearman")
    )
    return result


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
