"""🧭 Semântica & Relevância — o que o corpus realmente contém, segundo os embeddings."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from lake_literature.dashboard import loaders
from lake_literature.dashboard.components import (
    article_table,
    hero_banner,
    metric_row,
    page_header,
    render_chart,
    require_columns,
    semantic_staleness_notice,
)
from lake_literature.dashboard.theme import CATEGORICAL_PALETTE

LOW_RELEVANCE_PERCENTILE = 10
TOP_REVIEW_ROWS = 40


def render() -> None:
    page_header(
        "🧭",
        "Semântica & Relevância",
        "Triagem de relevância, temas descobertos automaticamente e quase-duplicatas — tudo "
        "derivado dos embeddings dos resumos.",
    )

    semantic_staleness_notice()

    signals = loaders.semantics()
    if signals.empty:
        st.info(
            "A etapa `semantic` ainda não foi executada — rode o botão na barra lateral ou "
            "`uv run lake-literature --stage semantic`. Ela depende de `gold` e `embed`."
        )
        return

    articles_df = loaders.require_articles()
    scoped = loaders.with_semantics(articles_df)
    if not require_columns(scoped, ["relevance_score"]):
        return
    scored = scoped.dropna(subset=["relevance_score"])

    hero_banner(
        "Por que esta página existe",
        "A busca que gerou este corpus (<i>distribution system planning</i>) é ambígua: casa tanto "
        "com <b>distribuição de energia elétrica</b> quanto com <b>distribuição logística</b>. "
        "Cada artigo recebe aqui um score de proximidade ao tema da revisão, calculado sobre o "
        "embedding do resumo — triagem de relevância é etapa metodológica de uma revisão "
        "sistemática, não um detalhe de implementação.",
    )

    tab_triagem, tab_mapa, tab_temas, tab_dupes = st.tabs(
        [
            "🎯 Triagem de Relevância",
            "🗺️ Mapa Semântico",
            "🧵 Temas Descobertos",
            "👯 Quase-Duplicatas",
        ]
    )

    with tab_triagem:
        _relevance_screening(scored)
    with tab_mapa:
        _semantic_map(scored)
    with tab_temas:
        _themes(scored)
    with tab_dupes:
        _duplicates()


def _relevance_screening(scored: pd.DataFrame) -> None:
    st.subheader("Distribuição do score de relevância")
    threshold = float(scored["relevance_score"].quantile(LOW_RELEVANCE_PERCENTILE / 100))
    low = scored[scored["relevance_score"] < threshold]

    metric_row(
        [
            ("📄 Artigos com score", f"{len(scored):,}", None),
            ("📉 Score mediano", f"{scored['relevance_score'].median():.3f}", None),
            (
                f"🚩 Abaixo do percentil {LOW_RELEVANCE_PERCENTILE}",
                f"{len(low):,}",
                f"corte em {threshold:.3f}",
            ),
        ]
    )

    fig = px.histogram(
        scored,
        x="relevance_score",
        nbins=60,
        title="Quão perto do tema da revisão está cada artigo",
        labels={"relevance_score": "Score de relevância (cosseno)", "count": "Artigos"},
        color_discrete_sequence=[CATEGORICAL_PALETTE[0]],
    )
    fig.update_layout(
        xaxis_title="Score de relevância (1,0 = idêntico ao tema-âncora)",
        yaxis_title="Quantidade de artigos",
        showlegend=False,
    )
    render_chart(
        fig,
        caption="O score é o cosseno entre o resumo e um texto-âncora que descreve o escopo da "
        "revisão. A cauda à esquerda concentra os falsos positivos da busca. Para excluí-los de "
        "**todos** os gráficos do dashboard, use o filtro na barra lateral.",
    )

    st.divider()
    st.subheader(f"Cauda de baixa relevância — {len(low):,} artigos para revisão manual")
    st.caption(
        "Ordenados do menos relevante para o mais relevante. O score é um auxílio à triagem, "
        "não um veredito: revise antes de descartar."
    )
    review = low.sort_values("relevance_score").head(TOP_REVIEW_ROWS).copy()
    review["relevance_score"] = review["relevance_score"].round(3)
    article_table(
        review,
        ["relevance_score", "theme_label", "title", "year", "venue", "source", "doi"],
        download_key="baixa_relevancia",
    )


def _semantic_map(scored: pd.DataFrame) -> None:
    st.subheader("Mapa semântico do corpus")
    if not require_columns(scored, ["map_x", "map_y", "theme_label"]):
        return

    plot_df = scored.dropna(subset=["map_x", "map_y"]).copy()
    plot_df["Título"] = plot_df["title"].fillna("—").str.slice(0, 90)
    fig = px.scatter(
        plot_df,
        x="map_x",
        y="map_y",
        color="theme_label",
        hover_name="Título",
        hover_data={"map_x": False, "map_y": False, "year": True, "relevance_score": ":.3f"},
        title="Cada ponto é um artigo; a proximidade reflete similaridade de conteúdo",
        labels={"theme_label": "Tema"},
        color_discrete_sequence=CATEGORICAL_PALETTE,
        opacity=0.75,
    )
    fig.update_traces(marker=dict(size=6))
    # As coordenadas do t-SNE não têm unidade nem orientação interpretável --
    # só a vizinhança entre pontos significa algo.
    fig.update_layout(
        xaxis=dict(title="", showticklabels=False),
        yaxis=dict(title="", showticklabels=False),
        legend_title_text="Tema",
    )
    render_chart(
        fig,
        height=620,
        caption="Projeção t-SNE dos embeddings dos resumos. **Os eixos não têm significado** — só a "
        "proximidade entre pontos importa. A ilha do tema de logística é a contaminação da busca "
        "ficando visível.",
    )


def _themes(scored: pd.DataFrame) -> None:
    st.subheader("Temas descobertos automaticamente")
    if not require_columns(scored, ["theme_label"]):
        return

    by_theme = (
        scored.groupby("theme_label")
        .agg(artigos=("doi", "size"), relevancia_media=("relevance_score", "mean"))
        .reset_index()
        .sort_values("artigos", ascending=False)
    )

    fig = px.bar(
        by_theme,
        x="artigos",
        y="theme_label",
        orientation="h",
        color="relevancia_media",
        color_continuous_scale=["#e34948", "#eda100", "#1baf7a"],
        title="Tamanho de cada tema e sua proximidade média ao escopo da revisão",
        labels={
            "artigos": "Quantidade de artigos",
            "theme_label": "",
            "relevancia_media": "Relevância",
        },
    )
    fig.update_layout(
        xaxis_title="Quantidade de artigos",
        yaxis_title="",
        yaxis=dict(categoryorder="total ascending"),
    )
    render_chart(
        fig,
        caption="Os rótulos vêm dos termos que cada grupo usa **mais que o resto do corpus** — sem "
        "isso, todo tema sairia rotulado como 'distribution, power, planning'. A cor mostra que o "
        "tema de menor relevância média é justamente o de logística, confirmando por outro caminho "
        "o que o score de relevância indica.",
    )

    st.divider()
    st.subheader("Evolução dos temas ao longo do tempo")
    if not require_columns(scored, ["year"], "Coluna 'year' não disponível nesta camada."):
        return
    yearly = scored.dropna(subset=["year"]).copy()
    yearly["year"] = pd.to_numeric(yearly["year"], errors="coerce")
    yearly = yearly.dropna(subset=["year"]).astype({"year": int})
    by_year = yearly.groupby(["year", "theme_label"]).size().reset_index(name="artigos")
    if by_year.empty:
        st.info("Sem anos válidos para esta análise.")
        return

    fig = px.area(
        by_year.sort_values("year"),
        x="year",
        y="artigos",
        color="theme_label",
        groupnorm="percent",
        title="Composição temática do corpus por ano (participação %)",
        labels={"year": "Ano", "artigos": "Participação", "theme_label": "Tema"},
        color_discrete_sequence=CATEGORICAL_PALETTE,
    )
    fig.update_layout(
        xaxis_title="Ano de publicação",
        yaxis_title="Participação no total do ano (%)",
        hovermode="x unified",
        legend_title_text="Tema",
    )
    render_chart(
        fig,
        caption="Participação relativa, não volume absoluto: mostra para onde a atenção da área "
        "migrou. Anos iniciais têm poucos artigos, então oscilam muito — leia a tendência, não o "
        "ponto isolado.",
    )


def _duplicates() -> None:
    st.subheader("Quase-duplicatas que a deduplicação por DOI não pegou")
    pairs = loaders.duplicate_pairs()
    if pairs.empty:
        st.success("Nenhum par de resumos quase idênticos com DOIs distintos.")
        return

    _, articles_df = loaders.articles()
    titles = (
        articles_df.set_index("doi")["title"]
        if "doi" in articles_df.columns and "title" in articles_df.columns
        else pd.Series(dtype="object")
    )
    table = pairs.copy()
    table["Título A"] = table["doi_a"].map(titles)
    table["Título B"] = table["doi_b"].map(titles)
    table["Similaridade"] = table["similarity"].round(4)

    st.caption(
        "O DOI é a única chave confiável de deduplicação deste corpus (ver `CLAUDE.md`), então o "
        "mesmo trabalho publicado sob dois DOIs sobrevive como dois registros. Estes pares foram "
        "detectados pela similaridade do resumo — **nada é mesclado automaticamente**, é uma lista "
        "para revisão."
    )
    st.dataframe(
        table[["Similaridade", "Título A", "Título B", "doi_a", "doi_b"]].sort_values(
            "Similaridade", ascending=False
        ),
        hide_index=True,
        width="stretch",
    )
