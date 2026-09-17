"""👥 Pesquisadores — quem publica, com quem, e quem lidera cada linha de pesquisa."""

from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from lake_literature.dashboard import loaders
from lake_literature.dashboard.analytics import (
    RECENT_WINDOW_YEARS,
    author_count_series,
    author_display_name,
    author_productivity_trend,
    author_year_matrix,
    canonical_author,
    cumulative_researchers,
    explode_authors_with_position,
    explode_keywords,
    gini_coefficient,
    lorenz_curve,
    output_impact_correlation,
    researchers_by_year,
    valid_years,
)
from lake_literature.dashboard.charts import (
    lorenz_chart,
    source_bars,
    source_lines,
    source_topn_hbar,
    topn_hbar,
)
from lake_literature.dashboard.components import (
    article_table,
    hero_banner,
    metric_row,
    page_header,
    render_chart,
)
from lake_literature.dashboard.theme import CATEGORICAL_PALETTE, theme_tokens

TOP_AUTHORS = 25
MIN_PAPERS_FOR_NETWORK = 4
TOP_NETWORK_AUTHORS = 18


# Both helpers take `loaders.filter_signature()` rather than the frame itself:
# hashing the frame meant serializing ~3.5MB to JSON on every cache lookup,
# which cost more than the work being cached. They re-read the filtered frame
# internally, so the signature fully determines the result.
@st.cache_data(ttl=60)
def _author_table(filter_sig: tuple) -> pd.DataFrame:
    """Explode authors (with byline position), canonicalize identity, keep one display name per key."""
    _, articles_df = loaders.filtered_articles()
    exploded = explode_authors_with_position(articles_df)
    if exploded.empty:
        return exploded
    exploded["author_key"] = exploded["author"].apply(canonical_author)
    exploded = exploded[exploded["author_key"] != ""]
    display_names = exploded.groupby("author_key")["author"].apply(author_display_name)
    exploded["author_display"] = exploded["author_key"].map(display_names)
    return exploded


@st.cache_data(ttl=60)
def _author_year_matrix_cached(filter_sig: tuple) -> pd.DataFrame:
    _, articles_df = loaders.filtered_articles()
    return author_year_matrix(articles_df)


def render() -> None:
    page_header(
        "👥",
        "Pesquisadores",
        "Produção, colaboração e linhas de pesquisa dos autores do corpus.",
    )

    articles_df = loaders.require_articles()
    author_rows = _author_table(loaders.filter_signature())

    if author_rows.empty:
        st.info("Coluna 'authors' não disponível ou vazia nesta camada.")
        return

    hero_banner(
        "⚠️ Nomes canonicalizados, não identidades verificadas",
        "Os nomes são normalizados para <b>inicial + sobrenome</b> (ex.: <code>Junyong Liu</code> e "
        "<code>J. Liu</code> viram a mesma chave) porque o IEEE exporta iniciais e a Elsevier nomes "
        "completos. Isso funde grafias do mesmo pesquisador, mas também pode fundir <b>homônimos "
        "diferentes</b> que compartilham inicial e sobrenome — trate os números como uma aproximação, não "
        "como identidade confirmada.",
    )

    n_authors = author_rows["author_key"].nunique()
    per_author_counts = (
        author_rows.groupby("author_key")["doi"].nunique()
        if "doi" in author_rows.columns
        else author_rows.groupby("author_key").size()
    )
    n_5plus = int((per_author_counts >= 5).sum())
    n_3plus = int((per_author_counts >= 3).sum())
    metric_row(
        [
            ("👥 Autores distintos (canonicalizados)", f"{n_authors:,}", None),
            ("🏅 Com ≥5 artigos", f"{n_5plus:,}", None),
            ("📗 Com ≥3 artigos", f"{n_3plus:,}", None),
            (
                "✍️ Média de autores/artigo",
                f"{author_count_series(articles_df).mean():.1f}",
                None,
            ),
        ]
    )

    st.divider()
    tab_ranking, tab_production, tab_collab, tab_explore, tab_stats = st.tabs(
        ["🏅 Ranking", "🗓️ Produção", "🕸️ Colaboração", "🔎 Exploração", "📐 Tabela & Estatísticas"]
    )

    with tab_ranking:
        sub_prolific, sub_lead = st.tabs(["✍️ Mais Prolíficos", "🥇 1º/2º Autor"])
        with sub_prolific:
            _top_authors(author_rows)
        with sub_lead:
            _lead_authors_ranking(author_rows)

    with tab_production:
        (
            sub_by_year,
            sub_cumulative,
            sub_lead_year,
            sub_lead_cumulative,
            sub_heatmap,
            sub_emerging,
        ) = st.tabs(
            [
                "👥 Pesquisadores/Ano",
                "📈 Acumulado",
                "🥇 1º/2º Autores/Ano",
                "📈 1º/2º Acumulado",
                "🗓️ Heatmap Top Autores",
                "🌱 Emergentes vs. Consolidados",
            ]
        )
        with sub_by_year:
            _researchers_by_year(articles_df)
        with sub_cumulative:
            _cumulative_researchers_chart(articles_df)
        with sub_lead_year:
            _lead_authors_by_year(articles_df)
        with sub_lead_cumulative:
            _cumulative_lead_authors_chart(articles_df)
        with sub_heatmap:
            _production_heatmap(author_rows)
        with sub_emerging:
            _emerging_vs_established(author_rows)

    with tab_collab:
        _coauthorship_network(author_rows)

    with tab_explore:
        (
            sub_leaders,
            sub_trend,
            sub_kw_year,
            sub_kw_cum,
            sub_kw_profile,
            sub_kw_shift,
        ) = st.tabs(
            [
                "🔎 Líderes da Linha",
                "📈 Trajetória Anual",
                "👥 Pesquisadores/Ano",
                "📈 Pesquisadores Acumulados",
                "🏷️ Perfil de Palavras-Chave",
                "🔀 Mudança de Foco",
            ]
        )
        selected_kw, scoped_authors, dois_with_kw = _research_line_selector(
            author_rows, articles_df
        )
        with sub_leaders:
            if selected_kw:
                _research_line_top_authors(selected_kw, scoped_authors)
        with sub_trend:
            if selected_kw:
                _research_line_trend(selected_kw, scoped_authors)
        with sub_kw_year:
            if selected_kw:
                _research_line_researchers_by_year(selected_kw, articles_df, dois_with_kw)
        with sub_kw_cum:
            if selected_kw:
                _research_line_researchers_cumulative(selected_kw, articles_df, dois_with_kw)
                _research_line_articles(articles_df, scoped_authors, selected_kw)

        selected_author = _author_keyword_selector(author_rows)
        working_kw = (
            _author_keyword_working(selected_author, author_rows, articles_df)
            if selected_author
            else None
        )
        with sub_kw_profile:
            if working_kw is not None:
                _author_keyword_overview(selected_author, working_kw)
        with sub_kw_shift:
            if working_kw is not None:
                _author_keyword_shift(working_kw)

    with tab_stats:
        sub_table, sub_concentration, sub_trend_table, sub_vs_impact = st.tabs(
            [
                "📋 Tabela Completa",
                "📐 Concentração (Gini/Lorenz)",
                "📈 Tendência de Produtividade",
                "📊 Volume × Impacto",
            ]
        )
        with sub_table:
            matrix = _full_output_table(articles_df)
        with sub_concentration:
            _concentration_analysis(matrix)
        with sub_trend_table:
            _productivity_trend(matrix)
        with sub_vs_impact:
            _volume_vs_impact(author_rows)


def _top_authors(author_rows: pd.DataFrame) -> None:
    st.subheader("✍️ Autores mais prolíficos (canonicalizado)")
    count_col = "doi" if "doi" in author_rows.columns else "author_display"
    agg = "nunique" if count_col == "doi" else "size"
    counts = author_rows.groupby("author_display")[count_col].agg(agg)
    top_index = counts.sort_values(ascending=False).head(15).index

    if "source" in author_rows.columns:
        scoped = author_rows[author_rows["author_display"].isin(top_index)]
        by_source = (
            scoped.groupby(["author_display", "source"])[count_col].agg(agg).unstack(fill_value=0)
        )
        for src in ("ieee", "elsevier"):
            if src not in by_source.columns:
                by_source[src] = 0
        by_source["total"] = counts.reindex(top_index)
        by_source = by_source.reindex(top_index).reset_index()
        fig = source_topn_hbar(
            by_source, "author_display", x_title="Quantidade de artigos", y_title="Autor"
        )
        fig.update_traces(hovertemplate="<b>%{y}</b><br>%{x:,} artigos<extra></extra>")
    else:
        fig = topn_hbar(counts.reindex(top_index), x_title="Quantidade de artigos", y_title="Autor")
        fig.update_traces(hovertemplate="<b>%{y}</b><br>%{x:,} artigos<extra></extra>")
    render_chart(fig)


def _lead_authors_ranking(author_rows: pd.DataFrame) -> None:
    st.subheader("🥇 Mais frequentes como 1º ou 2º autor")
    if "position" not in author_rows.columns:
        st.info("Posição do autor na publicação não disponível nesta camada.")
        return

    lead_rows = author_rows[author_rows["position"] <= 1]
    if lead_rows.empty:
        st.info("Nenhum autor em 1ª/2ª posição identificado nesta camada.")
        return

    count_col = "doi" if "doi" in lead_rows.columns else "author_display"
    agg = "nunique" if count_col == "doi" else "size"
    counts = lead_rows.groupby("author_display")[count_col].agg(agg)
    top_index = counts.sort_values(ascending=False).head(15).index

    if "source" in lead_rows.columns:
        scoped = lead_rows[lead_rows["author_display"].isin(top_index)]
        by_source = (
            scoped.groupby(["author_display", "source"])[count_col].agg(agg).unstack(fill_value=0)
        )
        for src in ("ieee", "elsevier"):
            if src not in by_source.columns:
                by_source[src] = 0
        by_source["total"] = counts.reindex(top_index)
        by_source = by_source.reindex(top_index).reset_index()
        fig = source_topn_hbar(
            by_source, "author_display", x_title="Artigos como 1º/2º autor", y_title="Autor"
        )
        fig.update_traces(hovertemplate="<b>%{y}</b><br>%{x:,} artigos<extra></extra>")
    else:
        fig = topn_hbar(
            counts.reindex(top_index), x_title="Artigos como 1º/2º autor", y_title="Autor"
        )
        fig.update_traces(hovertemplate="<b>%{y}</b><br>%{x:,} artigos<extra></extra>")
    render_chart(
        fig,
        caption="Contagem combinada de artigos em que o autor aparece na 1ª OU 2ª posição da lista de "
        "autores, na ordem registrada pela fonte (não é alfabética). Posição na publicação é apenas "
        "isso -- uma posição; não indica um papel de autoria específico (a convenção sobre o que 1ª/2ª "
        "posição significa varia por área, e este corpus não registra papéis). Vale o mesmo aviso de "
        "canonicalização do topo da página.",
    )


def _researchers_by_year(articles_df: pd.DataFrame) -> None:
    st.subheader("👥 Pesquisadores ativos por ano")
    by_year = researchers_by_year(articles_df)
    if by_year.empty:
        st.info("Sem anos válidos para este gráfico.")
        return

    fig = source_bars(by_year, "year", total_line=True)
    fig.update_layout(
        hovermode="x unified",
        xaxis_title="Ano de publicação",
        yaxis_title="Pesquisadores distintos",
    )
    render_chart(
        fig,
        caption="Autores canonicalizados distintos que publicaram em cada ano, por base. Um autor "
        "publicando nas duas bases no mesmo ano conta uma vez em cada base, mas apenas uma vez no "
        "Total — por isso o Total pode ser menor que a soma de IEEE + Elsevier.",
    )


def _cumulative_researchers_chart(articles_df: pd.DataFrame) -> None:
    st.subheader("📈 Pesquisadores acumulados")
    cum = cumulative_researchers(articles_df)
    if cum.empty:
        st.info("Sem anos válidos para o acumulado.")
        return

    fig = source_lines(
        cum,
        "year",
        title="Pesquisadores distintos acumulados por ano",
        y_title="Pesquisadores acumulados",
    )
    fig.update_layout(xaxis_title="Ano de publicação")
    render_chart(
        fig,
        caption=f"Cada pesquisador é contado uma única vez, no ano da sua primeira publicação "
        f"identificada no corpus (por base, e no geral para o Total). Ao final do período, o corpus "
        f"acumula {int(cum['total'].iloc[-1]):,} pesquisadores distintos "
        f"({int(cum['ieee'].iloc[-1]):,} IEEE, {int(cum['elsevier'].iloc[-1]):,} Elsevier).",
    )


def _lead_authors_by_year(articles_df: pd.DataFrame) -> None:
    st.subheader("🥇 1º/2º autores ativos por ano")
    by_year = researchers_by_year(articles_df, max_position=1)
    if by_year.empty:
        st.info("Sem anos válidos para este gráfico.")
        return

    fig = source_bars(by_year, "year", total_line=True)
    fig.update_layout(
        hovermode="x unified",
        xaxis_title="Ano de publicação",
        yaxis_title="Pesquisadores distintos (1º/2º autor)",
    )
    render_chart(
        fig,
        caption="Autores canonicalizados distintos que apareceram como 1º ou 2º autor em cada ano, "
        'por base -- não é o mesmo universo do gráfico "Pesquisadores ativos por ano" acima, que '
        "conta qualquer posição na lista de autores.",
    )


def _cumulative_lead_authors_chart(articles_df: pd.DataFrame) -> None:
    st.subheader("📈 1º/2º autores acumulados")
    cum = cumulative_researchers(articles_df, max_position=1)
    if cum.empty:
        st.info("Sem anos válidos para o acumulado.")
        return

    fig = source_lines(
        cum,
        "year",
        title="1º/2º autores distintos acumulados por ano",
        y_title="Pesquisadores acumulados",
    )
    fig.update_layout(xaxis_title="Ano de publicação")
    render_chart(
        fig,
        caption=f"Cada pesquisador é contado uma única vez, no ano da sua primeira aparição como 1º "
        f"ou 2º autor. Ao final do período, o corpus acumula {int(cum['total'].iloc[-1]):,} "
        f"pesquisadores distintos nessa condição ({int(cum['ieee'].iloc[-1]):,} IEEE, "
        f"{int(cum['elsevier'].iloc[-1]):,} Elsevier).",
    )


def _production_heatmap(author_rows: pd.DataFrame) -> None:
    st.subheader("🗓️ Produção por ano — top autores")
    working = author_rows.copy()
    working["year"] = valid_years(working)
    working = working.dropna(subset=["year"]).astype({"year": int})
    if working.empty:
        st.info("Sem anos válidos para o heatmap.")
        return

    top_authors = (
        working.groupby("author_display")["doi"]
        .nunique()
        .sort_values(ascending=False)
        .head(TOP_AUTHORS)
        .index
        if "doi" in working.columns
        else working.groupby("author_display")
        .size()
        .sort_values(ascending=False)
        .head(TOP_AUTHORS)
        .index
    )
    scoped = working[working["author_display"].isin(top_authors)]
    pivot = scoped.groupby(["author_display", "year"]).size().unstack(fill_value=0)
    pivot = pivot.reindex(top_authors)

    fig = px.imshow(
        pivot,
        aspect="auto",
        color_continuous_scale=["#0b1725", CATEGORICAL_PALETTE[0], CATEGORICAL_PALETTE[3]],
        labels={"x": "Ano de publicação", "y": "Autor", "color": "Artigos"},
    )
    fig.update_layout(height=max(420, 22 * len(pivot)))
    render_chart(
        fig,
        caption="Linhas com atividade recente indicam pesquisadores ativos; linhas concentradas em anos "
        "antigos indicam quem parou de publicar nesta linha de pesquisa.",
    )


def _emerging_vs_established(author_rows: pd.DataFrame) -> None:
    st.subheader("🌱 Emergentes vs. consolidados")
    working = author_rows.copy()
    working["year"] = valid_years(working)
    working = working.dropna(subset=["year"]).astype({"year": int})
    if working.empty:
        st.info("Sem anos válidos para esta análise.")
        return

    last_year = int(working["year"].max())
    by_author = working.groupby("author_display").agg(
        first_year=("year", "min"),
        total_papers=("year", "size"),
        recent_papers=("year", lambda s: (s >= last_year - RECENT_WINDOW_YEARS + 1).sum()),
    )
    by_author = by_author[by_author["total_papers"] >= 2]
    if by_author.empty:
        st.info("Sem autores com produção suficiente para o comparativo.")
        return

    fig = px.scatter(
        by_author.reset_index(),
        x="first_year",
        y="recent_papers",
        size="total_papers",
        color="total_papers",
        color_continuous_scale=["#4a3aa7", "#eda100", "#1baf7a"],
        hover_name="author_display",
        labels={
            "first_year": "Ano da primeira publicação no corpus",
            "recent_papers": f"Artigos nos últimos {RECENT_WINDOW_YEARS} anos",
            "total_papers": "Total de artigos",
        },
    )
    fig.update_layout(coloraxis_showscale=False)
    render_chart(
        fig,
        caption="Quadrante superior direito = pesquisadores recentes já com produção alta (em ascensão); "
        "quadrante inferior esquerdo (ano de estreia antigo, poucos artigos recentes) = atividade "
        "concentrada no passado nesta linha de pesquisa.",
    )


def _correlation_by_source(author_rows: pd.DataFrame) -> pd.DataFrame:
    """Pearson/Spearman/N for IEEE, Elsevier, and Total, as one small table."""
    sources: list[tuple[str, str | None]] = [("Total", None)]
    if "source" in author_rows.columns:
        sources = [("IEEE", "ieee"), ("Elsevier", "elsevier"), *sources]
    rows = []
    for label, key in sources:
        subset = author_rows[author_rows["source"] == key] if key else author_rows
        stats = output_impact_correlation(subset, "citation_count")
        rows.append(
            {
                "Base": label,
                "Pearson": f"{stats['pearson']:.2f}" if stats["pearson"] is not None else "—",
                "Spearman": f"{stats['spearman']:.2f}" if stats["spearman"] is not None else "—",
                "Autores": stats["n"],
            }
        )
    return pd.DataFrame(rows)


def _volume_vs_impact(author_rows: pd.DataFrame) -> None:
    st.subheader("📊 Volume × impacto")
    if "citation_count" not in author_rows.columns:
        st.info("Coluna 'citation_count' não disponível nesta camada.")
        return
    stats = output_impact_correlation(author_rows, "citation_count")
    by_author = author_rows.groupby("author_display").agg(
        articles=("author_display", "size"),
        mean_citations=("citation_count", "mean"),
        total_citations=("citation_count", "sum"),
    )
    by_author = by_author[by_author["articles"] >= 2].dropna(subset=["mean_citations"])
    if by_author.empty or stats["pearson"] is None:
        st.info("Sem dados de citação suficientes para autores com ≥2 artigos.")
        return

    st.dataframe(_correlation_by_source(author_rows), hide_index=True, width="stretch")
    fig = px.scatter(
        by_author.reset_index(),
        x="articles",
        y="mean_citations",
        size="total_citations",
        color="mean_citations",
        color_continuous_scale=["#4a3aa7", "#eda100", "#1baf7a"],
        hover_name="author_display",
        title=f"Volume × impacto (Pearson r = {stats['pearson']:.2f})",
        labels={"articles": "Artigos no corpus", "mean_citations": "Citações médias por artigo"},
    )
    fig.update_layout(coloraxis_showscale=False)
    render_chart(
        fig,
        caption="`citation_count` nulo é tratado como 'não coletado' e excluído da média — não como zero. "
        "O tamanho da bolha é o total de citações acumuladas pelo autor. A correlação de Spearman é "
        "incluída por ser mais robusta a distribuições de cauda longa (poucos autores com produção ou "
        "citações muito acima da média), comuns em dados bibliométricos.",
    )


def _full_output_table(articles_df: pd.DataFrame) -> pd.DataFrame:
    st.subheader("📋 Produção completa por autor e ano")
    matrix = _author_year_matrix_cached(loaders.filter_signature())
    if matrix.empty:
        st.info("Sem anos válidos para montar a tabela.")
        return matrix

    st.caption(
        "Uma linha por autor canonicalizado (ver aviso no topo da página), uma coluna por ano de "
        "publicação válido, mais `total`, `ieee_total` e `elsevier_total` (quebra do total histórico "
        "por base). Contagem por DOI distinto quando disponível, para não contar duas vezes um artigo "
        "em coautoria assinado pelo mesmo autor. **Ordenado do maior para o menor total.**"
    )
    st.dataframe(matrix, hide_index=True, width="stretch")
    st.download_button(
        "⬇️ Baixar tabela completa (CSV)",
        data=matrix.to_csv(index=False).encode("utf-8"),
        file_name="producao_por_autor_ano.csv",
        mime="text/csv",
        key="dl_author_year_matrix",
    )
    return matrix


def _gini_interpretation(gini: float) -> str:
    if gini < 0.3:
        return "baixa concentração — a produção é relativamente distribuída entre os autores"
    if gini > 0.6:
        return "alta concentração — a produção está dominada por poucos autores muito prolíficos"
    return "concentração moderada"


def _concentration_analysis(matrix: pd.DataFrame) -> None:
    st.subheader("📐 Concentração da produção (Gini / curva de Lorenz)")
    if matrix.empty:
        st.info("Sem dados suficientes para esta análise.")
        return

    gini_ieee = gini_coefficient(matrix["ieee_total"])
    gini_elsevier = gini_coefficient(matrix["elsevier_total"])
    gini_total = gini_coefficient(matrix["total"])
    metric_row(
        [
            ("📐 Gini — IEEE", f"{gini_ieee:.2f}", _gini_interpretation(gini_ieee)),
            ("📐 Gini — Elsevier", f"{gini_elsevier:.2f}", _gini_interpretation(gini_elsevier)),
            ("📐 Gini — Total", f"{gini_total:.2f}", _gini_interpretation(gini_total)),
        ]
    )

    fig = lorenz_chart(
        {
            "ieee": lorenz_curve(matrix["ieee_total"]),
            "elsevier": lorenz_curve(matrix["elsevier_total"]),
            "total": lorenz_curve(matrix["total"]),
        }
    )
    render_chart(
        fig,
        caption="Índice de Gini calculado sobre o total histórico por autor, separado por base (0 = "
        "todos publicam o mesmo tanto, 1 = um único autor concentra toda a produção). Quanto mais uma "
        "curva observada se afasta da diagonal de equidade perfeita, mais concentrada é a produção "
        "naquela base.",
    )


def _productivity_trend(matrix: pd.DataFrame) -> None:
    st.subheader("📈 Tendência de produtividade — top autores")
    if matrix.empty:
        st.info("Sem dados suficientes para esta análise.")
        return

    trend_df = author_productivity_trend(matrix, top_n=TOP_AUTHORS)
    st.caption(
        f"Reta de tendência (mínimos quadrados, `numpy.polyfit` grau 1) de artigos por ano para cada "
        f"um dos {TOP_AUTHORS} autores mais prolíficos, usando somente os anos em que o autor "
        "publicou. Classificado como 'crescendo'/'caindo' quando a inclinação ultrapassa ±0,15 "
        "artigo/ano; dentro dessa faixa é 'estável'. Séries deste tamanho (poucos anos ativos) não "
        "sustentam um teste de significância estatística confiável — é um indicador direcional, não "
        "uma previsão."
    )
    display = trend_df.rename(
        columns={
            "author": "Autor",
            "total": "Total histórico",
            "first_year": "Primeiro ano",
            "last_year": "Último ano",
            "active_years": "Anos ativos",
            "slope": "Inclinação (artigos/ano)",
            "trend": "Tendência",
        }
    )
    st.dataframe(display, hide_index=True, width="stretch")


def _coauthorship_network(author_rows: pd.DataFrame) -> None:
    st.subheader("🕸️ Rede de coautoria (top autores)")
    if "doi" not in author_rows.columns:
        st.info("Coluna 'doi' não disponível para reconstruir a rede.")
        return

    counts = author_rows.groupby("author_display")["doi"].nunique()
    # A force-directed layout was tried here and, even after several rounds of
    # tuning, still put too many authors too close together to read at 60
    # nodes. A much smaller, fixed circular layout trades "shows everyone" for
    # "every connection is actually legible" -- no physics, no randomness, no
    # possible overlap (evenly spaced points on a circle can't collide).
    top_authors = (
        counts[counts >= MIN_PAPERS_FOR_NETWORK]
        .sort_values(ascending=False)
        .head(TOP_NETWORK_AUTHORS)
        .index
    )
    if len(top_authors) < 3:
        st.info(
            f"Poucos autores com ≥{MIN_PAPERS_FOR_NETWORK} artigos para montar uma rede legível."
        )
        return

    scoped = author_rows[author_rows["author_display"].isin(top_authors)]
    by_doi = scoped.groupby("doi")["author_display"].apply(list)

    graph = nx.Graph()
    graph.add_nodes_from(top_authors)
    for authors in by_doi:
        unique_authors = sorted(set(authors))
        for i in range(len(unique_authors)):
            for j in range(i + 1, len(unique_authors)):
                a, b = unique_authors[i], unique_authors[j]
                if graph.has_edge(a, b):
                    graph[a][b]["weight"] += 1
                else:
                    graph.add_edge(a, b, weight=1)

    # Authors in the top-N by volume with no coauthor also in the top-N add
    # nothing to a *network* view -- drop them rather than scatter meaningless
    # isolated dots around the circle.
    graph.remove_nodes_from(list(nx.isolates(graph)))
    if graph.number_of_edges() == 0:
        st.info("Nenhuma coautoria encontrada entre os autores mais produtivos.")
        return

    n = graph.number_of_nodes()
    # Order nodes by a depth-first walk of the graph (starting from the most
    # connected author) rather than alphabetically or by rank -- neighbors in
    # the walk tend to be actual collaborators, so placing them next to each
    # other around the circle keeps most edges short instead of criss-crossing
    # the whole diagram. Any node a DFS from one root can't reach (a separate
    # component) is appended afterwards.
    root = max(graph.degree, key=lambda kv: kv[1])[0]
    order = list(nx.dfs_preorder_nodes(graph, source=root))
    order += [node for node in graph.nodes() if node not in order]

    radius = 9.0
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
    pos = {
        node: np.array([radius * np.cos(a), radius * np.sin(a)])
        for node, a in zip(order, angles, strict=True)
    }

    degree = dict(graph.degree())
    weighted_degree = dict(graph.degree(weight="weight"))
    nodes = list(graph.nodes())

    # Edges as separate line segments so each can carry its own width
    # (thicker = more shared papers) -- a single merged trace can only have
    # one width for every edge.
    edge_traces = []
    max_w = max((d["weight"] for _, _, d in graph.edges(data=True)), default=1)
    for a, b, d in graph.edges(data=True):
        x0, y0 = pos[a]
        x1, y1 = pos[b]
        edge_traces.append(
            go.Scatter(
                x=[x0, x1],
                y=[y0, y1],
                mode="lines",
                line=dict(
                    color="rgba(94,169,255,0.35)",
                    width=1 + 4 * (d["weight"] / max_w),
                ),
                hoverinfo="skip",
                showlegend=False,
            )
        )

    fig = go.Figure(data=edge_traces)
    fig.add_trace(
        go.Scatter(
            x=[pos[a][0] for a in nodes],
            y=[pos[a][1] for a in nodes],
            mode="markers+text",
            text=nodes,
            textposition="top center",
            textfont=dict(size=10, color=theme_tokens()["chart_text"]),
            marker=dict(
                size=[10 + 4 * degree[a] for a in nodes],
                color=CATEGORICAL_PALETTE[0],
                line=dict(width=1.5, color="rgba(255,255,255,0.4)"),
            ),
            customdata=[[degree[a], weighted_degree[a]] for a in nodes],
            hovertemplate=(
                "<b>%{text}</b><br>%{customdata[0]} coautores<br>"
                "%{customdata[1]} artigos em coautoria (peso total)<extra></extra>"
            ),
            showlegend=False,
        )
    )
    # O layout é um círculo fixo: a posição de um nó não codifica nada, então
    # ticks e grade somem (e `scaleanchor` mantém o círculo redondo). Os eixos
    # ficam nomeados dizendo exatamente isso, em vez de aparecerem anônimos.
    fig.update_layout(
        xaxis=dict(
            title="Posição no layout circular (sem unidade)",
            showticklabels=False,
            showgrid=False,
            zeroline=False,
            ticks="",
            scaleanchor="y",
            scaleratio=1,
        ),
        yaxis=dict(
            title="Posição no layout circular (sem unidade)",
            showticklabels=False,
            showgrid=False,
            zeroline=False,
            ticks="",
        ),
        showlegend=False,
        height=650,
        hovermode="closest",
    )
    render_chart(
        fig,
        caption=f"Layout circular fixo (sem física): os {n} autores com pelo menos uma coautoria entre os "
        f"{TOP_NETWORK_AUTHORS} mais produtivos (≥{MIN_PAPERS_FOR_NETWORK} artigos) ficam igualmente "
        "espaçados ao redor do círculo — a posição não indica proximidade, e a ordem segue uma caminhada "
        "pelo grafo a partir do autor mais conectado, para manter a maioria das conexões como linhas curtas "
        "em vez de cruzarem o desenho inteiro. A espessura da linha reflete quantos artigos os dois autores "
        "assinaram juntos, e o tamanho do nó reflete o número de coautores distintos. Esta visão prioriza "
        "legibilidade sobre cobertura — nem todo colaborador do corpus aparece aqui.",
    )


def _research_line_selector(
    author_rows: pd.DataFrame, articles_df: pd.DataFrame
) -> tuple[str | None, pd.DataFrame, set]:
    """Shared keyword selector for all "Exploração" research-line sub-tabs.

    Returns `(selected_keyword, scoped_authors, dois_with_kw)`; `selected_keyword`
    is None when there's nothing to show (missing data or no valid selection).
    """
    st.subheader("🔎 Quem lidera esta linha de pesquisa")
    kw_exploded = explode_keywords(articles_df)
    if kw_exploded.empty:
        st.info("Coluna 'keywords' não disponível nesta camada.")
        return None, author_rows.iloc[0:0], set()

    top_keywords = kw_exploded["keyword"].value_counts().head(60).index.tolist()
    selected = st.selectbox("Selecione uma palavra-chave:", options=top_keywords)
    if not selected:
        return None, author_rows.iloc[0:0], set()

    dois_with_kw = set(kw_exploded.loc[kw_exploded["keyword"] == selected, "doi"].dropna())
    scoped_authors = (
        author_rows[author_rows["doi"].isin(dois_with_kw)]
        if "doi" in author_rows.columns
        else author_rows.iloc[0:0]
    )
    if scoped_authors.empty:
        st.info("Nenhum autor associado a esse termo nesta camada.")
        return None, scoped_authors, dois_with_kw

    return selected, scoped_authors, dois_with_kw


def _research_line_top_authors(selected: str, scoped_authors: pd.DataFrame) -> None:
    leaders = (
        scoped_authors.groupby("author_display")["doi"]
        .nunique()
        .sort_values(ascending=False)
        .head(10)
    )
    fig = topn_hbar(
        leaders,
        title=f"Autores mais produtivos em '{selected}'",
        x_title="Quantidade de artigos",
        y_title="Autor",
    )
    render_chart(fig)


def _research_line_trend(selected: str, scoped_authors: pd.DataFrame) -> None:
    trend_df = scoped_authors.copy()
    trend_df["year"] = valid_years(trend_df)
    trend_df = trend_df.dropna(subset=["year"]).astype({"year": int})
    if trend_df.empty:
        st.info("Sem anos válidos para a trajetória.")
        return

    by_year = trend_df.groupby("year")["doi"].nunique().reset_index(name="articles")
    fig = px.line(
        by_year,
        x="year",
        y="articles",
        markers=True,
        title=f"Trajetória anual de '{selected}'",
        labels={"year": "Ano", "articles": "Artigos"},
    )
    fig.update_traces(line_color=CATEGORICAL_PALETTE[2])
    render_chart(fig)


def _research_line_researchers_by_year(
    selected: str, articles_df: pd.DataFrame, dois_with_kw: set
) -> None:
    keyword_articles = articles_df[articles_df["doi"].isin(dois_with_kw)]
    kw_by_year = researchers_by_year(keyword_articles)
    if kw_by_year.empty:
        st.info("Sem anos válidos para este gráfico.")
        return

    fig = source_bars(kw_by_year, "year", total_line=True)
    fig.update_layout(
        hovermode="x unified",
        xaxis_title="Ano de publicação",
        yaxis_title="Pesquisadores distintos",
    )
    render_chart(
        fig,
        caption=f"Pesquisadores distintos que publicaram em '{selected}' a cada ano, por base.",
    )


def _research_line_researchers_cumulative(
    selected: str, articles_df: pd.DataFrame, dois_with_kw: set
) -> None:
    keyword_articles = articles_df[articles_df["doi"].isin(dois_with_kw)]
    kw_cum = cumulative_researchers(keyword_articles)
    if kw_cum.empty:
        st.info("Sem anos válidos para o acumulado.")
        return

    fig = source_lines(
        kw_cum,
        "year",
        title=f"Pesquisadores acumulados em '{selected}'",
        y_title="Pesquisadores acumulados",
    )
    fig.update_layout(xaxis_title="Ano de publicação")
    render_chart(
        fig,
        caption="Total acumulado de pesquisadores distintos que já publicaram em "
        f"'{selected}' até cada ano ({int(kw_cum['total'].iloc[-1]):,} ao final do período).",
    )


def _research_line_articles(
    articles_df: pd.DataFrame, scoped_authors: pd.DataFrame, selected: str
) -> None:
    top_dois = scoped_authors["doi"].unique()
    subset = articles_df[articles_df["doi"].isin(top_dois)]
    if "citation_count" in subset.columns:
        subset = subset.sort_values("citation_count", ascending=False, na_position="last")
    article_table(
        subset,
        ["title", "year", "venue", "source", "citation_count", "doi"],
        download_key=f"lideres_{selected.replace(' ', '_')}",
    )


def _author_keyword_selector(author_rows: pd.DataFrame) -> str | None:
    """Shared author selector for the "Perfil de Palavras-Chave"/"Mudança de Foco" sub-tabs."""
    st.subheader("🏷️ Perfil de palavras-chave por autor")
    counts = (
        author_rows.groupby("author_display")["doi"].nunique()
        if "doi" in author_rows.columns
        else author_rows.groupby("author_display").size()
    )
    eligible = counts[counts >= 3].sort_values(ascending=False)
    if eligible.empty:
        st.info("Nenhum autor com pelo menos 3 artigos nesta camada.")
        return None

    selected_author = st.selectbox(
        "Selecione um autor (mínimo 3 artigos):", options=eligible.index.tolist()
    )
    return selected_author or None


def _author_keyword_working(
    selected_author: str, author_rows: pd.DataFrame, articles_df: pd.DataFrame
) -> pd.DataFrame | None:
    author_dois = set(
        author_rows.loc[author_rows["author_display"] == selected_author, "doi"].dropna()
    )
    subset = articles_df[articles_df["doi"].isin(author_dois)]
    kw_exploded = explode_keywords(subset)
    if kw_exploded.empty:
        st.info(f"Nenhuma palavra-chave registrada para {selected_author}.")
        return None

    working = kw_exploded.copy()
    working["year"] = valid_years(working)
    return working.dropna(subset=["year"]).astype({"year": int})


def _author_keyword_overview(selected_author: str, working: pd.DataFrame) -> None:
    top_terms = working["keyword"].value_counts().head(10)
    fig = topn_hbar(
        top_terms,
        title=f"Palavras-chave dominantes de {selected_author}",
        x_title="Quantidade de menções",
        y_title="Palavra-chave",
    )
    render_chart(fig)


def _author_keyword_shift(working: pd.DataFrame) -> None:
    if working["year"].nunique() < 2:
        st.info("Anos insuficientes para comparar início vs. fim da carreira no corpus.")
        return

    split_year = int(working["year"].median())
    early = working[working["year"] <= split_year]["keyword"].value_counts()
    late = working[working["year"] > split_year]["keyword"].value_counts()
    all_terms = set(early.index) | set(late.index)
    compare = pd.DataFrame(
        {
            "early": early.reindex(all_terms, fill_value=0),
            "late": late.reindex(all_terms, fill_value=0),
        }
    )
    compare = (
        compare[(compare["early"] + compare["late"]) > 0]
        .sort_values("late", ascending=False)
        .head(10)
    )
    fig = go.Figure()
    fig.add_bar(
        x=compare.index,
        y=compare["early"],
        name=f"até {split_year}",
        marker_color=CATEGORICAL_PALETTE[0],
    )
    fig.add_bar(
        x=compare.index,
        y=compare["late"],
        name=f"após {split_year}",
        marker_color=CATEGORICAL_PALETTE[2],
    )
    fig.update_layout(
        barmode="group",
        title="Mudança de foco: início vs. fim da carreira no corpus",
        xaxis_title="Palavra-chave",
        yaxis_title="Menções no período",
    )
    render_chart(fig)
