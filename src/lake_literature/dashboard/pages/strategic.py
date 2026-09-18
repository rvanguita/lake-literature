"""🌐 Cienciometria Estratégica & Síntese Epistêmica.

Aborda a estrutura conceitual do corpus através de metodologias avançadas de cienciometria
e ciência de dados: Diagrama Estratégico de Callon, Rede de Coocorrência de Palavras-Chave,
Proximidade Inter-Temática em R^384, Radar Multidimensional, Correlações Multivariadas,
Entropia de Shannon e Redes de Colaboração Internacional.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from lake_literature.dashboard import loaders
from lake_literature.dashboard.analytics import (
    callon_strategic_diagram,
    geographic_collaboration_stats,
    keyword_cooccurrence_graph,
    multivariate_correlation_matrix,
    shannon_thematic_entropy,
    thematic_centroids_similarity,
    thematic_radar_metrics,
)
from lake_literature.dashboard.components import (
    metric_row,
    page_header,
    render_chart,
)
from lake_literature.dashboard.theme import CATEGORICAL_PALETTE, theme_tokens


def render() -> None:
    page_header(
        "🌐",
        "Cienciometria Estratégica",
        "Paisagem epistêmica, dinâmica estrutural de temas, coocorrência conceitual e colaboração internacional.",
    )

    articles_df = loaders.require_articles()
    df = loaders.with_semantics(articles_df)

    embs_data = loaders.abstract_embeddings()
    dois, embeddings = embs_data if embs_data is not None else ([], None)

    (
        tab_callon,
        tab_cooccur,
        tab_proximity,
        tab_multivariate,
        tab_geo,
    ) = st.tabs(
        [
            "🧭 Diagrama de Callon",
            "🕸️ Rede de Coocorrência",
            "🗺️ Proximidade & Radar",
            "📊 Correlações & Entropia",
            "🌍 Geografia & Parcerias",
        ]
    )

    with tab_callon:
        _render_callon_tab(df, embeddings, dois)

    with tab_cooccur:
        _render_cooccurrence_tab(df)

    with tab_proximity:
        _render_proximity_tab(df, embeddings, dois)

    with tab_multivariate:
        _render_multivariate_tab(df)

    with tab_geo:
        _render_geography_tab(df)


def _render_callon_tab(
    df: pd.DataFrame, embeddings: np.ndarray | None, dois: list[str] | None
) -> None:
    st.markdown("### 🧭 Diagrama Estratégico de Callon (1991)")
    st.caption(
        "Mapeia a maturidade e o papel estrutural de cada tema científico cruzando a "
        "**Densidade Interna** (coesão conceitual dos artigos dentro do tema) com a "
        "**Centralidade Externa** (intensidade de conexões com os demais temas da literatura)."
    )

    if embeddings is None or not dois:
        st.info(
            "Embeddings vetoriais necessários para o Diagrama de Callon não encontrados na camada Gold."
        )
        return

    callon_res = callon_strategic_diagram(df, embeddings, dois)
    themes_df = callon_res["themes_df"]

    if themes_df.empty:
        st.warning("Dados temáticos insuficientes para o cálculo do Diagrama de Callon.")
        return

    # Visual Metric Row
    top_motor = themes_df[themes_df["quadrant"].str.contains("Motores")]["theme"].tolist()
    top_niche = themes_df[themes_df["quadrant"].str.contains("Especializados")]["theme"].tolist()
    top_trans = themes_df[themes_df["quadrant"].str.contains("Básicos")]["theme"].tolist()

    metric_row(
        [
            ("🚀 Temas Motores (Q1)", str(len(top_motor)), "Alta Centralidade & Densidade"),
            ("🔬 Temas Especializados (Q2)", str(len(top_niche)), "Nicho / Alta Coesão"),
            ("🧱 Temas Transversais (Q4)", str(len(top_trans)), "Pilares Fundamentais"),
            (
                "🎯 Densidade Mediana",
                f"{callon_res['median_density']:.3f}",
                f"Centralidade: {callon_res['median_centrality']:.3f}",
            ),
        ]
    )

    # 2D Callon Quadrant Scatter Plot
    fig = go.Figure()

    # Add quadrant shading or background zones
    x_min, x_max = themes_df["centrality_centered"].min(), themes_df["centrality_centered"].max()
    y_min, y_max = themes_df["density_centered"].min(), themes_df["density_centered"].max()
    pad_x = max(abs(x_min), abs(x_max)) * 1.35
    pad_y = max(abs(y_min), abs(y_max)) * 1.35

    # Center axes lines
    fig.add_vline(x=0, line_width=1.5, line_dash="dash", line_color="rgba(160, 160, 160, 0.6)")
    fig.add_hline(y=0, line_width=1.5, line_dash="dash", line_color="rgba(160, 160, 160, 0.6)")

    # Quadrant corner labels
    quadrant_labels = [
        (
            pad_x * 0.70,
            pad_y * 0.85,
            "<b>Q1: Temas Motores</b><br>(Alta Centralidade, Alta Densidade)",
            "rgba(46, 204, 113, 0.12)",
        ),
        (
            -pad_x * 0.70,
            pad_y * 0.85,
            "<b>Q2: Especializados / Nicho</b><br>(Baixa Centralidade, Alta Densidade)",
            "rgba(52, 152, 219, 0.12)",
        ),
        (
            -pad_x * 0.70,
            -pad_y * 0.85,
            "<b>Q3: Emergentes / Marginais</b><br>(Baixa Centralidade, Baixa Densidade)",
            "rgba(231, 76, 60, 0.12)",
        ),
        (
            pad_x * 0.70,
            -pad_y * 0.85,
            "<b>Q4: Básicos / Transversais</b><br>(Alta Centralidade, Baixa Densidade)",
            "rgba(241, 196, 15, 0.12)",
        ),
    ]

    for qx, qy, text, _ in quadrant_labels:
        fig.add_annotation(
            x=qx,
            y=qy,
            text=text,
            showarrow=False,
            font={"size": 12, "color": "gray"},
            align="center",
            bgcolor="rgba(128, 128, 128, 0.08)",
            bordercolor="rgba(128, 128, 128, 0.2)",
            borderpad=5,
        )

    # Theme bubbles
    for i, r in themes_df.iterrows():
        color = CATEGORICAL_PALETTE[i % len(CATEGORICAL_PALETTE)]
        marker_size = max(18, min(48, int(np.sqrt(r["n_articles"]) * 2.2)))

        hover = (
            f"<b>{r['theme']}</b><br>"
            f"• Quadrante: {r['quadrant']}<br>"
            f"• Artigos: {r['n_articles']:,}<br>"
            f"• Citações Médias: {r['mean_citations']:.1f}<br>"
            f"• Densidade Interna: {r['density']:.3f}<br>"
            f"• Centralidade Externa: {r['centrality']:.3f}<br>"
            f"• Margem de Relevância: {r['mean_margin']:.3f}"
        )

        t = theme_tokens()
        border_col = t.get("point_border", "#FFFFFF")
        text_col = t.get("chart_text", "#e5eefb")
        fig.add_trace(
            go.Scatter(
                x=[r["centrality_centered"]],
                y=[r["density_centered"]],
                mode="markers+text",
                marker={
                    "size": marker_size,
                    "color": color,
                    "line": {"width": 2, "color": border_col},
                    "opacity": 0.88,
                },
                text=[r["theme"].split("·")[0].strip()],
                textposition="top center",
                textfont={"size": 11, "color": text_col},
                name=r["theme"],
                hovertext=[hover],
                hoverinfo="text",
            )
        )

    fig.update_layout(
        title={"text": "Diagrama Estratégico de Callon — Espaço Vetorial R³⁸⁴", "x": 0.02},
        xaxis_title="Centralidade Externa Relativa (Interação com outros temas →)",
        yaxis_title="Densidade Interna Relativa (Coesão interna do tema ↑)",
        xaxis={"range": [-pad_x, pad_x], "zeroline": False},
        yaxis={"range": [-pad_y, pad_y], "zeroline": False},
        showlegend=False,
        height=580,
    )

    render_chart(fig)

    # Diagnostic Dataframe
    st.markdown("#### 📋 Diagnóstico Estratégico do Corpus por Tema")
    display_df = themes_df.copy()
    display_df = display_df.rename(
        columns={
            "theme": "Tema de Pesquisa",
            "quadrant": "Classificação Estratégica (Callon)",
            "n_articles": "Nº Artigos",
            "mean_citations": "Citações Médias",
            "mean_margin": "Margem Relevância",
            "density": "Densidade Interna",
            "centrality": "Centralidade Externa",
        }
    )
    cols_order = [
        "Tema de Pesquisa",
        "Classificação Estratégica (Callon)",
        "Nº Artigos",
        "Citações Médias",
        "Margem Relevância",
        "Densidade Interna",
        "Centralidade Externa",
    ]
    st.dataframe(
        display_df[cols_order].sort_values(by="Nº Artigos", ascending=False),
        hide_index=True,
        width="stretch",
    )


def _render_cooccurrence_tab(df: pd.DataFrame) -> None:
    st.markdown("### 🕸️ Rede de Coocorrência Conceitual (*Epistemic Backbone*)")
    st.caption(
        "Mapeia a arquitetura epistêmica do conhecimento: como os termos técnicos se associam nos mesmos "
        "artigos científicos. Ligações ponderadas pelo **Índice de Jaccard** com agrupamento de comunidades conceituais via **Louvain**."
    )

    col_ctrl1, col_ctrl2 = st.columns(2)
    top_n = col_ctrl1.slider(
        "Quantidade de Palavras-Chave no Grafo",
        min_value=20,
        max_value=70,
        value=35,
        step=5,
        key="cooccur_top_kws",
    )
    min_co = col_ctrl2.slider(
        "Coocorrência Mínima (Pares de artigos compartilhados)",
        min_value=2,
        max_value=12,
        value=3,
        step=1,
        key="cooccur_min_weight",
    )

    graph_data = keyword_cooccurrence_graph(df, min_cooccurrence=min_co, top_n_keywords=top_n)
    nodes = graph_data["nodes"]
    edges = graph_data["edges"]

    if not nodes:
        st.info(
            "Nenhuma conexão de palavras-chave atendeu ao limiar selecionado. Tente reduzir a coocorrência mínima."
        )
        return

    metric_row(
        [
            ("🏷️ Conceitos na Rede", str(len(nodes)), f"Top {top_n} termos"),
            ("🔗 Relações Conceituais", str(len(edges)), f"Coocorrência ≥ {min_co}"),
            ("🧬 Comunidades Epistêmicas", str(graph_data["n_communities"]), "Clusters Louvain"),
        ]
    )

    # Build Plotly Network Graph
    fig = go.Figure()

    # Draw edges
    for e in edges:
        width = max(1.0, min(5.0, e["jaccard"] * 18))
        hover_edge = f"Conexão: <b>{e['source']}</b> ↔ <b>{e['target']}</b><br>• Artigos em comum: {e['weight']}<br>• Índice Jaccard: {e['jaccard']:.3f}"
        fig.add_trace(
            go.Scatter(
                x=[e["x0"], e["x1"], None],
                y=[e["y0"], e["y1"], None],
                mode="lines",
                line={"width": width, "color": "rgba(100, 160, 240, 0.35)"},
                hoverinfo="text",
                hovertext=hover_edge,
                showlegend=False,
            )
        )

    # Draw nodes
    node_x = [n["x"] for n in nodes]
    node_y = [n["y"] for n in nodes]
    node_text = [n["id"] for n in nodes]
    node_size = [max(16, min(42, int(np.sqrt(n["count"]) * 3.8))) for n in nodes]
    node_color = [CATEGORICAL_PALETTE[n["community"] % len(CATEGORICAL_PALETTE)] for n in nodes]
    node_hover = [
        f"<b>{n['id'].upper()}</b><br>• Frequência no corpus: {n['count']} artigos<br>• Comunidade Semântica: #{n['community'] + 1}"
        for n in nodes
    ]

    t = theme_tokens()
    border_col = t.get("point_border", "#FFFFFF")
    text_col = t.get("chart_text", "#e5eefb")

    fig.add_trace(
        go.Scatter(
            x=node_x,
            y=node_y,
            mode="markers+text",
            marker={
                "size": node_size,
                "color": node_color,
                "line": {"width": 1.5, "color": border_col},
                "opacity": 0.95,
            },
            text=node_text,
            textposition="top center",
            textfont={"size": 10, "color": text_col},
            hoverinfo="text",
            hovertext=node_hover,
            showlegend=False,
        )
    )

    fig.update_layout(
        title={"text": "Grafo de Coocorrência Conceitual e Comunidades Semânticas", "x": 0.02},
        xaxis={"showgrid": False, "zeroline": False, "showticklabels": False},
        yaxis={"showgrid": False, "zeroline": False, "showticklabels": False},
        height=620,
    )

    render_chart(fig)


def _render_proximity_tab(
    df: pd.DataFrame, embeddings: np.ndarray | None, dois: list[str] | None
) -> None:
    st.markdown("### 🗺️ Proximidade Inter-Temática & Radar de Maturidade")
    st.caption(
        "Mede a distância e o alinhamento semântico entre os temas centrais do corpus em **384 dimensões**, "
        "e compara seus perfis multidimensionais de evolução e impacto."
    )

    if embeddings is None or not dois:
        st.info("Embeddings vetoriais necessários para a matriz de proximidade não encontrados.")
        return

    sim_df = thematic_centroids_similarity(df, embeddings, dois)
    if sim_df.empty:
        st.warning("Não foi possível computar a similaridade dos centróides temáticos.")
        return

    col_map, col_radar = st.columns([1.1, 0.9])

    with col_map:
        st.markdown("#### 📐 Similaridade Cosseno entre Centróides (8×8)")
        # Truncate theme names for clean heatmap display
        short_names = [t.split("·")[0].strip() for t in sim_df.index]
        short_sim = sim_df.copy()
        short_sim.index = short_names
        short_sim.columns = short_names

        fig_heat = px.imshow(
            short_sim,
            text_auto=".2f",
            aspect="auto",
            color_continuous_scale="Viridis",
            labels={"x": "Tema Alvo", "y": "Tema de Origem", "color": "Similaridade Cosseno"},
        )
        fig_heat.update_layout(
            xaxis_title="Tema Alvo",
            yaxis_title="Tema de Origem",
            height=480,
            margin={"l": 20, "r": 20, "t": 40, "b": 40},
        )
        render_chart(fig_heat)

    with col_radar:
        st.markdown("#### 🎯 Radar de Maturidade Multidimensional")
        radar_df = thematic_radar_metrics(df)
        if not radar_df.empty:
            themes_avail = radar_df["theme_label"].tolist()
            selected = st.multiselect(
                "Comparar Temas no Radar:",
                options=themes_avail,
                default=themes_avail[:3],
                key="radar_themes_select",
            )

            fig_radar = go.Figure()
            axes = [
                "Momentum Recente",
                "Densidade Teórica",
                "Impacto Citações",
                "Aderência Escopo",
                "Tamanho Equipe",
            ]
            score_cols = [
                "pct_recent_score",
                "mean_refs_score",
                "mean_citations_score",
                "mean_margin_score",
                "mean_authors_score",
            ]

            for idx, th in enumerate(selected):
                row = radar_df[radar_df["theme_label"] == th]
                if not row.empty:
                    values = [row[c].iloc[0] for c in score_cols]
                    values.append(values[0])  # close polar polygon
                    color = CATEGORICAL_PALETTE[idx % len(CATEGORICAL_PALETTE)]
                    fig_radar.add_trace(
                        go.Scatterpolar(
                            r=values,
                            theta=axes + [axes[0]],
                            fill="toself",
                            name=th.split("·")[0].strip(),
                            line={"color": color, "width": 2},
                            opacity=0.65,
                        )
                    )

            t = theme_tokens()
            fig_radar.update_layout(
                polar={
                    "bgcolor": "rgba(0,0,0,0)",
                    "radialaxis": {
                        "visible": True,
                        "range": [0, 100],
                        "showticklabels": False,
                        "gridcolor": t["grid"],
                        "linecolor": t["axis_line"],
                    },
                    "angularaxis": {
                        "tickfont": {
                            "color": t["chart_text"],
                            "size": 11,
                        },
                        "gridcolor": t["grid"],
                        "linecolor": t["axis_line"],
                    },
                },
                showlegend=True,
                height=480,
                margin={"l": 40, "r": 40, "t": 40, "b": 40},
                xaxis={"visible": False, "showticklabels": False},
                yaxis={"visible": False, "showticklabels": False},
            )
            render_chart(fig_radar)

    # Analytical Table of Dimensions
    st.markdown("#### 📊 Métricas Absolutas por Tema de Pesquisa")
    table_radar = radar_df[
        [
            "theme_label",
            "n_articles",
            "pct_recent",
            "mean_citations",
            "mean_refs",
            "mean_margin",
            "mean_authors",
        ]
    ].copy()
    table_radar["pct_recent"] = (table_radar["pct_recent"] * 100).round(1).astype(str) + "%"
    table_radar["mean_citations"] = table_radar["mean_citations"].round(1)
    table_radar["mean_refs"] = table_radar["mean_refs"].round(1)
    table_radar["mean_margin"] = table_radar["mean_margin"].round(3)
    table_radar["mean_authors"] = table_radar["mean_authors"].round(2)
    table_radar.columns = [
        "Tema",
        "Artigos",
        "Publicado ≥ 2021",
        "Citações Médias",
        "Referências Citadas",
        "Margem Relevância",
        "Autores / Artigo",
    ]
    st.dataframe(table_radar, hide_index=True, width="stretch")


def _render_multivariate_tab(df: pd.DataFrame) -> None:
    st.markdown("### 📊 Correlações Multivariadas & Entropia do Conhecimento")
    st.caption(
        "Investiga as interdependências estatísticas não-lineares (Spearman) entre atributos dos artigos e quantifica a "
        "evolução da **Entropia de Shannon** da diversidade temática ao longo das décadas."
    )

    col_corr, col_ent = st.columns([1.05, 0.95])

    with col_corr:
        st.markdown("#### 🔄 Matriz de Correlação de Postos (Spearman)")
        corr = multivariate_correlation_matrix(df)
        if not corr.empty:
            fig_corr = px.imshow(
                corr,
                text_auto=".2f",
                aspect="auto",
                color_continuous_scale="RdBu_r",
                zmin=-1,
                zmax=1,
                labels={"x": "Métrica", "y": "Métrica", "color": "Correlação (ρ)"},
            )
            fig_corr.update_layout(
                xaxis_title="Métrica",
                yaxis_title="Métrica",
                height=460,
                margin={"l": 20, "r": 20, "t": 30, "b": 30},
            )
            render_chart(fig_corr)

    with col_ent:
        st.markdown("#### 🧬 Entropia de Shannon da Diversidade Temática")
        ent_df = shannon_thematic_entropy(df, min_year=2000)
        if not ent_df.empty:
            fig_ent = go.Figure()
            fig_ent.add_trace(
                go.Scatter(
                    x=ent_df["year"],
                    y=ent_df["shannon_entropy"],
                    mode="lines+markers",
                    name="Entropia de Shannon (H)",
                    line={"color": "#00CC96", "width": 3},
                    marker={"size": 6},
                )
            )
            fig_ent.add_trace(
                go.Bar(
                    x=ent_df["year"],
                    y=ent_df["n_articles"],
                    name="Volume de Artigos",
                    yaxis="y2",
                    marker={"color": "rgba(99, 110, 250, 0.25)"},
                )
            )

            fig_ent.update_layout(
                title={"text": "Diversidade Temática ao Longo dos Anos", "x": 0.02},
                xaxis={"title": "Ano de Publicação"},
                yaxis={"title": "Entropia H (bits)", "range": [0, 3.2]},
                yaxis2={
                    "title": "Nº Artigos",
                    "overlaying": "y",
                    "side": "right",
                    "showgrid": False,
                },
                legend={"x": 0.02, "y": 0.98},
                height=460,
                margin={"l": 20, "r": 20, "t": 30, "b": 30},
            )
            render_chart(fig_ent)

    st.markdown(
        "> [!NOTE]\n"
        "> **Interpretação da Entropia**: O crescimento sustentado da Entropia de Shannon ($H$) demonstra que a literatura em "
        "> planejamento de distribuição de energia expandiu sua amplitude conceitual a partir de 2010, deixando de ser dominada "
        "> exclusivamente por algoritmos clássicos de subestações para integrar microrredes, resiliência climática, baterias e veículos elétricos."
    )


def _render_geography_tab(df: pd.DataFrame) -> None:
    st.markdown("### 🌍 Paisagem Geográfica & Colaboração Internacional")
    st.caption(
        "Mapeia a distribuição geográfica das publicações com metadados de afiliação de países (registros IEEE) "
        "e identifica as redes de cooperação científica bilateral transfronteiriça."
    )

    geo_stats = geographic_collaboration_stats(df)
    c_df = geo_stats["country_counts"]
    p_df = geo_stats["collaboration_pairs"]

    if c_df.empty:
        st.info("Nenhum metadado geográfico identificado no corpus atual.")
        return

    top_pair = p_df.iloc[0]["pair"] if not p_df.empty else "—"

    metric_row(
        [
            ("📑 Artigos com País Mapeado", str(geo_stats["total_with_country"]), "Filiações IEEE"),
            ("🌐 Países Distintos", str(len(c_df)), "Presença global"),
            (
                "🤝 Coautoria Internacional",
                f"{geo_stats['intl_pct']:.1f}%",
                f"{geo_stats['intl_papers']} artigos multinacionais",
            ),
            ("🥇 Maior Eixo Bilateral", top_pair, "Liderança de cooperação"),
        ]
    )

    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.markdown("#### 🏆 Top 15 Países Produtores")
        top_countries = c_df.head(15).iloc[::-1]
        fig_c = px.bar(
            top_countries,
            x="articles",
            y="country",
            orientation="h",
            color="articles",
            color_continuous_scale="Tealgrn",
            labels={"articles": "Artigos", "country": "País"},
        )
        fig_c.update_layout(height=480, margin={"l": 20, "r": 20, "t": 30, "b": 30})
        render_chart(fig_c)

    with col_right:
        st.markdown("#### 🤝 Principais Eixos de Cooperação Bilateral")
        if not p_df.empty:
            fig_p = px.bar(
                p_df.head(12).iloc[::-1],
                x="collaborations",
                y="pair",
                orientation="h",
                color="collaborations",
                color_continuous_scale="Purp",
                labels={"collaborations": "Artigos Conjuntos", "pair": "Eixo Bilateral"},
            )
            fig_p.update_layout(height=480, margin={"l": 20, "r": 20, "t": 30, "b": 30})
            render_chart(fig_p)
        else:
            st.info("Sem pares internacionais suficientes para exibição.")
