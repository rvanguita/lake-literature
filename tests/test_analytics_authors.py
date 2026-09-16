import pandas as pd

from lake_literature.dashboard.analytics import (
    author_productivity_trend,
    author_year_matrix,
    gini_coefficient,
    output_impact_correlation,
)


def _articles_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"authors": ["A. Silva"], "year": 2020, "doi": "10.1/1", "citation_count": 10},
            {"authors": ["A. Silva"], "year": 2021, "doi": "10.1/2", "citation_count": 12},
            {"authors": ["A. Silva"], "year": 2022, "doi": "10.1/3", "citation_count": 8},
            {"authors": ["B. Costa"], "year": 2020, "doi": "10.1/4", "citation_count": 1},
            {
                "authors": ["A. Silva", "B. Costa"],
                "year": 2022,
                "doi": "10.1/5",
                "citation_count": None,
            },
        ]
    )


def test_author_year_matrix_sorted_descending_by_total():
    matrix = author_year_matrix(_articles_df())

    assert matrix.iloc[0]["total"] >= matrix.iloc[1]["total"]
    # Silva: 2020, 2021, 2022, 2022 (coauthored) = 4 distinct DOIs.
    assert matrix.iloc[0]["total"] == 4
    # Costa: 2020, 2022 = 2 distinct DOIs.
    assert matrix.iloc[1]["total"] == 2


def test_author_year_matrix_year_columns_and_totals_consistent():
    matrix = author_year_matrix(_articles_df())
    year_cols = [
        c for c in matrix.columns if c not in ("author", "total", "ieee_total", "elsevier_total")
    ]

    assert year_cols == sorted(year_cols)
    for _, row in matrix.iterrows():
        assert row["total"] == sum(row[c] for c in year_cols)


def test_author_year_matrix_empty_when_no_authors():
    empty = pd.DataFrame({"year": [2020, 2021]})
    matrix = author_year_matrix(empty)
    assert matrix.empty


def test_author_year_matrix_splits_ieee_and_elsevier_totals():
    df = pd.DataFrame(
        [
            {"authors": ["J. Liu"], "year": 2020, "doi": "10.1/1", "source": "ieee"},
            {"authors": ["J. Liu"], "year": 2021, "doi": "10.1/2", "source": "ieee"},
            {"authors": ["Junyong Liu"], "year": 2022, "doi": "10.1/3", "source": "elsevier"},
            {"authors": ["B. Costa"], "year": 2020, "doi": "10.1/4", "source": "elsevier"},
        ]
    )
    matrix = author_year_matrix(df).set_index("author")

    # "J. Liu" (ieee) and "Junyong Liu" (elsevier) fold to the same canonical
    # author -- total must be the sum of both sources' contributions.
    liu = matrix.loc["Junyong Liu"]
    assert liu["ieee_total"] == 2
    assert liu["elsevier_total"] == 1
    assert liu["total"] == liu["ieee_total"] + liu["elsevier_total"] == 3

    costa = matrix.loc["B. Costa"]
    assert costa["ieee_total"] == 0
    assert costa["elsevier_total"] == 1
    assert costa["total"] == 1


def test_author_year_matrix_source_columns_default_to_zero_without_source():
    matrix = author_year_matrix(_articles_df())
    assert (matrix["ieee_total"] == 0).all()
    assert (matrix["elsevier_total"] == 0).all()


def test_gini_coefficient_perfect_equality_is_zero():
    assert gini_coefficient(pd.Series([5, 5, 5, 5])) == 0.0


def test_gini_coefficient_max_inequality_approaches_one():
    # One author has everything, the rest have nothing.
    gini = gini_coefficient(pd.Series([0, 0, 0, 100]))
    assert gini > 0.7


def test_gini_coefficient_handles_small_or_empty_input():
    assert gini_coefficient(pd.Series([])) == 0.0
    assert gini_coefficient(pd.Series([5])) == 0.0


def test_author_productivity_trend_classifies_growth_and_decline():
    matrix = pd.DataFrame(
        [
            {"author": "Growing", "total": 5, "2018": 0, "2019": 1, "2020": 2, "2021": 4},
            {"author": "Declining", "total": 5, "2018": 4, "2019": 2, "2020": 1, "2021": 0},
            {"author": "OnePoint", "total": 1, "2018": 0, "2019": 0, "2020": 0, "2021": 1},
        ]
    )
    trend = author_productivity_trend(matrix, top_n=10)
    by_author = trend.set_index("author")

    assert by_author.loc["Growing", "trend"] == "crescendo"
    assert by_author.loc["Declining", "trend"] == "caindo"
    assert by_author.loc["OnePoint", "trend"] == "dados insuficientes"
    # Sorted descending by total.
    assert list(trend["total"]) == sorted(trend["total"], reverse=True)


def test_output_impact_correlation_ignores_null_citation_rows():
    df = pd.DataFrame(
        [
            {"author_display": "A", "citation_count": 10},
            {"author_display": "A", "citation_count": 20},
            {"author_display": "B", "citation_count": None},
            {"author_display": "B", "citation_count": None},
            {"author_display": "C", "citation_count": 5},
            {"author_display": "C", "citation_count": 5},
        ]
    )
    result = output_impact_correlation(df, "citation_count")
    assert result["n"] >= 2
    assert result["pearson"] is None or -1.0 <= result["pearson"] <= 1.0


def test_output_impact_correlation_returns_none_below_minimum_sample():
    df = pd.DataFrame(
        [
            {"author_display": "A", "citation_count": 10},
            {"author_display": "B", "citation_count": 20},
        ]
    )
    result = output_impact_correlation(df, "citation_count")
    assert result["pearson"] is None
    assert result["spearman"] is None
