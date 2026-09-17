"""🧭 Semântica & Relevância — o que o corpus realmente contém, segundo os embeddings."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from lake_literature.dashboard import loaders
from lake_literature.dashboard.components import (
    article_table,
    hero_banner,
    metric_row,
    page_header,
    render_chart,
    require_columns,
)
from lake_literature.dashboard.theme import (
    CATEGORICAL_PALETTE,
    TREND_DOWN_COLOR,
    theme_tokens,
)

LOW_RELEVANCE_PERCENTILE = 10
TOP_REVIEW_ROWS = 40

# How the semantic map can be colored. The theme is the default, but a reviewer
# screening a corpus wants to ask the same picture different questions -- where
# the off-topic mass sits, whether a region is recent or old, which publisher
# indexed it.
MAP_COLOR_OPTIONS = {
    "Tema": "theme_label",
    "Relevância": "relevance_margin",
    "Ano": "year",
    "Fonte": "source",
}


def render() -> None:
    page_header(
        "🧭",
        "Semântica & Relevância",
        "Triagem de relevância, temas descobertos automaticamente e quase-duplicatas — tudo "
        "derivado dos embeddings dos resumos.",
    )

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
    # The margin needs `offtopic_score`, written by the contrastive anchor; a
    # database whose last `semantic` run predates it still gets the old view.
    has_margin = "relevance_margin" in scored.columns and scored["relevance_margin"].notna().any()
    if not has_margin:
        _legacy_relevance_screening(scored)
        return

    st.subheader("Distribuição da margem de relevância")
    margin = scored["relevance_margin"]
    low = scored[margin < 0]

    metric_row(
        [
            ("📄 Artigos com score", f"{len(scored):,}", None),
            ("📊 Margem mediana", f"{margin.median():+.3f}", None),
            (
                "🚩 Fora do escopo (margem < 0)",
                f"{len(low):,}",
                f"{100 * len(low) / len(scored):.1f}% do corpus",
            ),
        ]
    )

    fig = px.histogram(
        scored,
        x="relevance_margin",
        nbins=60,
        title="Quanto cada artigo pende para o tema da revisão, e não para logística",
        color_discrete_sequence=[CATEGORICAL_PALETTE[0]],
    )
    fig.update_layout(
        xaxis_title="Margem (relevância − proximidade a logística)",
        yaxis_title="Quantidade de artigos",
        showlegend=False,
    )
    render_chart(
        fig,
        caption="Cada resumo é comparado com **duas** âncoras: o tema da revisão e a leitura "
        "logística da mesma busca. A margem é a diferença, e o **zero é o corte**: à esquerda dele "
        "estão os artigos que o próprio texto coloca mais perto de cadeia de suprimentos do que de "
        "redes de distribuição de energia. Com uma âncora só, as duas distribuições se sobrepunham e "
        "qualquer percentil descartava também trabalho dentro do escopo. Para aplicar o corte a "
        "**todos** os gráficos, use o filtro na barra lateral.",
    )

    st.divider()
    st.subheader(f"Fora do escopo — {len(low):,} artigos para revisão manual")
    st.caption(
        "Ordenados da margem mais negativa para a menos negativa. O score é um auxílio à triagem, "
        "não um veredito: revise antes de descartar."
    )
    review = low.sort_values("relevance_margin").head(TOP_REVIEW_ROWS).copy()
    for column in ("relevance_margin", "relevance_score"):
        review[column] = review[column].round(3)
    article_table(
        review,
        [
            "relevance_margin",
            "relevance_score",
            "theme_label",
            "title",
            "year",
            "venue",
            "source",
            "doi",
        ],
        download_key="fora_do_escopo",
    )


def _legacy_relevance_screening(scored: pd.DataFrame) -> None:
    """The percentile view, for a database that predates the contrastive anchor."""
    st.subheader("Distribuição do score de relevância")
    st.info(
        "Esta camada foi gerada antes da âncora contrastiva — rode `--stage semantic` para usar a "
        "margem, cujo corte em zero substitui o percentil abaixo."
    )
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
    fig.add_vline(
        x=threshold,
        line_dash="dash",
        line_color=TREND_DOWN_COLOR,
        annotation_text=f"percentil {LOW_RELEVANCE_PERCENTILE}",
    )
    fig.update_layout(
        xaxis_title="Score de relevância (1,0 = idêntico ao tema-âncora)",
        yaxis_title="Quantidade de artigos",
        showlegend=False,
    )
    render_chart(
        fig,
        caption="O score é o cosseno entre o resumo e um texto-âncora que descreve o escopo da "
        "revisão. A cauda à esquerda concentra os falsos positivos da busca.",
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

    available = {
        label: column
        for label, column in MAP_COLOR_OPTIONS.items()
        if column in plot_df.columns and plot_df[column].notna().any()
    }
    choice = st.radio(
        "Colorir por",
        options=list(available),
        horizontal=True,
        key="semantic_map_color",
        help="A posição dos pontos não muda — só o que a cor está contando sobre eles.",
    )
    color_column = available[choice]
    continuous = choice in ("Relevância", "Ano")

    hover_data = {"map_x": False, "map_y": False, "year": True, "relevance_score": ":.3f"}
    if "relevance_margin" in plot_df.columns:
        hover_data["relevance_margin"] = ":.3f"
    fig = px.scatter(
        plot_df,
        x="map_x",
        y="map_y",
        color=color_column,
        hover_name="Título",
        hover_data=hover_data,
        title="Cada ponto é um artigo; a proximidade reflete similaridade de conteúdo",
        labels={
            "theme_label": "Tema",
            "relevance_margin": "Margem",
            "relevance_score": "Relevância",
            "year": "Ano",
            "source": "Base",
        },
        # A continuous dimension gets a scale, a categorical one the shared
        # palette -- `color_discrete_sequence` is simply ignored by px on a
        # numeric column, so passing both would silently do nothing.
        color_continuous_scale=None if not continuous else ["#e34948", "#eda100", "#1baf7a"],
        color_discrete_sequence=CATEGORICAL_PALETTE,
        opacity=0.75,
    )
    fig.update_traces(marker=dict(size=6))
    _add_theme_labels(fig, plot_df)
    # As coordenadas do t-SNE não têm unidade nem orientação interpretável --
    # só a vizinhança entre pontos significa algo --, por isso os valores dos
    # ticks ficam ocultos. Os eixos continuam nomeados: sem nome nenhum, o
    # leitor não sabe sequer em que plano está olhando.
    fig.update_layout(
        xaxis=dict(title="Dimensão 1 (t-SNE)", showticklabels=False),
        yaxis=dict(title="Dimensão 2 (t-SNE)", showticklabels=False),
        legend_title_text="Tema",
    )
    render_chart(
        fig,
        height=620,
        caption="Projeção t-SNE dos embeddings dos resumos, calculada no **mesmo espaço** em que os "
        "temas são descobertos — é isso que faz a cor de um ponto concordar com onde ele caiu. "
        "**Os eixos não têm significado**: só a proximidade entre pontos importa. Medido, o corpus é "
        "um contínuo denso com **uma** ilha destacada (a de logística, a contaminação da busca ficando "
        "visível); os temas são recortes desse contínuo, não grupos naturalmente separados.",
    )


def _add_theme_labels(fig, plot_df: pd.DataFrame) -> None:
    """Write each theme's name on the map, at the median of its points.

    Median, not mean: one article dragged to the far side of the projection
    would otherwise pull the label off its own cloud. This is a text *trace*
    (data), not `add_annotation` -- the dashboard's chart contract keeps
    annotations out of charts because they used to be guide lines covering the
    data, which these labels aren't.
    """
    if "theme_label" not in plot_df.columns:
        return
    centroids = plot_df.groupby("theme_label")[["map_x", "map_y"]].median().reset_index()
    fig.add_trace(
        go.Scatter(
            x=centroids["map_x"],
            y=centroids["map_y"],
            mode="text",
            text=centroids["theme_label"],
            textfont=dict(size=11, color=theme_tokens()["chart_annotation"]),
            hoverinfo="skip",
            showlegend=False,
        )
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
        yaxis_title="Tema",
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
    if "year" not in scored.columns:
        st.info("Coluna 'year' não disponível nesta camada.")
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
