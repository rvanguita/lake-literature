"""📊 Visão Geral — o corpus em resumo: volume, fontes, período temporal e crescimento."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from lake_literature.dashboard import loaders
from lake_literature.dashboard.analytics import (
    RECENT_WINDOW_YEARS,
    author_count_series,
    keyword_count_series,
    lorenz_curve,
    valid_years,
)
from lake_literature.dashboard.charts import lorenz_chart
from lake_literature.dashboard.components import (
    hero_banner,
    metric_row,
    page_header,
    render_chart,
    require_columns,
)
from lake_literature.dashboard.theme import SOURCE_COLORS, TREND_DOWN_COLOR, TREND_UP_COLOR


def render() -> None:
    page_header(
        "📊",
        "Visão Geral",
        'Pipeline de revisão sistemática de literatura sobre "planejamento de redes de distribuição de energia" — '
        "IEEE Xplore e ScienceDirect/Elsevier consolidados através das "
        "camadas raw → bronze → silver → gold.",
    )

    articles_df = loaders.require_articles()
    layer, _ = loaders.articles()  # just the active layer's name, for the banner
    chunks_df = loaders.filtered_chunks()

    years_df = _years(articles_df)
    active_year_range = st.session_state.get("global_year_range")
    active_sources = st.session_state.get("global_sources", [])
    active_venues = st.session_state.get("global_venues", [])
    filter_summary = []
    if active_year_range:
        filter_summary.append(f"ano {active_year_range[0]}–{active_year_range[1]}")
    if active_sources:
        filter_summary.append(f"{len(active_sources)} fontes")
    if active_venues:
        filter_summary.append(f"{len(active_venues)} periódicos")
    summary_text = ". ".join(filter_summary) if filter_summary else "sem filtros ativos"
    hero_banner(
        "Resumo executivo",
        f"O corpus mostra <b>{len(articles_df):,}</b> artigos em <b>{len(years_df):,}</b> anos, com "
        f"<b>{len(articles_df['source'].unique()) if 'source' in articles_df.columns else 0}</b> fontes "
        f"e filtros ativos em <b>{summary_text}</b> · camada ativa: <b>{layer}</b>.",
    )

    st.divider()
    _charts_grid(articles_df, years_df)

    if not years_df.empty:
        st.divider()
        st.subheader("Recência do Corpus")
        last_year = int(years_df["year"].max())
        recent_share = (years_df["year"] >= last_year - RECENT_WINDOW_YEARS + 1).mean()
        metric_row(
            [
                (
                    "🗓️ Período temporal coberto",
                    f"{int(years_df['year'].min())}–{last_year}",
                    None,
                ),
                (
                    f"🆕 Publicados nos últimos {RECENT_WINDOW_YEARS} anos",
                    f"{recent_share:.1%}",
                    None,
                ),
                ("📚 Artigos com ano identificado", f"{len(years_df):,}", None),
            ]
        )
        st.caption(
            f"Janela de {RECENT_WINDOW_YEARS} anos (mesma usada na página Pesquisadores) — indica se a "
            "revisão se apoia em literatura recente ou se concentra em trabalhos pioneiros clássicos."
        )

    st.divider()
    _numbers_summary(articles_df, years_df, chunks_df)


def _charts_grid(articles_df: pd.DataFrame, years_df: pd.DataFrame) -> None:
    tab_fontes, tab_ano, tab_correlacao, tab_concentracao = st.tabs(
        ["🥧 Fontes", "📐 Ano", "🔗 Correlação", "📉 Concentração"]
    )

    with tab_fontes:
        _source_distribution_pie(articles_df)

    with tab_ano:
        _year_distribution_by_source(years_df)

    with tab_correlacao:
        _correlation_heatmap(articles_df)

    with tab_concentracao:
        _venue_concentration(articles_df)


def _source_distribution_pie(articles_df: pd.DataFrame) -> None:
    st.subheader("Distribuição por Base / Fonte")
    if not require_columns(articles_df, ["source"], "Coluna 'source' não disponível nesta camada."):
        return

    by_source = articles_df["source"].value_counts().rename_axis("source").reset_index(name="count")
    fig = px.pie(
        by_source,
        names="source",
        values="count",
        color="source",
        color_discrete_map=SOURCE_COLORS,
    )
    fig.update_traces(
        texttemplate="<b>%{label}</b><br><b>%{value:,} (%{percent})</b>",
        hovertemplate="<b>%{label}</b>: %{value:,} artigos (%{percent})<extra></extra>",
    )
    render_chart(
        fig,
        caption="As duas bases não possuem sobreposição: nenhum DOI se repete entre elas, de modo "
        "que cada artigo pertence exclusivamente a uma editora.",
    )


def _year_distribution_by_source(years_df: pd.DataFrame) -> None:
    st.subheader("Distribuição do Ano de Publicação por Base")
    if years_df.empty or "source" not in years_df.columns:
        st.info("Dados insuficientes (ano/base) nesta camada.")
        return

    fig = px.box(
        years_df,
        x="source",
        y="year",
        color="source",
        color_discrete_map=SOURCE_COLORS,
        points="outliers",
        labels={"year": "Ano de publicação", "source": "Base"},
    )
    fig.update_layout(xaxis_title="Base", yaxis_title="Ano de publicação", showlegend=False)
    render_chart(
        fig,
        caption="Mediana, quartis e dispersão do ano de publicação por base — mostra se uma base tende a "
        "contribuir com literatura mais recente ou mais antiga, ao invés da contagem ano a ano (veja a "
        "página Produção para essa série).",
    )


def _correlation_heatmap(articles_df: pd.DataFrame) -> None:
    st.subheader("Correlação entre Métricas Bibliométricas")
    working = articles_df.copy()
    working["year"] = valid_years(working)

    metrics: dict[str, pd.Series] = {"Ano": working["year"]}
    if "citation_count" in working.columns:
        metrics["Citações"] = working["citation_count"]
    if "reference_count" in working.columns:
        metrics["Referências"] = working["reference_count"]
    metrics["Autores"] = author_count_series(working)
    metrics["Keywords"] = keyword_count_series(working)

    numeric_df = pd.DataFrame(metrics).apply(pd.to_numeric, errors="coerce")
    numeric_df = numeric_df.dropna(axis=1, how="all")
    if numeric_df.shape[1] < 2 or len(numeric_df) < 3:
        st.info("Dados insuficientes para calcular correlações nesta camada.")
        return

    corr = numeric_df.corr(numeric_only=True)
    fig = px.imshow(
        corr,
        zmin=-1,
        zmax=1,
        color_continuous_scale=[[0, TREND_DOWN_COLOR], [0.5, "#0b1725"], [1, TREND_UP_COLOR]],
        text_auto=".2f",
        aspect="auto",
        labels={"color": "Correlação (Pearson)"},
    )
    fig.update_layout(xaxis_title="", yaxis_title="")
    # Plotly auto-thins tick labels that would collide, which silently drops
    # columns from a small 5x5 grid like this one -- force every label to
    # show since there's no crowding risk at this size.
    fig.update_xaxes(
        tickmode="array", tickvals=list(range(len(corr.columns))), ticktext=list(corr.columns)
    )
    fig.update_yaxes(
        tickmode="array", tickvals=list(range(len(corr.index))), ticktext=list(corr.index)
    )
    render_chart(
        fig,
        caption="Correlação de Pearson entre métricas numéricas do corpus: +1 indica relação linear "
        "positiva forte, -1 negativa forte, 0 nenhuma relação linear aparente.",
    )


def _venue_concentration(articles_df: pd.DataFrame) -> None:
    st.subheader("Concentração Editorial (Curva de Lorenz)")
    if "venue" not in articles_df.columns or not articles_df["venue"].notna().any():
        st.info("Coluna 'venue' não disponível nesta camada.")
        return

    counts = articles_df["venue"].dropna().value_counts()
    lorenz_df = lorenz_curve(counts)
    x = lorenz_df["share_of_authors"].to_numpy()
    y = lorenz_df["share_of_output"].to_numpy()
    gini = 1 - 2 * np.trapezoid(y, x)

    fig = lorenz_chart({"total": lorenz_df}, entity_label="periódicos")
    render_chart(
        fig,
        caption=f"Índice de Gini de concentração editorial: {gini:.2f} (0 = produção igualmente distribuída "
        "entre periódicos; 1 = toda a produção concentrada em um único periódico). Veja a página Tópicos e "
        "Periódicos para o ranking completo.",
    )


def _numbers_summary(
    articles_df: pd.DataFrame, years_df: pd.DataFrame, chunks_df: pd.DataFrame
) -> None:
    st.subheader("📋 Resumo em números")

    n_total = len(articles_df)
    mean_refs = (
        articles_df["reference_count"].dropna().mean()
        if "reference_count" in articles_df and articles_df["reference_count"].notna().any()
        else None
    )
    mean_citations = (
        articles_df["citation_count"].dropna().mean()
        if "citation_count" in articles_df and articles_df["citation_count"].notna().any()
        else None
    )
    n_doi = (
        int(articles_df["doi"].fillna("").astype(str).str.strip().ne("").sum())
        if "doi" in articles_df
        else n_total
    )
    n_abstract = (
        int(articles_df["abstract"].fillna("").astype(str).str.strip().ne("").sum())
        if "abstract" in articles_df
        else 0
    )
    n_pdf = (
        int(articles_df["has_pdf"].fillna(False).astype(bool).sum())
        if "has_pdf" in articles_df
        else 0
    )

    st.markdown("**Cobertura**")
    metric_row(
        [
            ("📄 Artigos no Corpus", f"{n_total:,}", None),
            ("🔗 Com DOI", f"{n_doi:,}", f"{n_doi / n_total:.0%}"),
            ("📝 Com Resumo", f"{n_abstract:,}", f"{n_abstract / n_total:.0%}"),
            ("📎 Com PDF Vinculado", f"{n_pdf:,}", f"{n_pdf / n_total:.0%}"),
        ]
    )

    st.markdown("**Qualidade bibliométrica**")
    metric_row(
        [
            (
                "📚 Refs. por artigo",
                f"{mean_refs:,.1f}" if mean_refs is not None else "N/D",
                None,
            ),
            (
                "⭐ Citações médias",
                f"{mean_citations:,.1f}" if mean_citations is not None else "N/D",
                None,
            ),
            ("🧩 Chunks RAG", f"{len(chunks_df):,}", None),
            ("🧠 Cobertura de texto", f"{n_pdf / n_total:.0%}" if n_total else "N/D", None),
        ]
    )

    st.markdown("**Vocabulário**")
    n_venues = articles_df["venue"].nunique() if "venue" in articles_df else 0
    n_authors = _unique_list_values(articles_df, "authors")
    n_keywords = _unique_list_values(articles_df, "keywords")
    metric_row(
        [
            ("🗓️ Anos cobertos", f"{len(years_df):,}", None),
            ("📰 Periódicos / eventos", f"{n_venues:,}", None),
            ("👥 Autores identificados", f"{n_authors:,}", None),
            ("🏷️ Keywords únicas", f"{n_keywords:,}", None),
        ]
    )


def _years(articles_df: pd.DataFrame) -> pd.DataFrame:
    years = valid_years(articles_df).dropna()
    if years.empty:
        return pd.DataFrame()
    years_df = articles_df.loc[years.index].copy()
    years_df["year"] = years.astype(int)
    return years_df


def _unique_list_values(articles_df: pd.DataFrame, column: str) -> int:
    if column not in articles_df.columns:
        return 0
    return len(
        {
            str(value).strip().casefold()
            for values in articles_df[column]
            if isinstance(values, list)
            for value in values
            if str(value).strip()
        }
    )
