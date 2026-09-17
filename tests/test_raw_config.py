"""Tests for the provenance parser (ingest/raw_config.py).

CLAUDE.md is explicit that config.csv is free text, not a table: these regexes
are the only thing turning it into queryable provenance, and a silent miss
shows up as an empty field on the "Configuração da Busca" page rather than as
an error.
"""

from __future__ import annotations

from lake_literature.ingest.raw_config import _parse_config_text

_IEEE_CONFIG = """Busca realizada no IEEE Xplore
"distribution system planning" OR "distribution network planning"
Filtros: apenas journals, texto completo
year 2015-2026
https://ieeexplore.ieee.org/search/searchresult.jsp?queryText=distribution
"""


def test_extracts_query_year_range_and_url():
    parsed = _parse_config_text(_IEEE_CONFIG)

    assert parsed["query_string"].startswith('"distribution system planning"')
    assert parsed["year_range"] == "2015-2026"
    assert parsed["search_url"].startswith("https://ieeexplore.ieee.org/search")


def test_remaining_lines_become_the_filters_field():
    parsed = _parse_config_text(_IEEE_CONFIG)

    # The query, year and URL lines are consumed by their own fields; what's
    # left is kept as free-text provenance rather than discarded.
    assert "Filtros: apenas journals" in parsed["filters"]
    assert "year 2015-2026" not in parsed["filters"]
    assert "https://" not in parsed["filters"]


def test_missing_pieces_are_none_rather_than_an_error():
    parsed = _parse_config_text("Apenas uma anotação solta, sem consulta nem URL.\n")

    assert parsed["query_string"] is None
    assert parsed["year_range"] is None
    assert parsed["search_url"] is None
    assert parsed["filters"] == "Apenas uma anotação solta, sem consulta nem URL."


def test_empty_text_yields_all_none():
    assert _parse_config_text("") == {
        "query_string": None,
        "filters": None,
        "year_range": None,
        "search_url": None,
    }
