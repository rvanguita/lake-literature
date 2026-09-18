import pandas as pd

from lake_research_map.dashboard.qualis import match_venues_to_qualis


def _qualis_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "issn": "0142-0615",
                "titulo": "INTERNATIONAL JOURNAL OF ELECTRICAL POWER & ENERGY SYSTEMS",
                "estrato": "A1",
            },
            {
                "issn": "0378-7796",
                "titulo": "ELECTRIC POWER SYSTEMS RESEARCH (PRINT)",
                "estrato": "A2",
            },
            {"issn": "0960-1481", "titulo": "RENEWABLE ENERGY", "estrato": "A1"},
        ]
    )


def test_match_venues_to_qualis_exact_match():
    result = match_venues_to_qualis(["Renewable Energy"], _qualis_df()).set_index("venue")
    assert result.loc["Renewable Energy", "estrato"] == "A1"
    assert result.loc["Renewable Energy", "score"] == 100.0


def test_match_venues_to_qualis_handles_ampersand_and_suffix_variants():
    result = match_venues_to_qualis(
        [
            "International Journal of Electrical Power and Energy Systems",
            "Electric Power Systems Research",
        ],
        _qualis_df(),
    ).set_index("venue")

    assert (
        result.loc["International Journal of Electrical Power and Energy Systems", "estrato"]
        == "A1"
    )
    assert result.loc["Electric Power Systems Research", "estrato"] == "A2"


def test_match_venues_to_qualis_unmatched_venue_is_not_a_guess():
    result = match_venues_to_qualis(["Journal of Completely Unrelated Topic"], _qualis_df())
    row = result.iloc[0]
    assert row["estrato"] is None
    assert row["matched_title"] is None


def test_match_venues_to_qualis_empty_reference_returns_unclassified():
    empty_ref = pd.DataFrame(columns=["titulo", "estrato"])
    result = match_venues_to_qualis(["Renewable Energy"], empty_ref)
    assert result.iloc[0]["estrato"] is None
