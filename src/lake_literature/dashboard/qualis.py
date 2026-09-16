"""CAPES/Qualis journal-classification lookup for the corpus's venues.

The reference data (`config.CAPES_QUALIS_XLSX`) is the official CAPES export for the
2017-2020 quadriênio -- the last journal-level Qualis grading (CAPES moves to an
article-level evaluation for 2025-2028). A journal's stratum is evaluation-area
specific; this corpus is electric-power/distribution-planning, so it's matched
against `ENGENHARIAS IV` only -- a different área can grade the same journal
differently.

Venue strings in the corpus don't match the reference títulos exactly (e.g. this
corpus has "Renewable and Sustainable Energy Reviews", the reference has "RENEWABLE
& SUSTAINABLE ENERGY REVIEWS"; ScienceDirect/IEEE Xplore titles also carry "(Print)"/
"(Online)" suffixes the reference sometimes does and sometimes doesn't), so venues are
matched by fuzzy title similarity -- the same approach `transform.silver_articles`
already uses for PDF-to-title matching, reusing its `normalize_title`.
"""

from __future__ import annotations

import warnings

import pandas as pd
from rapidfuzz import fuzz, process

from lake_literature.config import CAPES_QUALIS_XLSX
from lake_literature.transform.silver_articles import normalize_title

QUALIS_AREA = "ENGENHARIAS IV"
MATCH_THRESHOLD = 85.0

NOT_CLASSIFIED = "Não classificado"

# Best to worst; unclassified always last. Shared by every chart/table that
# ranks or orders by classification, so "A1 first" only needs to be defined once.
ESTRATO_ORDER = ("A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4", "C", NOT_CLASSIFIED)


def load_qualis_reference(path=None) -> pd.DataFrame:
    """Read the official CAPES export, filtered to `QUALIS_AREA`.

    Returns columns `["issn", "titulo", "estrato"]`. Thin I/O wrapper over the
    xlsx file -- not unit tested, same as this project's other raw-file loaders.
    """
    xlsx_path = path or CAPES_QUALIS_XLSX
    with warnings.catch_warnings():
        # The source workbook has no explicit default cell style; openpyxl
        # substitutes its own and warns about it, but this never affects the
        # data actually read -- narrowly silenced so any other, genuinely
        # actionable warning from this call still surfaces.
        warnings.filterwarnings(
            "ignore",
            message="Workbook contains no default style, apply openpyxl's default",
            category=UserWarning,
        )
        df = pd.read_excel(xlsx_path, sheet_name="RelatorioQualis")
    df.columns = [c.strip() for c in df.columns]
    df["Área de Avaliação"] = df["Área de Avaliação"].astype(str).str.strip()
    df = df[df["Área de Avaliação"] == QUALIS_AREA]
    return df.rename(columns={"ISSN": "issn", "Título": "titulo", "Estrato": "estrato"})[
        ["issn", "titulo", "estrato"]
    ].reset_index(drop=True)


def match_venues_to_qualis(
    venues: list[str], qualis_df: pd.DataFrame, threshold: float = MATCH_THRESHOLD
) -> pd.DataFrame:
    """Fuzzy-match each distinct venue to a Qualis título, or leave it unclassified.

    Pure function (no file I/O) -- `qualis_df` must have a `titulo` column (as
    returned by `load_qualis_reference`) and, when matched, an `estrato` column.
    Returns one row per input venue: `["venue", "matched_title", "estrato", "score"]`.
    Below `threshold`, `matched_title`/`estrato` are `None` rather than a guessed
    grade -- an unmatched venue must read as "not classified," never as a wrong one.
    """
    choices = {idx: normalize_title(title) for idx, title in qualis_df["titulo"].items() if title}
    rows = []
    for venue in venues:
        normalized = normalize_title(venue)
        match = (
            process.extractOne(
                normalized, choices, scorer=fuzz.token_sort_ratio, score_cutoff=threshold
            )
            if normalized and choices
            else None
        )
        if match is None:
            rows.append({"venue": venue, "matched_title": None, "estrato": None, "score": None})
            continue
        _, score, ref_idx = match
        rows.append(
            {
                "venue": venue,
                "matched_title": qualis_df.loc[ref_idx, "titulo"],
                "estrato": qualis_df.loc[ref_idx, "estrato"],
                "score": score,
            }
        )
    return pd.DataFrame(rows, columns=["venue", "matched_title", "estrato", "score"])
