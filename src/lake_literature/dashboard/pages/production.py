"""📅 Produção ao Longo do Tempo — volume, acumulado por periódico e colaboração."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from lake_literature.dashboard import loaders
from lake_literature.dashboard.analytics import (
    OTHERS_LABEL,
    author_count_series,
    cumulative_by_source,
    cumulative_by_venue,
    source_counts_by,
    source_means,
    valid_years,
)
from lake_literature.dashboard.charts import source_bars, source_lines, stacked_area
from lake_literature.dashboard.components import page_header, render_chart, require_columns
from lake_literature.dashboard.qualis import ESTRATO_ORDER, NOT_CLASSIFIED, QUALIS_AREA
from lake_literature.dashboard.theme import (
    CATEGORICAL_PALETTE,
    CHART_HEIGHT,
    SOURCE_COLORS,
    SOURCE_LABELS,
    venue_color_map,
)

TOP_VENUES_PER_SOURCE = 8
TOP_VENUES_CUMULATIVE = 10


def render() -> None:
    page_header(
        "📅",
        "Produção ao Longo do Tempo",
        "Volume anual, crescimento acumulado por periódico e evolução do tamanho das equipes de autores.",
    )

    articles_df = loaders.require_articles()

    if not require_columns(articles_df, ["year"], "Coluna 'year' não disponível nesta camada."):
        return
    if not articles_df["year"].notna().any():
        st.info("Coluna 'year' vazia nesta camada.")
        return

    _volume_by_year(articles_df)
    st.divider()
    _volume_by_year_qualis(articles_df)
    st.divider()
    _cumulative_production(articles_df)
    st.divider()
    _venue_comparison(articles_df)
    st.divider()
    _collaboration(articles_df)


def _volume_by_year(articles_df: pd.DataFrame) -> None:
    st.subheader("Volume de publicações por ano")
    years_df = articles_df.copy()
    years_df["year"] = valid_years(years_df)
    years_df = years_df.dropna(subset=["year"]).astype({"year": int})

    by_year = source_counts_by(years_df, "year").sort_values("year")
    fig = source_bars(by_year, "year", total_line=True)
    fig.update_layout(
        hovermode="x unified",
        xaxis_title="Ano de publicação",
        yaxis_title="Quantidade de artigos",
    )
    render_chart(
        fig,
        caption="A altura empilhada mostra a contribuição de cada base (IEEE e Elsevier); a linha Total "
        "soma as duas.",
    )


def _volume_by_year_qualis(articles_df: pd.DataFrame) -> None:
    st.subheader("🎓 Volume de publicações por ano — classificação CAPES/Qualis (até B2)")
    if not require_columns(articles_df, ["venue"]) or not articles_df["venue"].notna().any():
        return

    venues = sorted(articles_df["venue"].dropna().unique())
    match_df = loaders.venue_qualis_map(tuple(venues))
    venue_to_estrato = dict(zip(match_df["venue"], match_df["estrato"], strict=True))

    # ESTRATO_ORDER is best-to-worst with the unclassified bucket last; "up to
    # B2" is everything from A1 through B2 in that ranking.
    allowed = ESTRATO_ORDER[: ESTRATO_ORDER.index("B2") + 1]

    years_df = articles_df.copy()
    years_df["year"] = valid_years(years_df)
    years_df = years_df.dropna(subset=["year"]).astype({"year": int})
    years_df["estrato"] = years_df["venue"].map(venue_to_estrato)
    years_df = years_df[years_df["estrato"].isin(allowed)]

    if years_df.empty:
        st.info(
            f"Nenhum artigo em periódico classificado até B2 (CAPES/Qualis, área {QUALIS_AREA}) "
            "nesta camada/filtro."
        )
        return

    by_year_estrato = (
        years_df.groupby(["year", "estrato"]).size().reset_index(name="count").sort_values("year")
    )
    estrato_order = [e for e in allowed if e in years_df["estrato"].unique()]
    fig = px.bar(
        by_year_estrato,
        x="year",
        y="count",
        color="estrato",
        category_orders={"estrato": estrato_order},
        color_discrete_map=venue_color_map(estrato_order, others_label=NOT_CLASSIFIED),
        barmode="stack",
        labels={
            "year": "Ano de publicação",
            "count": "Quantidade de artigos",
            "estrato": "Classificação",
        },
    )
    fig.update_traces(hovertemplate="Ano %{x}<br>%{data.name}: %{y:,} artigos<extra></extra>")
    fig.update_layout(
        hovermode="x unified",
        xaxis_title="Ano de publicação",
        yaxis_title="Quantidade de artigos",
        legend_title_text="Classificação",
    )
    render_chart(
        fig,
        caption=f"Inclui apenas periódicos classificados de A1 até B2 no CAPES/Qualis (área {QUALIS_AREA}, "
        "quadriênio 2017-2020); periódicos B3 ou piores, e os não classificados, ficam fora deste "
        "gráfico.",
    )


def _cumulative_production(articles_df: pd.DataFrame) -> None:
    st.subheader("📈 Crescimento acumulado")
    st.caption(
        "Publicações acumuladas ano a ano — total e por base — seguidas da composição acumulada por "
        "periódico."
    )
    col_total, col_venue = st.columns(2)

    with col_total:
        cum = cumulative_by_source(articles_df)
        if cum.empty:
            st.info("Sem anos válidos para o acumulado.")
        else:
            fig = source_lines(
                cum,
                "year",
                title="Publicações acumuladas por ano",
                y_title="Artigos acumulados",
            )
            fig.update_layout(xaxis_title="Ano de publicação")
            render_chart(
                fig,
                caption=f"Ao final do período, o corpus acumula {int(cum['total'].iloc[-1]):,} artigos "
                f"({int(cum['ieee'].iloc[-1]):,} IEEE, {int(cum['elsevier'].iloc[-1]):,} Elsevier).",
            )

    with col_venue:
        scope_label = st.segmented_control(
            "Escopo",
            options=["Total", "IEEE", "Elsevier"],
            default="Total",
            key="prod_cumulative_scope",
        )
        # segmented_control allows deselecting the current pill, returning
        # None -- fall back to "Total" for both the lookup and anything
        # displayed, so a deselect never renders a literal "None" in a title.
        scope_label = scope_label or "Total"
        scope = {"Total": "total", "IEEE": "ieee", "Elsevier": "elsevier"}[scope_label]
        venue_cum = cumulative_by_venue(articles_df, top_n=TOP_VENUES_CUMULATIVE, scope=scope)
        if venue_cum.empty:
            st.info("Sem dados de periódico suficientes para o acumulado por revista.")
        else:
            venue_order = (
                venue_cum.groupby("venue")["cumulative"]
                .max()
                .sort_values(ascending=False)
                .index.tolist()
            )
            venue_order = [v for v in venue_order if v != OTHERS_LABEL] + (
                [OTHERS_LABEL] if OTHERS_LABEL in venue_order else []
            )
            fig = stacked_area(
                venue_cum,
                x="year",
                y="cumulative",
                color="venue",
                color_map=venue_color_map(venue_order, others_label=OTHERS_LABEL),
                category_orders={"venue": venue_order},
                title=f"Composição acumulada por periódico ({scope_label})",
            )
            fig.update_traces(
                hovertemplate="Ano %{x}<br>%{data.name}: %{y:,.0f} artigos acumulados<extra></extra>"
            )
            fig.update_layout(
                xaxis_title="Ano de publicação",
                yaxis_title="Artigos acumulados",
                legend_title_text="Periódico",
            )
            render_chart(
                fig,
                caption=f"Top {TOP_VENUES_CUMULATIVE} periódicos no escopo selecionado; o restante é agrupado "
                f"em '{OTHERS_LABEL}'.",
            )


def _venue_comparison(articles_df: pd.DataFrame) -> None:
    st.subheader("Comparativo de periódicos: IEEE vs. Elsevier")
    st.caption(
        f"Publicações por ano discriminadas por periódico "
        f"(top {TOP_VENUES_PER_SOURCE} de cada base; os demais agrupados como '{OTHERS_LABEL}')."
    )
    col_ieee, col_els = st.columns(2)
    for col, src in ((col_ieee, "ieee"), (col_els, "elsevier")):
        with col:
            sub = articles_df.copy()
            sub["year"] = valid_years(sub)
            sub = sub.dropna(subset=["year"])
            sub = sub[sub["source"] == src] if "source" in sub.columns else sub.iloc[0:0]
            if sub.empty or "venue" not in sub.columns:
                st.info(f"Nenhum dado de {SOURCE_LABELS[src]} nesta camada.")
                continue

            top_venues = (
                sub["venue"].dropna().value_counts().head(TOP_VENUES_PER_SOURCE).index.tolist()
            )
            sub = sub.astype({"year": int}).copy()
            sub["venue_grouped"] = sub["venue"].where(sub["venue"].isin(top_venues), OTHERS_LABEL)
            by_year_venue = (
                sub.groupby(["year", "venue_grouped"])
                .size()
                .reset_index(name="count")
                .sort_values("year")
            )
            venue_order = top_venues + (
                [OTHERS_LABEL] if (sub["venue_grouped"] == OTHERS_LABEL).any() else []
            )
            fig = px.bar(
                by_year_venue,
                x="year",
                y="count",
                color="venue_grouped",
                color_discrete_map=venue_color_map(venue_order, others_label=OTHERS_LABEL),
                category_orders={"venue_grouped": venue_order},
                barmode="stack",
                title=f"{SOURCE_LABELS[src]} por ano e periódico",
                labels={"year": "Ano", "count": "Artigos", "venue_grouped": "Periódico"},
            )
            fig.update_traces(
                hovertemplate="Ano %{x}<br>%{data.name}: %{y:,} artigos<extra></extra>"
            )
            fig.update_layout(
                legend_title_text="Periódico",
                hovermode="x unified",
                xaxis_title="Ano de publicação",
                yaxis_title="Quantidade de artigos",
            )
            render_chart(fig, height=CHART_HEIGHT)


def _collaboration(articles_df: pd.DataFrame) -> None:
    st.subheader("👥 Colaboração: autores por artigo")
    if not require_columns(articles_df, ["authors"]):
        return
    with_authors = articles_df.assign(n_authors=author_count_series(articles_df))
    with_authors = with_authors[with_authors["n_authors"] > 0]

    if with_authors.empty:
        st.info("Coluna 'authors' vazia nesta camada.")
        return

    means = source_means(with_authors, "n_authors")

    col_dist, col_trend = st.columns(2)
    with col_dist:
        dist = (
            with_authors["n_authors"]
            .value_counts()
            .sort_index()
            .rename_axis("authors")
            .reset_index(name="articles")
        )
        fig = px.bar(
            dist,
            x="authors",
            y="articles",
            title="Distribuição do tamanho da equipe",
            labels={"authors": "Autores por artigo", "articles": "Quantidade de artigos"},
        )
        fig.update_traces(
            marker_color=CATEGORICAL_PALETTE[0],
            hovertemplate="%{x} autores: %{y:,} artigos<extra></extra>",
        )
        fig.update_layout(
            xaxis_title="Autores por artigo",
            yaxis_title="Quantidade de artigos",
        )
        render_chart(
            fig,
            height=CHART_HEIGHT,
            caption=f"Média de {means['total']:.1f} autores por artigo "
            f"(mediana {with_authors['n_authors'].median():.0f}). "
            f"IEEE: {means['ieee']:.1f} · Elsevier: {means['elsevier']:.1f}"
            if means["ieee"] is not None and means["elsevier"] is not None
            else f"Média de {means['total']:.1f} autores por artigo "
            f"(mediana {with_authors['n_authors'].median():.0f}).",
        )

    with col_trend:
        trend = with_authors.copy()
        trend["year"] = valid_years(trend)
        trend = trend.dropna(subset=["year"]).astype({"year": int})
        trend = trend[trend["year"] >= 2000]
        if trend.empty:
            st.info("Sem artigos a partir do ano 2000 para a série temporal.")
            return

        if "source" in trend.columns:
            by_year_auth_src = (
                trend.groupby(["year", "source"])["n_authors"].mean().reset_index(name="mean")
            )
            fig = px.line(
                by_year_auth_src,
                x="year",
                y="mean",
                color="source",
                color_discrete_map=SOURCE_COLORS,
                markers=True,
                title="Evolução do tamanho médio da equipe ao longo do tempo",
                labels={"year": "Ano", "mean": "Média de autores", "source": "Base"},
            )
        else:
            by_year_auth = trend.groupby("year")["n_authors"].mean().rename("mean").reset_index()
            fig = px.line(
                by_year_auth,
                x="year",
                y="mean",
                markers=True,
                title="Evolução do tamanho médio da equipe ao longo do tempo",
                labels={"year": "Ano", "mean": "Média de autores"},
            )
            fig.update_traces(line_color=CATEGORICAL_PALETTE[0])

        fig.update_traces(hovertemplate="Ano %{x}: %{y:.2f} autores/artigo<extra></extra>")
        fig.update_layout(
            xaxis_title="Ano de publicação",
            yaxis_title="Média de autores por artigo",
        )
        render_chart(
            fig,
            height=CHART_HEIGHT,
            caption="Tendência de colaboração desde 2000: valores crescentes indicam equipes maiores ao "
            f"longo dos anos. Média geral do corpus: {means['total']:.1f} autores/artigo.",
        )
