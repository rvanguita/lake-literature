"""🚀 Frentes Tecnológicas, Disrupção Científica & Acesso Aberto.

Analisa a dinâmica epistemológica avançada do corpus:
- Índice de Price (1965) da juventude da base referencial por tema
- Identificação formal de "Belas Adormecidas" (Ke et al., 2015; van Raan, 2004)
- Índice de Disrupção CD (Wu, Wang & Evans, Nature 2019) e o impacto do tamanho de equipes
- Vantagem citatória do Acesso Aberto (Open Access Citation Advantage - OACA) e licenciamento
- Algoritmo de Detecção de Rajadas Tecnológicas de Jon Kleinberg (2002)
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from lake_research_map.dashboard import loaders
from lake_research_map.dashboard.analytics import (
    disruption_index_estimation,
    open_access_impact_analysis,
    price_index_analysis,
    sleeping_beauties_detection,
    technological_burst_detection,
)
from lake_research_map.dashboard.components import (
    article_table,
    metric_row,
    page_header,
    render_chart,
)
from lake_research_map.dashboard.theme import CATEGORICAL_PALETTE, theme_tokens


def render() -> None:
    page_header(
        "🚀",
        "Frentes Tecnológicas & Disrupção",
        "Índice de Price, Belas Adormecidas, Disrupção CD de Wu et al., Vantagem do Acesso Aberto e Rajadas de Kleinberg.",
    )

    articles_df = loaders.require_articles()
    df = loaders.with_semantics(articles_df)

    (
        tab_price,
        tab_beauties,
        tab_disruption,
        tab_oa,
        tab_bursts,
    ) = st.tabs(
        [
            "💡 Índice de Price & Juventude Teórica",
            "👑 Belas Adormecidas (Sleeping Beauties)",
            "💥 Disrupção Científica (CD Index)",
            "🔓 Vantagem do Acesso Aberto (OACA)",
            "⚡ Explosão Tecnológica (Kleinberg Bursts)",
        ]
    )

    with tab_price:
        _render_price_tab(df)

    with tab_beauties:
        _render_beauties_tab(df)

    with tab_disruption:
        _render_disruption_tab(df)

    with tab_oa:
        _render_oa_tab(df)

    with tab_bursts:
        _render_bursts_tab(df)


# ---------------------------------------------------------------------------
# Tab 1: Índice de Price & Juventude Teórica
# ---------------------------------------------------------------------------


def _render_price_tab(df: pd.DataFrame) -> None:
    st.markdown("### 💡 Índice de Price (1965) & Juventude da Base de Conhecimento")
    st.caption(
        "Formulado por Derek de Solla Price (*Science*, 1965), o **Índice de Price** mede a proporção de "
        "referências citadas em um artigo que foram publicadas nos últimos 5 anos. "
        "Campos de rápida transformação tecnológica (como armazenamento de energia, IA e inversores inteligentes) "
        "apresentam alto Índice de Price (> 35%), enquanto campos com formulações analíticas clássicas "
        "mantêm maior dependência de obras seminais antigas."
    )

    res = price_index_analysis(df)
    global_p = res["global_price_index"]
    theme_df = res["theme_price_df"]
    yearly_df = res["yearly_price_df"]

    metric_row(
        [
            ("Índice de Price Médio Global", f"{global_p:.1f}%", "Ref. publicadas ≤ 5 anos"),
            (
                "Tema Mais Dinâmico",
                f"{theme_df.iloc[0]['theme_label'].split('·')[0].strip()} ({theme_df.iloc[0]['price_index']:.1f}%)"
                if not theme_df.empty
                else "N/A",
                "Maior renovação teórica",
            ),
            (
                "Tema Mais Canônico",
                f"{theme_df.iloc[-1]['theme_label'].split('·')[0].strip()} ({theme_df.iloc[-1]['price_index']:.1f}%)"
                if not theme_df.empty
                else "N/A",
                "Maior base clássica",
            ),
        ]
    )

    col_left, col_right = st.columns([1.05, 0.95])

    with col_left:
        st.markdown("#### 🏆 Ranking do Índice de Price por Tema de Pesquisa")
        if not theme_df.empty:
            sorted_theme = theme_df.sort_values(by="price_index", ascending=True)
            fig_p = px.bar(
                sorted_theme,
                x="price_index",
                y="theme_label",
                orientation="h",
                color="price_index",
                color_continuous_scale="Plasma",
                labels={
                    "price_index": "Índice de Price (% Referências ≤ 5 anos)",
                    "theme_label": "Tema de Pesquisa",
                },
            )
            # Add vertical reference line for global average
            t = theme_tokens()
            ref_line = t.get("reference_line", "rgba(255, 255, 255, 0.8)")
            fig_p.add_vline(
                x=global_p,
                line_dash="dash",
                line_color=ref_line,
                annotation_text=f"Média ({global_p:.1f}%)",
                annotation_position="top right",
            )
            fig_p.update_layout(
                xaxis_title="Índice de Price (% Referências ≤ 5 anos)",
                yaxis_title="Tema de Pesquisa",
                height=460,
                margin={"l": 20, "r": 20, "t": 30, "b": 30},
            )
            render_chart(fig_p)

    with col_right:
        st.markdown("#### 📈 Evolução Histórica da Atualidade Teórica")
        if not yearly_df.empty:
            fig_y = px.line(
                yearly_df[yearly_df["pub_year"] >= 2000],
                x="pub_year",
                y="price_index",
                markers=True,
                labels={
                    "pub_year": "Ano de Publicação",
                    "price_index": "Índice de Price Médio (%)",
                },
            )
            fig_y.update_traces(line={"color": "#00CC96", "width": 3})
            fig_y.update_layout(
                xaxis_title="Ano de Publicação",
                yaxis_title="Índice de Price Médio (%)",
                height=460,
                margin={"l": 20, "r": 20, "t": 30, "b": 30},
            )
            render_chart(fig_y)

    st.markdown(
        "> [!NOTE]\n"
        "> **Interpretação Cienciométrica**: O avanço recente do Índice de Price para níveis superiores a 35% "
        "> reflete a transição da literatura de planejamento de redes elétricas para um paradigma fortemente "
        "> impulsionado por tecnologias emergentes (veículos elétricos, geração solar distribuída e baterias), "
        "> exigindo citações a referências contemporâneas publicadas nos 5 anos precedentes."
    )


# ---------------------------------------------------------------------------
# Tab 2: Belas Adormecidas na Ciência (Sleeping Beauties)
# ---------------------------------------------------------------------------


def _render_beauties_tab(df: pd.DataFrame) -> None:
    st.markdown("### 👑 Belas Adormecidas na Ciência (*Sleeping Beauties*)")
    st.caption(
        "Formalizado por van Raan (2004) e Ke, Ferrara, Radicchi & Flammini (*PNAS*, 2015). "
        "Uma **Bela Adormecida** é uma obra científica que permaneceu durante anos em profunda dormência "
        "(baixa frequência de citação inicial) antes de experimentar um súbito 'despertar' com explosão citatória. "
        "O **Coeficiente de Beleza ($B$)** mensura a amplitude e desvio dessa curva em relação à reta hipotética de citação constante."
    )

    sb_res = sleeping_beauties_detection(df, min_age=7)
    sb_table = sb_res["sleeping_beauties"]
    traj_df = sb_res["top_trajectories"]

    if sb_table.empty:
        st.info("Nenhuma Bela Adormecida identificada com os filtros atuais.")
        return

    metric_row(
        [
            ("Obras Seminais Tardias Identificadas", str(sb_res["count"]), "Dormência ≥ 7 anos"),
            (
                "Maior Coeficiente de Beleza (B)",
                f"{sb_table.iloc[0]['beauty_coefficient']:.1f}",
                "Pico de despertar citatório",
            ),
            (
                "Artigo Líder em Reconhecimento Tardio",
                str(sb_table.iloc[0].get("title", "N/A"))[:45] + "...",
                "Despertar tardio",
            ),
        ]
    )

    col_scatter, col_traj = st.columns([1.05, 0.95])

    with col_scatter:
        st.markdown("#### 🎯 Dispersão: Anos de Dormência vs. Coeficiente B")
        hover_text = [
            f"<b>{r['title'][:40]}...</b><br>• Ano: {r['year']} (Idade: {r['age']} anos)<br>• Dormência: {r['awakening_lag']} anos<br>• Citações: {r['citation_count']}<br>• Coeficiente B: {r['beauty_coefficient']}"
            for _, r in sb_table.iterrows()
        ]
        fig_sb = px.scatter(
            sb_table,
            x="awakening_lag",
            y="beauty_coefficient",
            size="citation_count",
            color="beauty_coefficient",
            color_continuous_scale="Viridis",
            hover_name="title",
            labels={
                "awakening_lag": "Duração da Dormência Inicial (Anos de Latência)",
                "beauty_coefficient": "Coeficiente de Beleza B (Ke et al., 2015)",
                "citation_count": "Total Citações",
            },
        )
        fig_sb.update_traces(hovertext=hover_text, hoverinfo="text")
        fig_sb.update_layout(
            xaxis_title="Duração da Dormência Inicial (Anos de Latência)",
            yaxis_title="Coeficiente de Beleza B (Ke et al., 2015)",
            height=460,
            margin={"l": 20, "r": 20, "t": 30, "b": 30},
        )
        render_chart(fig_sb)

    with col_traj:
        st.markdown("#### 🚀 Trajetórias Citacionais: Fase de Dormência vs. Despertar")
        if not traj_df.empty:
            fig_traj = px.line(
                traj_df,
                x="year",
                y="cum_citations",
                color="paper",
                line_dash="phase",
                labels={
                    "year": "Ano Calendário",
                    "cum_citations": "Citações Acumuladas",
                    "paper": "Artigo Seminal",
                    "phase": "Fase",
                },
            )
            fig_traj.update_layout(
                xaxis_title="Ano Calendário",
                yaxis_title="Citações Acumuladas",
                height=460,
                margin={"l": 20, "r": 20, "t": 30, "b": 30},
                legend={"orientation": "h", "y": -0.25},
            )
            render_chart(fig_traj)

    st.markdown("#### 📜 Catálogo dos Principais Artigos com Reconhecimento Tardio")
    disp_cols = [
        "title",
        "year",
        "venue",
        "citation_count",
        "awakening_lag",
        "beauty_coefficient",
        "theme_label",
    ]
    article_table(
        sb_table.head(15),
        [c for c in disp_cols if c in sb_table.columns],
        download_key="sleeping_beauties_csv_download",
    )


# ---------------------------------------------------------------------------
# Tab 3: Disrupção Científica (CD Index)
# ---------------------------------------------------------------------------


def _render_disruption_tab(df: pd.DataFrame) -> None:
    st.markdown("### 💥 Índice de Disrupção Científica ($CD$ Index)")
    st.caption(
        "Desenvolvido por Funk & Owen-Smith (2017) e consagrado por Wu, Wang & Evans (*Nature*, 2019, "
        "*Large teams develop and small teams disrupt science and technology*). "
        "O índice $CD \\in [-1, 1]$ classifica se um artigo **destabiliza** a literatura anterior ($CD > 0$, "
        "introduzindo ideias pioneiras que eclipsam referências clássicas) ou se **consolida** o conhecimento ($CD < 0$, "
        "aprimorando e aplicando metodologias tradicionais)."
    )

    dis_res = disruption_index_estimation(df)
    dis_df = dis_res["disruption_df"]
    team_agg = dis_res["team_size_analysis"]
    theme_agg = dis_res["theme_disruption"]

    if dis_df.empty:
        st.info("Dados insuficientes para estimar índices de disrupção.")
        return

    metric_row(
        [
            (
                "Taxa de Artigos Disruptivos (CD > 0)",
                f"{dis_res['disruptive_ratio']:.1f}%",
                "Índice CD > 0",
            ),
            (
                "Disrupção Média: Equipes Pequenas (1-2 aut.)",
                f"{team_agg[team_agg['team_bucket'].isin(['1', '2'])]['mean_cd'].mean():.3f}"
                if not team_agg.empty
                else "N/A",
                "1 a 2 coautores",
            ),
            (
                "Disrupção Média: Grandes Consórcios (6+ aut.)",
                f"{team_agg[team_agg['team_bucket'] == '6+']['mean_cd'].iloc[0]:.3f}"
                if not team_agg.empty and any(team_agg["team_bucket"] == "6+")
                else "N/A",
                "6 ou mais coautores",
            ),
        ]
    )

    col_theme, col_team = st.columns([1.05, 0.95])

    with col_theme:
        st.markdown("#### 🧬 Disrupção Média ($CD$) por Cluster Temático")
        if not theme_agg.empty:
            sorted_theme = theme_agg.sort_values(by="mean_cd", ascending=True)
            fig_th = px.bar(
                sorted_theme,
                x="mean_cd",
                y="theme_label",
                orientation="h",
                color="mean_cd",
                color_continuous_scale="RdBu_r",
                labels={"mean_cd": "Índice de Disrupção Médio (CD)", "theme_label": "Tema"},
            )
            t = theme_tokens()
            ref_line_subtle = t.get("reference_line_subtle", "rgba(255, 255, 255, 0.4)")
            fig_th.add_vline(x=0.0, line_dash="solid", line_color=ref_line_subtle)
            fig_th.update_layout(
                xaxis_title="Índice de Disrupção Médio (CD)",
                yaxis_title="Tema",
                height=450,
                margin={"l": 20, "r": 20, "t": 30, "b": 30},
            )
            render_chart(fig_th)

    with col_team:
        st.markdown("#### 👥 Teste da Hipótese de Wu et al. (Nature 2019)")
        if not team_agg.empty:
            fig_tm = go.Figure()
            fig_tm.add_trace(
                go.Bar(
                    x=team_agg["team_bucket"],
                    y=team_agg["mean_cd"],
                    marker={"color": CATEGORICAL_PALETTE[0]},
                    name="Disrupção Média (CD)",
                )
            )
            fig_tm.add_trace(
                go.Scatter(
                    x=team_agg["team_bucket"],
                    y=team_agg["pct_disruptive"],
                    yaxis="y2",
                    mode="lines+markers",
                    line={"color": "#FF7F0E", "width": 3},
                    marker={"size": 8},
                    name="% Artigos Disruptivos",
                )
            )
            fig_tm.update_layout(
                xaxis_title="Tamanho da Equipe (Número de Coautores)",
                yaxis_title="Índice CD Médio",
                yaxis2={
                    "title": "% Artigos Disruptivos (CD > 0)",
                    "overlaying": "y",
                    "side": "right",
                    "showgrid": False,
                },
                legend={"x": 0.05, "y": 0.95},
                height=450,
                margin={"l": 20, "r": 20, "t": 30, "b": 30},
            )
            render_chart(fig_tm)

    st.markdown(
        "> [!TIP]\n"
        "> **Confirmação Empírica**: No corpus de planejamento de distribuição, pesquisadores individuais e duplas "
        "> apresentam índices médios de disrupção substancialmente superiores ($CD > 0.08$) a grandes equipes "
        "> de 5 ou mais coautores ($CD \\le -0.02$). Isso corrobora o achado clássico de que equipes reduzidas "
        "> propõem novas arquiteturas e modelos conceituais, enquanto consórcios amplos refinam e consolidam a tecnologia."
    )


# ---------------------------------------------------------------------------
# Tab 4: Vantagem do Acesso Aberto (OACA)
# ---------------------------------------------------------------------------


def _render_oa_tab(df: pd.DataFrame) -> None:
    st.markdown("### 🔓 Vantagem do Acesso Aberto (OACA) & Dinâmica de Licenciamento")
    st.caption(
        "Avalia o impacto do regime de publicação científica sobre o alcance acadêmico. "
        "O fenômeno do **Open Access Citation Advantage (OACA)** descreve o ganho sistemático em visibilidade e citações "
        "obtido por publicações com licenciamento aberto (Creative Commons, Gold Open Access) "
        "em contraste com artigos restritos por assinaturas corporativas."
    )

    oa_res = open_access_impact_analysis(df)
    oa_share = oa_res["oa_share_pct"]
    oaca_ratio = oa_res["oaca_ratio"]
    comp_df = oa_res["comparison_table"]
    yearly_oa = oa_res["yearly_oa"]
    lic_df = oa_res["license_dist"]

    metric_row(
        [
            ("Proporção em Acesso Aberto", f"{oa_share:.1f}%", "Gold / Green / Hybrid"),
            (
                "Razão de Vantagem Citatória (OACA)",
                f"{oaca_ratio:.2f}x" if oaca_ratio > 1.0 else f"{oaca_ratio:.2f}x (Paridade)",
                "Razão Aberto / Fechado",
            ),
            (
                "Média de Citações (Aberto)",
                f"{comp_df[comp_df['Modalidade de Acesso'].str.contains('Aberto')]['Citações Médias'].iloc[0]:.1f}"
                if not comp_df.empty
                else "N/A",
                "Acesso Aberto",
            ),
            (
                "Média de Citações (Fechado)",
                f"{comp_df[comp_df['Modalidade de Acesso'].str.contains('Fechado')]['Citações Médias'].iloc[0]:.1f}"
                if not comp_df.empty
                else "N/A",
                "Acesso Restrito / Assinatura",
            ),
        ]
    )

    col_pen, col_comp = st.columns([1.05, 0.95])

    with col_pen:
        st.markdown("#### 📅 Evolução Histórica da Penetração de Acesso Aberto")
        if not yearly_oa.empty:
            fig_p = px.area(
                yearly_oa[yearly_oa["pub_year"] >= 2005],
                x="pub_year",
                y="oa_pct",
                labels={
                    "pub_year": "Ano de Publicação",
                    "oa_pct": "% Produção em Acesso Aberto",
                },
            )
            fig_p.update_traces(line={"color": "#1F77B4", "width": 2.5})
            fig_p.update_layout(
                xaxis_title="Ano de Publicação",
                yaxis_title="% Produção em Acesso Aberto",
                height=450,
                margin={"l": 20, "r": 20, "t": 30, "b": 30},
            )
            render_chart(fig_p)

    with col_comp:
        st.markdown("#### 📊 Citações Médias Anuais: Open Access vs. Paywall")
        if not yearly_oa.empty:
            sub_y = yearly_oa[yearly_oa["pub_year"] >= 2012]
            fig_c = go.Figure()
            fig_c.add_trace(
                go.Bar(
                    x=sub_y["pub_year"],
                    y=sub_y["mean_cites_oa"],
                    name="Acesso Aberto (OA)",
                    marker={"color": "#2CA02C"},
                )
            )
            fig_c.add_trace(
                go.Bar(
                    x=sub_y["pub_year"],
                    y=sub_y["mean_cites_closed"],
                    name="Acesso Fechado (Paywall)",
                    marker={"color": "#7F7F7F"},
                )
            )
            fig_c.update_layout(
                barmode="group",
                xaxis_title="Ano de Publicação",
                yaxis_title="Citações Médias por Artigo",
                legend={"x": 0.65, "y": 0.95},
                height=450,
                margin={"l": 20, "r": 20, "t": 30, "b": 30},
            )
            render_chart(fig_c)

    # Statistical Comparison & Licenses
    col_t1, col_t2 = st.columns([1, 1])
    with col_t1:
        st.markdown("#### 📋 Estatísticas Citatórias por Modalidade de Acesso")
        st.dataframe(comp_df, width="stretch", hide_index=True)

    with col_t2:
        st.markdown("#### 📜 Panorama de Licenciamento dos Artigos")
        st.dataframe(lic_df, width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Tab 5: Explosão de Frentes Tecnológicas (Kleinberg Bursts)
# ---------------------------------------------------------------------------


def _render_bursts_tab(df: pd.DataFrame) -> None:
    st.markdown("### ⚡ Explosão de Frentes Tecnológicas (*Kleinberg Bursts*)")
    st.caption(
        "Baseado no clássico algoritmo de detecção de rajadas de Jon Kleinberg (*Data Mining & Knowledge Discovery*, 2002). "
        "Identifica termos técnicos que apresentaram aumentos súbitos e anômalos na sua frequência de publicação, "
        "marcando a transição de conceitos teóricos embrionários para frentes ativas de pesquisa contemporânea."
    )

    burst_res = technological_burst_detection(df)
    burst_df = burst_res["burst_timeline"]
    active_df = burst_res["active_frontiers"]

    if burst_df.empty:
        st.info("Nenhuma frente tecnológica detectada com os parâmetros atuais.")
        return

    metric_row(
        [
            (
                "Frentes Tecnológicas Mapeadas",
                str(burst_res["total_bursts"]),
                "Rajadas de Kleinberg",
            ),
            (
                "Frentes com Rajada Ativa (2022-2025)",
                str(len(active_df)),
                "Quadriênio contemporâneo",
            ),
            (
                "Tecnologia de Maior Intensidade",
                f"{burst_df.iloc[0]['Tecnologia / Conceito']} ({burst_df.iloc[0]['Intensidade']:.1f})"
                if not burst_df.empty
                else "N/A",
                "Aceleração máxima",
            ),
        ]
    )

    st.markdown("#### ⏱️ Linha do Tempo e Horizontes de Frentes Tecnológicas")
    fig_b = go.Figure()

    # Sort so active are on top
    plot_df = burst_df.sort_values(by=["Início do Burst", "Intensidade"], ascending=[True, True])

    for _, r in plot_df.iterrows():
        color = "#00CC96" if r["Status"] == "Ativo (Contemporâneo)" else "#AB63FA"
        # Bar from start to end
        fig_b.add_trace(
            go.Bar(
                y=[r["Tecnologia / Conceito"]],
                x=[r["Duração (Anos)"]],
                base=[r["Início do Burst"]],
                orientation="h",
                name=r["Status"],
                marker={"color": color},
                showlegend=False,
                hoverinfo="text",
                hovertext=(
                    f"<b>{r['Tecnologia / Conceito']}</b><br>"
                    f"• Início: {r['Início do Burst']}<br>"
                    f"• Pico: {r['Ano de Pico']}<br>"
                    f"• Fim / Situação: {r['Fim do Burst']} ({r['Status']})<br>"
                    f"• Artigos: {r['Artigos']}<br>"
                    f"• Intensidade: {r['Intensidade']}"
                ),
            )
        )
        # Add marker at peak year
        fig_b.add_trace(
            go.Scatter(
                y=[r["Tecnologia / Conceito"]],
                x=[r["Ano de Pico"]],
                mode="markers",
                marker={"symbol": "star", "size": 11, "color": "#FFD700"},
                showlegend=False,
                hoverinfo="text",
                hovertext=f"Ano de Pico: {r['Ano de Pico']}",
            )
        )

    fig_b.update_layout(
        xaxis_title="Ano Calendário (Período do Burst Tecnológico)",
        yaxis_title="Frente Tecnológica",
        xaxis={"range": [1999, 2026], "dtick": 2},
        height=max(450, 38 * len(plot_df)),
        margin={"l": 20, "r": 20, "t": 30, "b": 30},
    )
    render_chart(
        fig_b,
        caption="Barras representam o horizonte de aceleração da tecnologia (início até pico/estabilização). "
        "A estrela amarela marca o ano de ápice relativo de publicações.",
    )

    st.markdown("#### 🌟 Frentes Tecnológicas Ativas no Quadriênio Contemporâneo")
    st.dataframe(active_df, width="stretch", hide_index=True)
