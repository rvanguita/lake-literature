from lake_literature.db.gold_models import Chunk
from lake_literature.db.silver_models import Article as SilverArticle
from lake_literature.transform.gold_articles import (
    CHUNK_MAX_CHARS,
    CHUNK_OVERLAP_CHARS,
    _build_abstract_text,
    _chunk_text,
    build_gold_articles,
)


def test_chunk_text_empty_returns_empty_list():
    assert _chunk_text("") == []
    assert _chunk_text("   ") == []


def test_chunk_text_short_text_is_a_single_chunk():
    text = "A short paragraph well under the chunking cap."
    assert _chunk_text(text) == [text]


def test_chunk_text_long_text_splits_into_multiple_overlapping_chunks():
    # Long enough to force at least two chunks, made of sentences so a
    # boundary break point exists near the target size.
    sentence = "This is a representative sentence about distribution planning. "
    text = sentence * 40  # well over CHUNK_MAX_CHARS
    chunks = _chunk_text(text, max_chars=200, overlap=50)

    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)
    # consecutive chunks overlap: the tail of one reappears near the head of the next
    assert chunks[1][:20] in text


def test_chunk_text_respects_default_constants():
    # sanity check the constants imported above are the ones actually used
    assert CHUNK_MAX_CHARS > CHUNK_OVERLAP_CHARS > 0


def _silver(**overrides) -> SilverArticle:
    fields = dict(
        doi="10.1109/example.1",
        sources=["ieee"],
        record_type="article",
        title="Example Title",
        authors=["Doe, John"],
        keywords=[],
        abstract=None,
    )
    fields.update(overrides)
    return SilverArticle(**fields)


def test_build_abstract_text_assembles_title_keywords_abstract_in_order():
    row = _silver(title="A Title", keywords=["grid", "planning"], abstract="An abstract.")
    text = _build_abstract_text(row)
    assert text.startswith("A Title")
    assert "Keywords: grid, planning" in text
    assert text.endswith("An abstract.")


def test_build_abstract_text_skips_missing_pieces():
    row = _silver(title="Only A Title", keywords=[], abstract=None)
    assert _build_abstract_text(row) == "Only A Title"


# ---------------------------------------------------------------------------
# Chunk reconciliation: an embedding costs a full `embed` stage to recompute,
# and losing one also orphans the `lit_semantics` row derived from it, so a
# `gold` rebuild must not throw vectors away for text that didn't change.
# ---------------------------------------------------------------------------


def _embed_everything(gold_session, vector=(0.1, 0.2, 0.3)):
    """Stand in for the `embed` stage without loading the real model."""
    for chunk in gold_session.query(Chunk).all():
        chunk.embedding = list(vector)
        chunk.embed_model = "test-model"
    gold_session.commit()


def test_build_gold_articles_preserves_embeddings_when_text_is_unchanged(
    silver_session, gold_session
):
    silver_session.add(_silver(doi="10.1109/example.1", abstract="An abstract."))
    silver_session.commit()

    build_gold_articles(silver_session, gold_session)
    _embed_everything(gold_session)

    stats = build_gold_articles(silver_session, gold_session)

    assert stats["chunks_unchanged"] == 1
    assert stats["chunks_invalidated"] == 0
    assert stats["chunks_new"] == 0
    assert stats["chunks_removed"] == 0
    assert stats["chunks_missing_embedding"] == 0

    chunk = gold_session.query(Chunk).one()
    assert chunk.embedding == [0.1, 0.2, 0.3]
    assert chunk.embed_model == "test-model"


def test_build_gold_articles_drops_the_vector_only_where_the_text_changed(
    silver_session, gold_session
):
    silver_session.add_all(
        [
            _silver(doi="10.1109/example.1", abstract="First abstract."),
            _silver(doi="10.1109/example.2", abstract="Second abstract."),
        ]
    )
    silver_session.commit()

    build_gold_articles(silver_session, gold_session)
    _embed_everything(gold_session)

    edited = silver_session.query(SilverArticle).filter_by(doi="10.1109/example.1").one()
    edited.abstract = "First abstract, revised."
    silver_session.commit()

    stats = build_gold_articles(silver_session, gold_session)

    assert stats["chunks_invalidated"] == 1
    assert stats["chunks_unchanged"] == 1
    assert stats["chunks_missing_embedding"] == 1

    revised = gold_session.query(Chunk).filter_by(doi="10.1109/example.1").one()
    untouched = gold_session.query(Chunk).filter_by(doi="10.1109/example.2").one()
    assert revised.embedding is None
    assert revised.embed_model is None
    assert "revised" in revised.text
    assert revised.char_len == len(revised.text)
    assert untouched.embedding == [0.1, 0.2, 0.3]


def test_build_gold_articles_removes_chunks_whose_article_is_gone(silver_session, gold_session):
    silver_session.add_all(
        [
            _silver(doi="10.1109/example.1", abstract="First abstract."),
            _silver(doi="10.1109/example.2", abstract="Second abstract."),
        ]
    )
    silver_session.commit()

    build_gold_articles(silver_session, gold_session)
    _embed_everything(gold_session)

    silver_session.query(SilverArticle).filter_by(doi="10.1109/example.2").delete()
    silver_session.commit()

    stats = build_gold_articles(silver_session, gold_session)

    assert stats["chunks_removed"] == 1
    assert stats["chunks_unchanged"] == 1
    assert [c.doi for c in gold_session.query(Chunk).all()] == ["10.1109/example.1"]
