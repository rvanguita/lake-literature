"""Per-article semantic signals derived from the abstract embeddings.

Runs as `--stage semantic`, after `embed` (which itself needs `gold`): it reads
`lit_chunks.embedding` and writes `lit_semantics` / `lit_duplicate_pairs`.
Re-running `gold` rebuilds the chunks, so this stage must be re-run after it.

Why this exists: the corpus was assembled from a search for "distribution
system planning", which is ambiguous -- it matches electric power distribution
*and* logistics/supply-chain distribution. Roughly a tenth of the corpus turned
out to be facility-location and cold-chain papers, plus book front matter
("Preface", "Index") ingested as if it were an article. Relevance screening is
a core step of a systematic literature review, so instead of hiding that, every
article gets a score and the dashboard lets a reviewer act on it.

The functions below take plain numpy arrays so they can be tested without a
database or the embedding model; `build_semantics` is the only part that does
I/O.
"""

from __future__ import annotations

import logging

import numpy as np
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from lake_literature.db.gold_models import Chunk, DuplicatePair, Semantics
from lake_literature.transform.embeddings import EMBED_MODEL_NAME

logger = logging.getLogger(__name__)

# What the review is actually about. Written as a descriptive passage rather
# than as the raw boolean search string: the chunks were embedded as passages,
# so a passage-shaped anchor sits in the same region of the space. Validated
# against the known off-topic cluster -- it ranks those papers at roughly the
# 9th-30th percentile while genuine distribution-planning papers land at the
# 98th+, ROC AUC 0.96.
ANCHOR_TEXT = (
    "Planning and expansion of electric power distribution systems: distribution network "
    "planning, distributed generation, feeders, substations, voltage, reliability and power "
    "quality in electrical energy distribution grids."
)

N_THEMES = 8
DUPLICATE_THRESHOLD = 0.95
THEME_LABEL_TERMS = 3
RANDOM_SEED = 0


def relevance_scores(matrix: np.ndarray, anchor: np.ndarray) -> np.ndarray:
    """Cosine similarity of each row of `matrix` to `anchor`.

    Both sides are L2-normalized first, so this is a plain dot product and the
    result is in [-1, 1] regardless of whether the caller pre-normalized.
    """
    if matrix.size == 0:
        return np.zeros(0, dtype="float32")
    normalized = matrix / np.linalg.norm(matrix, axis=1, keepdims=True)
    unit_anchor = anchor / np.linalg.norm(anchor)
    return (normalized @ unit_anchor).astype("float32")


def discover_themes(
    matrix: np.ndarray, texts: list[str], k: int = N_THEMES
) -> tuple[np.ndarray, dict[int, str]]:
    """Cluster `matrix` into `k` themes and name each from its distinctive terms.

    Returns `(labels, {theme_id: label})`. `k` is a fixed, human-inspected
    choice, not an optimized one: silhouette scores on same-domain text
    embeddings are uninformative (~0.02 here) because the clusters genuinely
    overlap, so the criterion is whether the labels read as real topics.

    Labels come from the terms a cluster over-uses *relative to the rest of the
    corpus*, not its highest raw TF-IDF terms -- otherwise every cluster in a
    distribution-planning corpus gets labelled "distribution, power, planning".
    """
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import TfidfVectorizer

    n_samples = len(matrix)
    k = max(1, min(k, n_samples))
    labels = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_SEED).fit_predict(matrix)

    try:
        vectorizer = TfidfVectorizer(
            max_features=6000, stop_words="english", ngram_range=(1, 2), min_df=2
        )
        tfidf = vectorizer.fit_transform(texts)
        terms = np.array(vectorizer.get_feature_names_out())
        corpus_mean = np.asarray(tfidf.mean(axis=0)).ravel()
    except ValueError:
        # Too few/too short documents for a vocabulary -- fall back to numbers.
        logger.debug("discover_themes: TF-IDF vocabulary empty", exc_info=True)
        return labels, {int(t): f"Tema {int(t) + 1}" for t in np.unique(labels)}

    theme_labels: dict[int, str] = {}
    for theme in np.unique(labels):
        member_mean = np.asarray(tfidf[labels == theme].mean(axis=0)).ravel()
        distinctive = terms[np.argsort(member_mean - corpus_mean)[::-1][:THEME_LABEL_TERMS]]
        theme_labels[int(theme)] = " · ".join(distinctive)
    return labels, theme_labels


def project_2d(matrix: np.ndarray) -> np.ndarray:
    """Project embeddings to 2D for the semantic map.

    t-SNE preserves local neighbourhoods, which is what makes the off-topic
    group read as a visually separate island. Coordinates are only comparable
    within one run.
    """
    from sklearn.manifold import TSNE

    n_samples = len(matrix)
    if n_samples < 3:
        return np.zeros((n_samples, 2), dtype="float32")
    # t-SNE requires perplexity < n_samples; 30 is its default.
    perplexity = min(30, max(2, (n_samples - 1) // 3))
    projection = TSNE(
        n_components=2, perplexity=perplexity, init="pca", random_state=RANDOM_SEED
    ).fit_transform(matrix)
    return projection.astype("float32")


def near_duplicate_pairs(
    matrix: np.ndarray, dois: list[str], threshold: float = DUPLICATE_THRESHOLD
) -> list[tuple[str, str, float]]:
    """Distinct-DOI pairs whose abstracts are near-identical.

    Returns `(doi_a, doi_b, similarity)` sorted by similarity, each unordered
    pair once. Only the upper triangle is scanned, so a row is never paired
    with itself.
    """
    if len(matrix) < 2:
        return []
    normalized = matrix / np.linalg.norm(matrix, axis=1, keepdims=True)
    similarity = normalized @ normalized.T
    rows, cols = np.triu_indices(len(matrix), k=1)
    hits = similarity[rows, cols] >= threshold
    pairs = [
        (dois[int(i)], dois[int(j)], float(similarity[int(i), int(j)]))
        for i, j in zip(rows[hits], cols[hits], strict=True)
        if dois[int(i)] != dois[int(j)]
    ]
    return sorted(pairs, key=lambda p: p[2], reverse=True)


def _embed_anchor(text: str) -> np.ndarray:
    # Imported lazily, like transform/embeddings.py does, so stages that never
    # touch the model don't pay fastembed's import cost.
    from fastembed import TextEmbedding

    model = TextEmbedding(model_name=EMBED_MODEL_NAME)
    return np.array(next(model.embed([text])), dtype="float32")


def build_semantics(gold_session: Session, anchor_text: str = ANCHOR_TEXT) -> dict:
    """Rebuild `lit_semantics` and `lit_duplicate_pairs` from the abstract chunks.

    One abstract chunk per article is the unit here: it exists for every gold
    article and is a self-contained summary, whereas fulltext chunks only exist
    for the minority of articles that have a PDF.
    """
    rows = gold_session.execute(
        select(Chunk.doi, Chunk.embedding, Chunk.text)
        .where(Chunk.chunk_type == "abstract")
        .where(Chunk.embedding.is_not(None))
        .order_by(Chunk.doi)
    ).all()

    # Coverage, not just presence: this stage used to run happily on whatever
    # subset happened to be embedded, so a `gold` rebuild followed by a partial
    # `embed` produced a full-looking `lit_semantics` derived from a fraction of
    # the corpus, with nothing saying so.
    total_abstracts = (
        gold_session.scalar(
            select(func.count()).select_from(Chunk).where(Chunk.chunk_type == "abstract")
        )
        or 0
    )
    coverage = len(rows) / total_abstracts if total_abstracts else 0.0

    if not rows:
        return {
            "articles": 0,
            "themes": 0,
            "duplicate_pairs": 0,
            "embedding_coverage": 0.0,
            "skipped": "no embeddings yet",
        }

    if coverage < 1.0:
        logger.warning(
            "build_semantics: only %d of %d abstract chunks are embedded (%.1f%%) -- "
            "the signals written here describe that subset only; run `--stage embed` first",
            len(rows),
            total_abstracts,
            coverage * 100,
        )

    dois = [r[0] for r in rows]
    matrix = np.array([r[1] for r in rows], dtype="float32")
    texts = [r[2] or "" for r in rows]

    scores = relevance_scores(matrix, _embed_anchor(anchor_text))
    labels, theme_labels = discover_themes(matrix, texts)
    coords = project_2d(matrix)
    pairs = near_duplicate_pairs(matrix, dois)

    gold_session.execute(delete(Semantics))
    gold_session.execute(delete(DuplicatePair))
    gold_session.add_all(
        [
            Semantics(
                doi=doi,
                relevance_score=float(scores[i]),
                theme_id=int(labels[i]),
                theme_label=theme_labels[int(labels[i])],
                map_x=float(coords[i][0]),
                map_y=float(coords[i][1]),
                embed_model=EMBED_MODEL_NAME,
            )
            for i, doi in enumerate(dois)
        ]
    )
    gold_session.add_all([DuplicatePair(doi_a=a, doi_b=b, similarity=s) for a, b, s in pairs])
    gold_session.commit()

    return {
        "articles": len(dois),
        "themes": len(theme_labels),
        "duplicate_pairs": len(pairs),
        "embedding_coverage": round(coverage, 4),
        "median_relevance": round(float(np.median(scores)), 4),
    }
