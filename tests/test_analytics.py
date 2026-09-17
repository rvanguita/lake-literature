import pandas as pd

from lake_literature.dashboard.analytics import (
    OTHERS_LABEL,
    cumulative_by_category,
    cumulative_by_venue,
)


def _category_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"category": "A1", "year": 2020},
            {"category": "A1", "year": 2021},
            {"category": "A2", "year": 2021},
            {"category": "C", "year": 2022},
        ]
    )


def test_cumulative_by_category_buckets_and_cumsums():
    result = cumulative_by_category(_category_df(), "category", top_n=10)

    a1 = result[result["category"] == "A1"].set_index("year")["cumulative"]
    assert list(a1.reindex([2020, 2021, 2022], fill_value=a1.max())) == [1, 2, 2]

    a2 = result[result["category"] == "A2"].set_index("year")["cumulative"]
    assert a2.loc[2022] == 1


def test_cumulative_by_category_buckets_tail_into_others():
    result = cumulative_by_category(_category_df(), "category", top_n=1)
    # Only the most frequent category ("A1", 2 rows) keeps its own name; the
    # rest collapse into the catch-all bucket.
    assert set(result["category"]) == {"A1", OTHERS_LABEL}


def test_cumulative_by_category_empty_when_no_valid_years():
    empty = pd.DataFrame({"category": ["A1"], "year": [None]})
    assert cumulative_by_category(empty, "category").empty


def test_cumulative_by_venue_is_a_thin_wrapper():
    df = pd.DataFrame(
        [
            {"venue": "Journal A", "year": 2020},
            {"venue": "Journal A", "year": 2021},
        ]
    )
    result = cumulative_by_venue(df, top_n=10)
    assert "venue" in result.columns
    assert list(result.set_index("year")["cumulative"]) == [1, 2]
