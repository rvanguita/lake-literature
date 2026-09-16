"""Multipage Streamlit dashboard for the lake-literature medallion pipeline.

Run from the repo root with:
    uv run streamlit run main.py

Or via docker compose:
    docker compose up dashboard

`main()` is a function on purpose: Streamlit re-executes the entry script on
every rerun, and a function body re-runs with it. (A module whose top-level code
does the rendering only executes once per process, because Python caches
imports -- every later rerun would silently no-op.)
"""

from __future__ import annotations

import streamlit as st

from lake_literature.dashboard.components import render_sidebar
from lake_literature.dashboard.pages import (
    forecasting,
    highlights,
    overview,
    pipeline_layers,
    production,
    quality,
    researchers,
    search_config,
    topics,
)
from lake_literature.dashboard.theme import apply_dashboard_theme, render_theme_toggle

PAGES = [
    (overview.render, "Visão Geral", "📊", "overview"),
    (production.render, "Produção ao Longo do Tempo", "📅", "output-over-time"),
    (topics.render, "Tópicos e Periódicos", "🏷️", "topics"),
    (highlights.render, "Destaques e Impacto", "🏆", "highlights"),
    (researchers.render, "Pesquisadores", "👥", "researchers"),
    (forecasting.render, "Tendências & Previsão", "🔮", "forecast"),
    (pipeline_layers.render, "Camadas & Pipeline", "🏗️", "pipeline-layers"),
    (quality.render, "Qualidade e RAG", "🧩", "quality"),
    (search_config.render, "Configuração da Busca", "🔎", "search-config"),
]


def main() -> None:
    st.set_page_config(page_title="lake-literature", page_icon="📚", layout="wide")
    # Must run before apply_dashboard_theme() so a just-changed choice is
    # reflected in this same rerun's CSS -- see theme.render_theme_toggle.
    render_theme_toggle()
    apply_dashboard_theme()

    page_objects = [
        st.Page(render, title=title, icon=icon, url_path=url_path, default=(i == 0))
        for i, (render, title, icon, url_path) in enumerate(PAGES)
    ]

    st.sidebar.header("📚 lake-literature")
    navigation = st.navigation(
        {
            "Resumo executivo": [page_objects[0]],
            "Análises": page_objects[1:],
        }
    )
    render_sidebar()
    navigation.run()


if __name__ == "__main__":
    main()
