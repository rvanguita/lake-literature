import numpy as np
import pandas as pd

from lake_literature.dashboard.search import _rank_by_similarity


def _chunks_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"doi": "10.1/a", "text": "close match", "embedding": [1.0, 0.0, 0.0]},
            {"doi": "10.1/b", "text": "far match", "embedding": [0.0, 1.0, 0.0]},
            {"doi": "10.1/c", "text": "no embedding yet", "embedding": None},
        ]
    )


def test_rank_by_similarity_ranks_closest_vector_first():
    query = np.array([1.0, 0.0, 0.0])
    result = _rank_by_similarity(query, _chunks_df(), top_k=10)

    assert list(result["doi"]) == ["10.1/a", "10.1/b"]
    assert result.iloc[0]["score"] > result.iloc[1]["score"]


def test_rank_by_similarity_excludes_rows_without_embedding():
    query = np.array([1.0, 0.0, 0.0])
    result = _rank_by_similarity(query, _chunks_df(), top_k=10)

    assert "10.1/c" not in set(result["doi"])


def test_rank_by_similarity_respects_top_k():
    query = np.array([1.0, 0.0, 0.0])
    result = _rank_by_similarity(query, _chunks_df(), top_k=1)

    assert len(result) == 1
    assert result.iloc[0]["doi"] == "10.1/a"


def test_rank_by_similarity_no_embedded_rows_returns_empty():
    df = pd.DataFrame([{"doi": "10.1/c", "text": "no embedding yet", "embedding": None}])
    result = _rank_by_similarity(np.array([1.0, 0.0, 0.0]), df, top_k=10)
    assert result.empty


def test_rank_by_similarity_no_embedding_column_returns_empty():
    df = pd.DataFrame([{"doi": "10.1/c", "text": "no embedding column"}])
    result = _rank_by_similarity(np.array([1.0, 0.0, 0.0]), df, top_k=10)
    assert result.empty
