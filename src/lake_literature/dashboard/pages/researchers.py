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
    explode_authors,
    explode_keywords,
    gini_coefficient,
    lorenz_curve,
    output_impact_correlation,
    valid_years,
)
from lake_literature.dashboard.charts import lorenz_chart, topn_hbar
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


@st.cache_data(
    ttl=60, hash_funcs={pd.DataFrame: lambda df: df.to_json(orient="split", default_handler=str)}
)
def _author_table(articles_df: pd.DataFrame) -> pd.DataFrame:
    """Explode authors, canonicalize identity, and keep one display name per key."""
    exploded = explode_authors(articles_df)
    if exploded.empty:
        return exploded
    exploded["author_key"] = exploded["author"].apply(canonical_author)
    exploded = exploded[exploded["author_key"] != ""]
    display_names = exploded.groupby("author_key")["author"].apply(author_display_name)
    exploded["author_display"] = exploded["author_key"].map(display_names)
    return exploded


@st.cache_data(
    ttl=60, hash_funcs={pd.DataFrame: lambda df: df.to_json(orient="split", default_handler=str)}
)
def _author_year_matrix_cached(articles_df: pd.DataFrame) -> pd.DataFrame:
    return author_year_matrix(articles_df)


def render() -> None:
    page_header(
        "👥",
        "Pesquisadores",
        "Produção, colaboração e linhas de pesquisa dos autores do corpus.",
    )

    articles_df = loaders.require_articles()
    author_rows = _author_table(articles_df)

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
        _top_authors(author_rows)

    with tab_production:
        _production_heatmap(author_rows)
        st.divider()
        _emerging_vs_established(author_rows)

    with tab_collab:
        _coauthorship_network(author_rows)

    with tab_explore:
        _research_line_leaders(author_rows, articles_df)
        st.divider()
        _author_keyword_profile(author_rows, articles_df)

    with tab_stats:
        matrix = _full_output_table(articles_df)
        st.divider()
        _concentration_analysis(matrix)
        st.divider()
        _productivity_trend(matrix)
        st.divider()
        _volume_vs_impact(author_rows)


def _top_authors(author_rows: pd.DataFrame) -> None:
    st.subheader("✍️ Autores mais prolíficos (canonicalizado)")
    counts = (
        author_rows.groupby("author_display")["doi"].nunique()
        if "doi" in author_rows.columns
        else author_rows.groupby("author_display").size()
    )
    top = counts.sort_values(ascending=False).head(15)
    modal_source = (
        author_rows.groupby("author_display")["source"].agg(lambda s: s.mode().iat[0])
        if "source" in author_rows.columns
        else None
    )
    fig = topn_hbar(top, color_by=modal_source, x_title="Artigos")
    fig.update_traces(hovertemplate="<b>%{y}</b><br>%{x:,} artigos<extra></extra>")
    render_chart(fig)


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
        labels={"x": "Ano", "y": "", "color": "Artigos"},
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
                "Pearson": stats["pearson"],
                "Spearman": stats["spearman"],
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
    matrix = _author_year_matrix_cached(articles_df)
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
    fig.update_layout(
        xaxis=dict(visible=False, scaleanchor="y", scaleratio=1),
        yaxis=dict(visible=False),
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


def _research_line_leaders(author_rows: pd.DataFrame, articles_df: pd.DataFrame) -> None:
    st.subheader("🔎 Quem lidera esta linha de pesquisa")
    kw_exploded = explode_keywords(articles_df)
    if kw_exploded.empty:
        st.info("Coluna 'keywords' não disponível nesta camada.")
        return

    top_keywords = kw_exploded["keyword"].value_counts().head(60).index.tolist()
    selected = st.selectbox("Selecione uma palavra-chave:", options=top_keywords)
    if not selected:
        return

    dois_with_kw = set(kw_exploded.loc[kw_exploded["keyword"] == selected, "doi"].dropna())
    scoped_authors = (
        author_rows[author_rows["doi"].isin(dois_with_kw)]
        if "doi" in author_rows.columns
        else author_rows.iloc[0:0]
    )
    if scoped_authors.empty:
        st.info("Nenhum autor associado a esse termo nesta camada.")
        return

    leaders = (
        scoped_authors.groupby("author_display")["doi"]
        .nunique()
        .sort_values(ascending=False)
        .head(10)
    )
    col_leaders, col_trend = st.columns(2)
    with col_leaders:
        fig = topn_hbar(
            leaders, title=f"Autores mais produtivos em '{selected}'", x_title="Artigos"
        )
        render_chart(fig)
    with col_trend:
        trend_df = scoped_authors.copy()
        trend_df["year"] = valid_years(trend_df)
        trend_df = trend_df.dropna(subset=["year"]).astype({"year": int})
        if trend_df.empty:
            st.info("Sem anos válidos para a trajetória.")
        else:
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

    top_dois = scoped_authors["doi"].unique()
    subset = articles_df[articles_df["doi"].isin(top_dois)]
    if "citation_count" in subset.columns:
        subset = subset.sort_values("citation_count", ascending=False, na_position="last")
    article_table(
        subset,
        ["title", "year", "venue", "source", "citation_count", "doi"],
        download_key=f"lideres_{selected.replace(' ', '_')}",
    )


def _author_keyword_profile(author_rows: pd.DataFrame, articles_df: pd.DataFrame) -> None:
    st.subheader("🏷️ Perfil de palavras-chave por autor")
    counts = (
        author_rows.groupby("author_display")["doi"].nunique()
        if "doi" in author_rows.columns
        else author_rows.groupby("author_display").size()
    )
    eligible = counts[counts >= 3].sort_values(ascending=False)
    if eligible.empty:
        st.info("Nenhum autor com pelo menos 3 artigos nesta camada.")
        return

    selected_author = st.selectbox(
        "Selecione um autor (mínimo 3 artigos):", options=eligible.index.tolist()
    )
    if not selected_author:
        return

    author_dois = set(
        author_rows.loc[author_rows["author_display"] == selected_author, "doi"].dropna()
    )
    subset = articles_df[articles_df["doi"].isin(author_dois)]
    kw_exploded = explode_keywords(subset)
    if kw_exploded.empty:
        st.info(f"Nenhuma palavra-chave registrada para {selected_author}.")
        return

    working = kw_exploded.copy()
    working["year"] = valid_years(working)
    working = working.dropna(subset=["year"]).astype({"year": int})
    top_terms = working["keyword"].value_counts().head(10)

    col_overall, col_shift = st.columns(2)
    with col_overall:
        fig = topn_hbar(
            top_terms, title=f"Palavras-chave dominantes de {selected_author}", x_title="Menções"
        )
        render_chart(fig)
    with col_shift:
        if working["year"].nunique() < 2:
            st.info("Anos insuficientes para comparar início vs. fim da carreira no corpus.")
        else:
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
                barmode="group", title="Mudança de foco: início vs. fim da carreira no corpus"
            )
            render_chart(fig)
