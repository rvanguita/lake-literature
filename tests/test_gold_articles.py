from lake_literature.db.silver_models import Article as SilverArticle
from lake_literature.transform.gold_articles import (
    CHUNK_MAX_CHARS,
    CHUNK_OVERLAP_CHARS,
    _build_abstract_text,
    _chunk_text,
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
