"""Unit tests for knowledge frontiers, disruption, Price's index, and open access analytics."""

import pandas as pd

from lake_literature.dashboard.analytics import (
    disruption_index_estimation,
    open_access_impact_analysis,
    price_index_analysis,
    sleeping_beauties_detection,
    technological_burst_detection,
)


def _sample_corpus_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id": 1,
                "doi": "10.1109/TPWRS.2015.001",
                "title": "Robust Optimization for Microgrid Islanding with BESS and Solar PV",
                "abstract": "We develop a two-stage robust optimization model for microgrids with battery storage.",
                "year": 2015,
                "citation_count": 120,
                "reference_count": 35,
                "authors": ["A. Padilha", "J. Liu", "D. Das"],
                "theme_label": "DG Optimization",
                "relevance_margin": 0.8,
                "license": "CC-BY",
                "document_type": "Journal Article",
                "venue": "IEEE Trans. Power Syst.",
            },
            {
                "id": 2,
                "doi": "10.1109/TPWRS.2023.002",
                "title": "Deep Learning and Vehicle-to-Grid Integration for Hosting Capacity",
                "abstract": "Deep reinforcement learning applied to v2g electric vehicles to expand hosting capacity.",
                "year": 2023,
                "citation_count": 28,
                "reference_count": 42,
                "authors": ["J. Liu", "X. Wang"],
                "theme_label": "Renewable & Storage",
                "relevance_margin": 1.2,
                "license": "CC BY-NC",
                "document_type": "Journal Article",
                "venue": "IEEE Trans. Smart Grid",
            },
            {
                "id": 3,
                "doi": "10.1016/j.ijepes.2010.003",
                "title": "Early Analytical Formulation of Convex SOCP Relaxation",
                "abstract": "Second-order cone programming formulation for distribution network loss minimization.",
                "year": 2010,
                "citation_count": 95,
                "reference_count": 18,
                "authors": ["M. Costa"],
                "theme_label": "Network Topology",
                "relevance_margin": 0.4,
                "license": None,
                "document_type": "Conference Paper",
                "venue": "Int. J. Electr. Power",
            },
            {
                "id": 4,
                "doi": "10.1109/TSG.2021.004",
                "title": "Peer-to-Peer Energy Trading and Blockchain in Active Distribution Networks",
                "abstract": "P2P transactive energy with smart meters and active distribution adn resilience.",
                "year": 2021,
                "citation_count": 45,
                "reference_count": 38,
                "authors": ["R. Silva", "T. Souza", "E. Santos", "F. Lima"],
                "theme_label": "Electricity Markets",
                "relevance_margin": 0.6,
                "license": "Closed",
                "document_type": "Journal Article",
                "venue": "IEEE Trans. Smart Grid",
            },
            {
                "id": 5,
                "doi": "10.1109/TPWRS.2008.005",
                "title": "Classical Radial Distribution Feeders Load Flow Algorithm",
                "abstract": "Backward forward sweep method on benchmark feeders without distributed energy.",
                "year": 2008,
                "citation_count": 60,
                "reference_count": 15,
                "authors": ["D. Das", "A. Padilha"],
                "theme_label": "Network Topology",
                "relevance_margin": -0.2,
                "license": None,
                "document_type": "Journal Article",
                "venue": "IEEE Trans. Power Del.",
            },
        ]
    )


def test_price_index_analysis() -> None:
    df = _sample_corpus_df()
    res = price_index_analysis(df)

    assert "global_price_index" in res
    assert res["global_price_index"] > 0
    assert not res["theme_price_df"].empty
    assert "price_index" in res["theme_price_df"].columns
    assert not res["yearly_price_df"].empty
    assert "pub_year" in res["yearly_price_df"].columns

    # Test empty dataframe
    empty_res = price_index_analysis(pd.DataFrame())
    assert empty_res["global_price_index"] == 0.0


def test_sleeping_beauties_detection() -> None:
    df = _sample_corpus_df()
    res = sleeping_beauties_detection(df, min_age=5)

    assert "sleeping_beauties" in res
    assert not res["sleeping_beauties"].empty
    assert "beauty_coefficient" in res["sleeping_beauties"].columns
    assert "awakening_lag" in res["sleeping_beauties"].columns
    assert res["count"] >= 1
    assert "top_trajectories" in res
    assert not res["top_trajectories"].empty

    # Test empty dataframe
    empty_res = sleeping_beauties_detection(pd.DataFrame())
    assert empty_res["count"] == 0


def test_disruption_index_estimation() -> None:
    df = _sample_corpus_df()
    res = disruption_index_estimation(df)

    assert "disruption_df" in res
    assert "cd_index" in res["disruption_df"].columns
    assert "team_size_analysis" in res
    assert not res["team_size_analysis"].empty
    assert "mean_cd" in res["team_size_analysis"].columns
    assert "disruptive_ratio" in res

    # Check CD range
    cd_vals = res["disruption_df"]["cd_index"]
    assert (cd_vals >= -1.0).all() and (cd_vals <= 1.0).all()

    # Test empty dataframe
    empty_res = disruption_index_estimation(pd.DataFrame())
    assert empty_res["disruptive_ratio"] == 0.0


def test_open_access_impact_analysis() -> None:
    df = _sample_corpus_df()
    res = open_access_impact_analysis(df)

    assert "oa_share_pct" in res
    assert "oaca_ratio" in res
    assert not res["comparison_table"].empty
    assert not res["yearly_oa"].empty
    assert "oa_pct" in res["yearly_oa"].columns

    # Test empty dataframe
    empty_res = open_access_impact_analysis(pd.DataFrame())
    assert empty_res["oa_share_pct"] == 0.0


def test_technological_burst_detection() -> None:
    df = _sample_corpus_df()
    # Replicate multiple rows to trigger counts
    big_df = pd.concat([df] * 6, ignore_index=True)
    res = technological_burst_detection(big_df)

    assert "burst_timeline" in res
    assert "total_bursts" in res
    assert res["total_bursts"] >= 1
    assert "Tecnologia / Conceito" in res["burst_timeline"].columns
    assert "Início do Burst" in res["burst_timeline"].columns

    # Test empty dataframe
    empty_res = technological_burst_detection(pd.DataFrame())
    assert empty_res["total_bursts"] == 0


def test_frontiers_page_import() -> None:
    from lake_literature.dashboard.pages import frontiers

    assert callable(frontiers.render)
