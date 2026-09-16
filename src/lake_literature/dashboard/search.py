"""Semantic search over `gold.chunks` using the embeddings the `embed` pipeline
stage already produced.

`_rank_by_similarity` is a pure function (no Streamlit, no model loading) so it
can be unit tested directly with a hand-built query vector -- see
`tests/test_search.py`. `semantic_search` wires it up to the real embedding
model, cached across Streamlit reruns with `st.cache_resource` so the ONNX
model is loaded once per process, not once per query.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st
from sklearn.metrics.pairwise import cosine_similarity

from lake_literature.transform.embeddings import EMBED_MODEL_NAME


def _rank_by_similarity(
    query_vector: np.ndarray, chunks_df: pd.DataFrame, top_k: int
) -> pd.DataFrame:
    """Rank `chunks_df` by cosine similarity of `embedding` to `query_vector`.

    Rows with a null `embedding` are excluded. Returns a copy of the top_k
    matching rows with an added `score` column, sorted descending. Empty
    input (no column, no embedded rows) returns an empty frame.
    """
    if "embedding" not in chunks_df.columns:
        return chunks_df.iloc[0:0].copy()

    embedded = chunks_df[chunks_df["embedding"].notna()]
    if embedded.empty:
        return embedded.copy()

    matrix = np.stack(embedded["embedding"].to_numpy())
    scores = cosine_similarity(query_vector.reshape(1, -1), matrix)[0]

    result = embedded.copy()
    result["score"] = scores
    return result.sort_values("score", ascending=False).head(top_k).reset_index(drop=True)


@st.cache_resource
def _get_embedding_model():
    # Imported here so pages that never call semantic_search don't pay
    # fastembed's import cost or trigger a model-file check.
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=EMBED_MODEL_NAME)


def semantic_search(query: str, chunks_df: pd.DataFrame, top_k: int = 10) -> pd.DataFrame:
    """Embed `query` with the same model used for `chunks.embedding` and rank
    `chunks_df` by cosine similarity. Returns an empty frame if no chunk in
    `chunks_df` has an embedding yet.
    """
    if "embedding" not in chunks_df.columns or not chunks_df["embedding"].notna().any():
        return chunks_df.iloc[0:0].copy()

    model = _get_embedding_model()
    query_vector = np.array(next(model.embed([query])))
    return _rank_by_similarity(query_vector, chunks_df, top_k)
