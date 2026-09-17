"""🏆 Destaques e Impacto — citações, referências, colaboração e periódicos mais influentes."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from lake_literature.dashboard import loaders
from lake_literature.dashboard.analytics import (
    author_count_series,
    source_counts_by,
    source_means,
    valid_years,
)
from lake_literature.dashboard.charts import source_lines, topn_hbar
from lake_literature.dashboard.components import (
    article_table,
    metric_row,
    page_header,
    render_chart,
    require_columns,
)
from lake_literature.dashboard.theme import SOURCE_COLORS

MIN_CITED_ARTICLES = 3


def render() -> None:
    page_header(
        "🏆",
        "Destaques e Impacto",
        "Análise bibliométrica: contagem de referências por artigo, citações, colaboração e periódicos mais influentes.",
    )

    articles_df = loaders.require_articles()

    tab_refs, tab_citations, tab_collab, tab_rankings = st.tabs(
        ["📚 Referências", "⭐ Citações", "👥 Colaboração", "🏅 Rankings"]
    )

    with tab_refs:
        ref_df = _reference_distribution_intro(articles_df)
        sub_hist, sub_ecdf, sub_box, sub_vs_cit, sub_top = st.tabs(
            [
                "📊 Histograma",
                "📈 ECDF",
                "📦 Box Plot",
                "🔗 Refs vs. Citações",
                "📖 Mais Referenciados",
            ]
        )
        with sub_hist:
            if ref_df is not None:
                _reference_histogram(ref_df)
        with sub_ecdf:
            if ref_df is not None:
                _reference_ecdf(ref_df)
        with sub_box:
            if ref_df is not None:
                _reference_box(ref_df)
        with sub_vs_cit:
            _references_vs_citations(articles_df)
        with sub_top:
            _top_referenced(articles_df)

    with tab_citations:
        sub_cited, sub_by_year = st.tabs(["🏆 Mais Citados", "📅 Citados por Ano"])
        with sub_cited:
            _top_cited(articles_df)
        with sub_by_year:
            _cited_by_year(articles_df)

    with tab_collab:
        _collaboration_team_size(articles_df)

    with tab_rankings:
        sub_authors, sub_impact = st.tabs(["✍️ Autores Mais Prolíficos", "📈 Impacto por Periódico"])
        with sub_authors:
            _top_authors(articles_df)
        with sub_impact:
            _venue_impact(articles_df)


def _reference_distribution_intro(articles_df: pd.DataFrame) -> pd.DataFrame | None:
    """Guard + shared metric row for the Histograma/ECDF/Box Plot sub-tabs.

    Returns the cleaned `reference_count` frame, or None if there's nothing to show.
    """
    st.subheader("📚 Quantidade de referências usadas por artigo (IEEE vs. Elsevier)")
    if not require_columns(articles_df, ["reference_count"]) or not (
        articles_df["reference_count"].notna().any()
    ):
        st.info("Nenhum artigo com contagem de referências disponível nesta camada.")
        return None

    ref_df = articles_df.dropna(subset=["reference_count"]).copy()
    ref_df["reference_count"] = ref_df["reference_count"].astype(int)
    means = source_means(ref_df, "reference_count")
    ieee_med = (
        ref_df.loc[ref_df.get("source") == "ieee", "reference_count"].median()
        if "source" in ref_df
        else None
    )
    els_med = (
        ref_df.loc[ref_df.get("source") == "elsevier", "reference_count"].median()
        if "source" in ref_df
        else None
    )
    tot_med = float(ref_df["reference_count"].median())
    max_refs = int(ref_df["reference_count"].max())

    metric_row(
        [
            (
                "📘 Média de Refs (IEEE)",
                f"{means['ieee']:.1f}" if means["ieee"] is not None else "N/D",
                f"Mediana: {ieee_med:.0f}"
                if ieee_med == ieee_med and ieee_med is not None
                else None,
            ),
            (
                "📙 Média de Refs (Elsevier)",
                f"{means['elsevier']:.1f}" if means["elsevier"] is not None else "N/D",
                f"Mediana: {els_med:.0f}" if els_med == els_med and els_med is not None else None,
            ),
            ("📊 Média de Refs (Total)", f"{means['total']:.1f}", f"Mediana: {tot_med:.0f}"),
            ("🔝 Maior Bibliografia", f"{max_refs:,} refs", f"{len(ref_df):,} artigos analisados"),
        ]
    )
    st.caption(
        "Distribuição do número de referências citadas por artigo — como histograma, curva cumulativa "
        "(ECDF) e box plot, nas abas abaixo. Os dados do IEEE têm origem direta no export CSV do IEEE "
        "Xplore (`Reference Count`). Os dados da Elsevier foram enriquecidos via cache offline "
        "(`data/enrichment_cache.json`); ver os cartões acima para as médias por base."
    )
    return ref_df


def _reference_histogram(ref_df: pd.DataFrame) -> None:
    # In overlay mode, the last category painted sits on top -- draw the
    # smaller-volume source last so its bars aren't hidden behind the
    # larger one wherever their bins overlap.
    source_order = (
        ref_df["source"].value_counts().sort_values(ascending=False).index.tolist()
        if "source" in ref_df.columns
        else None
    )
    fig_hist = px.histogram(
        ref_df,
        x="reference_count",
        color="source" if "source" in ref_df.columns else None,
        barmode="overlay",
        opacity=0.75,
        nbins=40,
        color_discrete_map=SOURCE_COLORS,
        category_orders={"source": source_order} if source_order else None,
        labels={"reference_count": "Referências citadas por artigo", "source": "Base"},
    )
    fig_hist.update_traces(
        hovertemplate="Intervalo: %{x} refs<br>Quantidade: %{y:,} artigos (%{data.name})<extra></extra>"
    )
    fig_hist.update_layout(
        xaxis_title="Referências citadas por artigo (tamanho da bibliografia)",
        yaxis_title="Quantidade de artigos",
        hovermode="x unified",
    )
    render_chart(fig_hist)


def _reference_ecdf(ref_df: pd.DataFrame) -> None:
    fig_cdf = px.ecdf(
        ref_df,
        x="reference_count",
        color="source" if "source" in ref_df.columns else None,
        color_discrete_map=SOURCE_COLORS,
        ecdfnorm="percent",
        labels={"reference_count": "Referências citadas por artigo", "source": "Base"},
    )
    fig_cdf.update_traces(
        hovertemplate="Até %{x} refs: %{y:.1f}% dos artigos (%{data.name})<extra></extra>"
    )
    fig_cdf.update_layout(
        xaxis_title="Referências citadas por artigo (tamanho da bibliografia)",
        yaxis_title="% acumulado de artigos",
        hovermode="x unified",
    )
    render_chart(
        fig_cdf,
        caption="Cada ponto (x, y) lê-se: 'y% dos artigos têm até x referências citadas'.",
    )


def _reference_box(ref_df: pd.DataFrame) -> None:
    fig_box = px.box(
        ref_df,
        x="source" if "source" in ref_df.columns else None,
        y="reference_count",
        color="source" if "source" in ref_df.columns else None,
        color_discrete_map=SOURCE_COLORS,
        points="outliers",
        labels={"reference_count": "Referências citadas por artigo", "source": "Base"},
    )
    fig_box.update_layout(
        yaxis_title="Referências citadas por artigo",
        xaxis_title="Base",
        showlegend=False,
    )
    render_chart(fig_box)


def _references_vs_citations(articles_df: pd.DataFrame) -> None:
    st.subheader("🔗 Referências citadas vs. Citações recebidas")
    if (
        not require_columns(articles_df, ["reference_count", "citation_count"])
        or not articles_df["reference_count"].notna().any()
        or not articles_df["citation_count"].notna().any()
    ):
        return

    scatter_df = articles_df.dropna(subset=["reference_count", "citation_count"]).copy()
    scatter_df = scatter_df[scatter_df["reference_count"] > 0]
    if len(scatter_df) < 5:
        st.info("Poucos artigos com dados de referências e citações disponíveis para correlação.")
        return

    corr = scatter_df[["reference_count", "citation_count"]].corr().iloc[0, 1]
    ref_mean = float(scatter_df["reference_count"].mean())
    cit_mean = float(scatter_df["citation_count"].mean())

    fig = px.scatter(
        scatter_df,
        x="reference_count",
        y="citation_count",
        color="source" if "source" in scatter_df.columns else None,
        color_discrete_map=SOURCE_COLORS,
        hover_data={
            "title": True,
            "year": True,
            "venue": True,
            "reference_count": True,
            "citation_count": True,
        },
        title=f"Relação entre tamanho da bibliografia e impacto em citações (Correlação de Pearson r = {corr:.2f})",
        labels={
            "reference_count": "Referências citadas (bibliografia)",
            "citation_count": "Citações recebidas",
            "source": "Base",
        },
    )
    fig.update_layout(hovermode="closest")
    metric_row(
        [
            ("📚 Média de referências", f"{ref_mean:.1f}", None),
            ("⭐ Média de citações", f"{cit_mean:.1f}", None),
            ("📈 Correlação de Pearson (r)", f"{corr:.2f}", None),
        ]
    )
    render_chart(
        fig,
        caption="Examina se artigos que constroem uma fundamentação teórica com maior quantidade de "
        "referências tendem a receber mais citações no decorrer dos anos.",
    )


def _top_referenced(articles_df: pd.DataFrame) -> None:
    st.subheader("📖 Artigos com maior bibliografia (Revisões sistemáticas e surveys)")
    if (
        not require_columns(articles_df, ["reference_count"])
        or not (articles_df["reference_count"] > 0).any()
    ):
        st.info("Nenhum artigo com contagem de referências disponível nesta camada.")
        return

    top_ref = articles_df[articles_df["reference_count"] > 0].nlargest(20, "reference_count")
    article_table(
        top_ref,
        ["title", "year", "venue", "source", "reference_count", "citation_count", "doi"],
        download_key="artigos_mais_referenciados",
    )
    st.caption(
        "Artigos ordenados pelo tamanho da bibliografia — contagens altas são típicas de "
        "surveys, revisões de literatura abrangentes e estudos do estado da arte. Clique no DOI para abrir o artigo."
    )


def _collaboration_team_size(articles_df: pd.DataFrame) -> None:
    st.subheader("👥 Colaboração e tamanho das equipes de autores")
    if not require_columns(articles_df, ["authors"]):
        return

    collab_df = articles_df.assign(author_count=author_count_series(articles_df))
    collab_df = collab_df[collab_df["author_count"] > 0]
    means = source_means(collab_df, "author_count")
    solo_pct = float((collab_df["author_count"] == 1).mean())

    metric_row(
        [
            (
                "📘 Média de Autores (IEEE)",
                f"{means['ieee']:.1f}" if means["ieee"] is not None else "N/D",
                None,
            ),
            (
                "📙 Média de Autores (Elsevier)",
                f"{means['elsevier']:.1f}" if means["elsevier"] is not None else "N/D",
                None,
            ),
            ("📊 Média de Autores (Total)", f"{means['total']:.1f}", None),
            ("👤 Artigos com autor único", f"{solo_pct:.1%}", f"{len(collab_df):,} artigos"),
        ]
    )

    fig = px.histogram(
        collab_df,
        x="author_count",
        color="source" if "source" in collab_df.columns else None,
        barmode="group",
        color_discrete_map=SOURCE_COLORS,
        labels={"author_count": "Quantidade de autores", "source": "Base"},
    )
    fig.update_traces(hovertemplate="%{x} autores: %{y:,} artigos (%{data.name})<extra></extra>")
    fig.update_layout(
        xaxis_title="Quantidade de autores por artigo",
        yaxis_title="Quantidade de artigos",
        hovermode="x unified",
    )
    render_chart(
        fig,
        caption="Comparativo do tamanho das equipes de autores entre IEEE e Elsevier — veja os cartões "
        "acima para as médias por base e no total.",
    )


def _top_cited(articles_df: pd.DataFrame) -> None:
    st.subheader("🏆 Artigos mais citados")
    if (
        not require_columns(articles_df, ["citation_count"])
        or not (articles_df["citation_count"] > 0).any()
    ):
        st.info("Nenhum artigo com contagem de citações disponível nesta camada.")
        return

    top_cited = articles_df[articles_df["citation_count"] > 0].nlargest(20, "citation_count")
    article_table(
        top_cited,
        ["title", "year", "venue", "source", "citation_count", "reference_count", "doi"],
        download_key="artigos_mais_citados",
    )
    st.caption(
        "Artigos ordenados pelo volume de citações acumuladas no corpus. Clique no link do DOI para abrir a publicação."
    )


def _cited_by_year(articles_df: pd.DataFrame) -> None:
    st.subheader("📅 Artigos citados por ano de publicação")
    has_citations = (
        "citation_count" in articles_df.columns and articles_df["citation_count"].notna().any()
    )
    has_year = "year" in articles_df.columns and articles_df["year"].notna().any()
    if not (has_citations and has_year):
        st.info("Colunas 'citation_count' e 'year' não disponíveis nesta camada.")
        return

    cited = articles_df.copy()
    cited["year"] = valid_years(cited)
    cited = cited.dropna(subset=["citation_count", "year"])
    cited = cited[cited["citation_count"] > 0].astype({"year": int})
    if cited.empty:
        st.info("Nenhum artigo com citações registradas nesta camada.")
        return

    counts = source_counts_by(cited, "year").sort_values("year")
    fig = source_lines(
        counts,
        "year",
        y_title="Artigos com citações registradas",
        spline=True,
        fill=True,
    )
    fig.update_layout(
        xaxis_title="Ano de publicação", hovermode="x unified", legend_title_text="Base"
    )
    render_chart(
        fig,
        caption="Quantidade de artigos publicados em cada ano que acumularam ao menos uma citação na "
        "literatura, por base e no total.",
    )


def _modal_source(rows: pd.DataFrame, key: str, keys_shown) -> pd.Series | None:
    """Most frequent `source` per entity, for the entities actually plotted.

    Scoped to `keys_shown` first: the previous
    `groupby(key)["source"].agg(lambda s: s.mode().iat[0])` ran a per-group
    mode over every author/venue in the corpus (thousands of groups) just to
    colour 15 bars. Ties resolve to the alphabetically first source, matching
    `Series.mode()`, because the groupby output is sorted and the sort below
    is stable.
    """
    if "source" not in rows.columns:
        return None
    scoped = rows[rows[key].isin(keys_shown)]
    if scoped.empty:
        return None
    counts = scoped.groupby([key, "source"], observed=True).size()
    return (
        counts.sort_values(ascending=False)
        .reset_index()
        .drop_duplicates(key)
        .set_index(key)["source"]
    )


def _top_authors(articles_df: pd.DataFrame) -> None:
    st.subheader("✍️ Autores mais prolíficos")
    if not require_columns(articles_df, ["authors"]):
        return
    authors_series = articles_df["authors"].apply(lambda a: a if isinstance(a, list) else [])
    author_rows = (
        articles_df.assign(author=authors_series).explode("author").dropna(subset=["author"])
    )
    author_rows = author_rows[author_rows["author"].astype(str).str.strip() != ""]

    if author_rows.empty:
        st.info("Coluna 'authors' vazia nesta camada.")
        return

    top_authors = author_rows["author"].value_counts().head(15)
    modal_source = _modal_source(author_rows, "author", top_authors.index)

    fig = topn_hbar(
        top_authors,
        color_by=modal_source,
        x_title="Quantidade de artigos publicados",
        y_title="Autor",
    )
    fig.update_traces(hovertemplate="<b>%{y}</b><br>%{x:,} artigos publicados<extra></extra>")
    render_chart(
        fig,
        caption="⚠️ Os nomes não estão padronizados entre as fontes: o IEEE exporta iniciais (`J. Liu`) "
        "enquanto a Elsevier exporta nomes completos (`Junyong Liu`), de modo que o mesmo pesquisador pode "
        "aparecer em registros separados aqui. Veja a página Pesquisadores para uma visão com nomes "
        "canonicalizados (e suas limitações).",
    )


def _venue_impact(articles_df: pd.DataFrame) -> None:
    st.subheader("📈 Impacto médio por periódico")
    if not require_columns(articles_df, ["citation_count", "venue"]):
        return

    cited_venues = articles_df.dropna(subset=["citation_count", "venue"])
    venue_impact = (
        cited_venues.groupby("venue")["citation_count"]
        .agg(articles="size", mean="mean")
        .query("articles >= @MIN_CITED_ARTICLES")
        .sort_values("mean", ascending=False)
        .head(15)
    )
    if venue_impact.empty:
        st.info("Nenhum periódico com artigos suficientes com contagem de citações nesta camada.")
        return

    modal_source = _modal_source(cited_venues, "venue", venue_impact.index)

    article_counts = venue_impact["articles"]
    fig = topn_hbar(
        venue_impact["mean"],
        color_by=modal_source,
        x_title="Média de citações por artigo",
        y_title="Periódico / Evento",
    )
    for trace in fig.data:
        trace.customdata = article_counts.reindex(trace.y).to_numpy().reshape(-1, 1)
        trace.hovertemplate = "<b>%{y}</b><br>%{x:.1f} citações/artigo (%{customdata[0]:,} artigos analisados)<extra></extra>"
    render_chart(
        fig,
        caption=f"Média de citações por artigo, restrita a periódicos com pelo menos "
        f"{MIN_CITED_ARTICLES} artigos com citações no corpus.",
    )
