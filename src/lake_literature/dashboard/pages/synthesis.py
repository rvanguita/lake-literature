"""🔬 Evidências Metodológicas & Síntese Científica da Literatura.

Mapeia a taxonomia dos métodos matemáticos de otimização e espectro de complexidade (MILP, SOCP, MINLP, IA),
as funções-objetivo e formulações multi-critério (Pareto), os paradigmas de modelagem da incerteza (estocástica,
robusta, fuzzy, DRO), os horizontes temporais (expansão dinâmica vs. dias representativos), a validação em sistemas
elétricos de teste (IEEE 33, 69, 123-bus e redes reais), o ferramental de solvers computacionais (GAMS, CPLEX,
MATLAB, OpenDSS), a dinâmica de liderança científica (h-index, g-index, e-index, m-quotient de Hirsch),
a estilometria textual (Flesch-Kincaid / TTR) e a longevidade citacional (meia-vida e artigos evergreen).
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from lake_literature.dashboard import loaders
from lake_literature.dashboard.analytics import (
    author_impact_advanced_indices,
    author_m_quotient_analysis,
    benchmark_feeders_analysis,
    citation_longevity_and_decay,
    computational_solvers_analysis,
    mathematical_complexity_spectrum,
    objective_functions_taxonomy,
    optimization_methods_taxonomy,
    planning_time_horizons_analysis,
    text_readability_and_stylometrics,
    uncertainty_paradigms_analysis,
)
from lake_literature.dashboard.components import (
    article_table,
    metric_row,
    page_header,
    render_chart,
)
from lake_literature.dashboard.theme import CATEGORICAL_PALETTE, theme_tokens


def render() -> None:
    page_header(
        "🔬",
        "Evidências Metodológicas",
        "Formulação matemática, funções-objetivo, incerteza, horizontes temporais, validação IEEE, solvers e longevidade citacional.",
    )

    articles_df = loaders.require_articles()
    df = loaders.with_semantics(articles_df)

    (
        tab_methods,
        tab_objectives,
        tab_uncertainty,
        tab_horizons,
        tab_feeders,
        tab_solvers,
        tab_longevity,
    ) = st.tabs(
        [
            "⚙️ Métodos & Complexidade",
            "🎯 Funções-Objetivo",
            "🎲 Modelagem da Incerteza",
            "⏱️ Horizontes Temporais",
            "⚡ Benchmarks IEEE & Redes",
            "💻 Ferramental & Solvers",
            "⏳ Longevidade & Estilometria",
        ]
    )

    with tab_methods:
        _render_methods_tab(df)

    with tab_objectives:
        _render_objectives_tab(df)

    with tab_uncertainty:
        _render_uncertainty_tab(df)

    with tab_horizons:
        _render_horizons_tab(df)

    with tab_feeders:
        _render_feeders_tab(df)

    with tab_solvers:
        _render_solvers_tab(df)

    with tab_longevity:
        _render_longevity_and_text_tab(df)


# ---------------------------------------------------------------------------
# Tab 1: Métodos & Complexidade Matemática
# ---------------------------------------------------------------------------


def _render_methods_tab(df: pd.DataFrame) -> None:
    st.markdown("### ⚙️ Taxonomia dos Paradigmas de Otimização & Complexidade Matemática")
    st.caption(
        "Identifica e quantifica os métodos matemáticos empregados na literatura de planejamento de distribuição. "
        "Evidencia a transição histórica de meta-heurísticas clássicas para programação exata (MILP, SOCP), "
        "otimização sob incerteza (Robusta, Estocástica) e inteligência artificial."
    )

    res = optimization_methods_taxonomy(df)
    summary_df = res["summary_df"]
    temporal_df = res["temporal_df"]

    if summary_df.empty:
        st.info("Nenhum método de otimização detectado no corpus.")
        return

    spec_res = mathematical_complexity_spectrum(df)
    spectrum_df = spec_res["spectrum_df"]
    temp_spec = spec_res["temporal_spectrum"]

    top_method = summary_df.iloc[0]["method"]
    top_cites_method = summary_df.sort_values(by="mean_citations", ascending=False).iloc[0][
        "method"
    ]
    top_recent_method = summary_df.sort_values(by="pct_recent", ascending=False).iloc[0]["method"]

    metric_row(
        [
            ("🏆 Método Mais Frequente", top_method, f"{summary_df.iloc[0]['articles']} artigos"),
            ("🚀 Maior Momentum Recente", top_recent_method, "Maior proporção ≥ 2021"),
            ("💡 Maior Impacto Citacional", top_cites_method, "Média de citações/artigo"),
            ("📐 Paradigmas Mapeados", str(len(summary_df)), "Famílias de resolução"),
        ]
    )

    col_bar, col_line = st.columns([1, 1])

    with col_bar:
        st.markdown("#### 📊 Volume Total por Método")
        bar_data = summary_df.sort_values(by="articles", ascending=True)
        fig_bar = px.bar(
            bar_data,
            x="articles",
            y="method",
            orientation="h",
            color="pct_recent",
            color_continuous_scale="Viridis",
            labels={
                "articles": "Artigos",
                "method": "Paradigma",
                "pct_recent": "% Recente (≥2021)",
            },
        )
        fig_bar.update_layout(
            xaxis_title="Quantidade de Artigos",
            yaxis_title="Paradigma",
            height=440,
            margin={"l": 20, "r": 20, "t": 30, "b": 30},
        )
        render_chart(fig_bar)

    with col_line:
        st.markdown("#### 📈 Evolução Temporal dos Principais Métodos")
        if not temporal_df.empty:
            top_cols = summary_df.head(5)["method"].tolist()
            plot_temp = temporal_df[[c for c in top_cols if c in temporal_df.columns]].reset_index()
            fig_temp = px.line(
                plot_temp,
                x="year",
                y=[c for c in top_cols if c in temporal_df.columns],
                labels={
                    "value": "Nº Artigos / Ano",
                    "year": "Ano de Publicação",
                    "variable": "Método",
                },
                color_discrete_sequence=CATEGORICAL_PALETTE,
            )
            fig_temp.update_layout(
                xaxis_title="Ano de Publicação",
                yaxis_title="Nº Artigos / Ano",
                height=440,
                legend={"orientation": "h", "y": -0.25, "x": 0.0},
                margin={"l": 20, "r": 20, "t": 30, "b": 30},
            )
            render_chart(fig_temp)

    st.markdown("#### 📐 Espectro de Complexidade Matemática das Formulações")
    col_c1, col_c2 = st.columns([1, 1])
    with col_c1:
        if not spectrum_df.empty:
            fig_spec = px.bar(
                spectrum_df.sort_values(by="articles", ascending=True),
                x="articles",
                y="complexity_class",
                orientation="h",
                color="pct_recent",
                color_continuous_scale="Plasma",
                labels={
                    "articles": "Artigos",
                    "complexity_class": "Classe de Complexidade",
                    "pct_recent": "% Recente (≥2021)",
                },
            )
            fig_spec.update_layout(
                xaxis_title="Artigos no Corpus",
                yaxis_title="Classe de Complexidade",
                height=380,
                margin={"l": 20, "r": 20, "t": 30, "b": 30},
            )
            render_chart(fig_spec)

    with col_c2:
        if not temp_spec.empty:
            classes_avail = [c for c in temp_spec.columns if c != "year"]
            fig_tspec = px.line(
                temp_spec,
                x="year",
                y=classes_avail,
                labels={
                    "value": "Artigos / Ano",
                    "year": "Ano de Publicação",
                    "variable": "Classe",
                },
                color_discrete_sequence=CATEGORICAL_PALETTE,
            )
            fig_tspec.update_layout(
                xaxis_title="Ano de Publicação",
                yaxis_title="Artigos / Ano",
                height=380,
                legend={"orientation": "h", "y": -0.25, "x": 0.0},
                margin={"l": 20, "r": 20, "t": 30, "b": 30},
            )
            render_chart(fig_tspec)

    st.markdown("#### 📋 Tabela Analítica dos Métodos de Otimização")
    display_sum = summary_df.copy()
    display_sum["pct_recent"] = display_sum["pct_recent"].astype(str) + "%"
    display_sum.columns = [
        "Paradigma de Resolução",
        "Artigos no Corpus",
        "Publicações ≥ 2021",
        "Citações Médias",
    ]
    st.dataframe(display_sum, hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# Tab 2: Funções-Objetivo & Co-Otimização
# ---------------------------------------------------------------------------


def _render_objectives_tab(df: pd.DataFrame) -> None:
    st.markdown("### 🎯 Funções-Objetivo & Formulações Multi-Critério")
    st.caption(
        "Mapeia quais critérios a literatura busca otimizar: custos econômicos de investimento e operação (CAPEX/OPEX), "
        "confiabilidade e continuidade de suprimento (SAIDI, SAIFI, ENS), perdas técnicas ($I^2R$), perfil de tensão, "
        "descarbonização e emissões, e resiliência a eventos climáticos extremos. "
        "A matriz de co-ocorrência revela quais pares de objetivos são frequentemente resolvidos em conjunto."
    )

    obj_res = objective_functions_taxonomy(df)
    summary_df = obj_res["summary_df"]
    co_matrix = obj_res["co_matrix"]
    multi_ratio = obj_res["multi_obj_ratio"]
    temporal_multiobj = obj_res["temporal_multiobj"]

    if summary_df.empty:
        st.info("Nenhuma função-objetivo identificada no corpus.")
        return

    top_obj = summary_df.iloc[0]["objective"]
    top_cites = summary_df.sort_values(by="mean_citations", ascending=False).iloc[0]["objective"]

    metric_row(
        [
            ("🏆 Objetivo Mais Frequente", top_obj, f"{summary_df.iloc[0]['articles']} artigos"),
            ("🌐 Taxa Multi-Objetivo", f"{multi_ratio:.1f}%", "Estudos com ≥ 2 objetivos"),
            ("💡 Maior Impacto Citacional", top_cites, "Média de citações/artigo"),
            ("📐 Famílias de Objetivos", str(len(summary_df)), "Critérios fundamentais"),
        ]
    )

    col_bar, col_heat = st.columns([1, 1.1])

    with col_bar:
        st.markdown("#### 📊 Frequência e Atualidade das Funções-Objetivo")
        fig_obj = px.bar(
            summary_df.sort_values(by="articles", ascending=True),
            x="articles",
            y="objective",
            orientation="h",
            color="pct_recent",
            color_continuous_scale="Tealgrn",
            labels={
                "articles": "Artigos",
                "objective": "Critério / Função-Objetivo",
                "pct_recent": "% Recente (≥2021)",
            },
        )
        fig_obj.update_layout(
            xaxis_title="Artigos no Corpus",
            yaxis_title="Critério / Função-Objetivo",
            height=460,
            margin={"l": 20, "r": 20, "t": 30, "b": 30},
        )
        render_chart(fig_obj)

    with col_heat:
        st.markdown("#### 🧬 Matriz de Co-Otimização de Objetivos")
        if not co_matrix.empty:
            fig_co = px.imshow(
                co_matrix,
                text_auto=True,
                aspect="auto",
                color_continuous_scale="Purples",
                labels={
                    "x": "Objetivo Concorrente",
                    "y": "Objetivo Primário",
                    "color": "Artigos Conjuntos",
                },
            )
            fig_co.update_layout(
                xaxis_title="Objetivo Concorrente",
                yaxis_title="Objetivo Primário",
                height=460,
                margin={"l": 20, "r": 20, "t": 30, "b": 30},
            )
            render_chart(fig_co)

    st.markdown("#### 📈 Transição Histórica: Mono-Objetivo vs. Multi-Objetivo")
    if not temporal_multiobj.empty:
        fig_mo = go.Figure()
        fig_mo.add_trace(
            go.Bar(
                x=temporal_multiobj["year"],
                y=temporal_multiobj["mono_objective"],
                name="Mono-Objetivo",
                marker={"color": "#636EFA"},
            )
        )
        fig_mo.add_trace(
            go.Bar(
                x=temporal_multiobj["year"],
                y=temporal_multiobj["multi_objective"],
                name="Multi-Objetivo (≥2 critérios)",
                marker={"color": "#00CC96"},
            )
        )
        fig_mo.add_trace(
            go.Scatter(
                x=temporal_multiobj["year"],
                y=temporal_multiobj["pct_multi"],
                yaxis="y2",
                mode="lines+markers",
                name="% Multi-Objetivo",
                line={"color": "#FFA15A", "width": 2.5},
            )
        )
        fig_mo.update_layout(
            barmode="stack",
            xaxis_title="Ano de Publicação",
            yaxis_title="Volume de Artigos",
            yaxis2={
                "title": "Participação Multi-Objetivo (%)",
                "overlaying": "y",
                "side": "right",
                "showgrid": False,
            },
            legend={"orientation": "h", "y": -0.2, "x": 0.0},
            height=420,
            margin={"l": 20, "r": 20, "t": 30, "b": 30},
        )
        render_chart(fig_mo)

    st.markdown("#### 📋 Detalhamento das Funções-Objetivo")
    disp_obj = summary_df.copy()
    disp_obj["pct_recent"] = disp_obj["pct_recent"].astype(str) + "%"
    disp_obj.columns = [
        "Função-Objetivo / Critério",
        "Artigos no Corpus",
        "Publicações ≥ 2021",
        "Citações Médias",
    ]
    st.dataframe(disp_obj, hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# Tab 3: Modelagem da Incerteza
# ---------------------------------------------------------------------------


def _render_uncertainty_tab(df: pd.DataFrame) -> None:
    st.markdown("### 🎲 Paradigmas de Modelagem da Incerteza & Estocástica")
    st.caption(
        "Avalia como a literatura lida com a aleatoriedade da geração renovável (solar, eólica), "
        "comportamento de carga e recarga de veículos elétricos. "
        "Contrapõe abordagens determinísticas à programação estocástica com redução de cenários, "
        "otimização robusta (conjuntos de incerteza do pior caso), lógica fuzzy e otimização distribucionalmente robusta (DRO)."
    )

    unc_res = uncertainty_paradigms_analysis(df)
    paradigms_df = unc_res["paradigms_df"]
    cross_resources = unc_res["cross_resources"]
    temp_paradigms = unc_res["temporal_paradigms"]

    if paradigms_df.empty:
        st.info("Nenhum paradigma de incerteza detectado no corpus.")
        return

    top_paradigm = paradigms_df.iloc[0]["paradigm"]
    top_cites = paradigms_df.sort_values(by="mean_citations", ascending=False).iloc[0]["paradigm"]

    metric_row(
        [
            (
                "🎲 Paradigma Predominante",
                top_paradigm,
                f"{paradigms_df.iloc[0]['articles']} artigos",
            ),
            (
                "🚀 Paradigma Mais Recente",
                paradigms_df.sort_values(by="pct_recent", ascending=False).iloc[0]["paradigm"],
                "Maior % pós-2021",
            ),
            ("💡 Maior Impacto Citacional", top_cites, "Média de citações/artigo"),
            ("📐 Paradigmas Mapeados", str(len(paradigms_df)), "Modelos de incerteza"),
        ]
    )

    col_pbar, col_pcross = st.columns([1, 1.1])

    with col_pbar:
        st.markdown("#### 📊 Distribuição dos Paradigmas de Incerteza")
        fig_p = px.bar(
            paradigms_df.sort_values(by="articles", ascending=True),
            x="articles",
            y="paradigm",
            orientation="h",
            color="pct_recent",
            color_continuous_scale="Plasma",
            labels={
                "articles": "Artigos",
                "paradigm": "Paradigma de Incerteza",
                "pct_recent": "% Recente (≥2021)",
            },
        )
        fig_p.update_layout(
            xaxis_title="Artigos no Corpus",
            yaxis_title="Paradigma de Incerteza",
            height=440,
            margin={"l": 20, "r": 20, "t": 30, "b": 30},
        )
        render_chart(fig_p)

    with col_pcross:
        st.markdown("#### 🧬 Incerteza × Recurso Físico Modelado")
        if not cross_resources.empty:
            fig_cr = px.imshow(
                cross_resources,
                text_auto=True,
                aspect="auto",
                color_continuous_scale="Viridis",
                labels={
                    "x": "Recurso / Vetor Físico",
                    "y": "Paradigma de Incerteza",
                    "color": "Artigos Conjuntos",
                },
            )
            fig_cr.update_layout(
                xaxis_title="Recurso / Vetor Físico",
                yaxis_title="Paradigma de Incerteza",
                height=440,
                margin={"l": 20, "r": 20, "t": 30, "b": 30},
            )
            render_chart(fig_cr)

    if not temp_paradigms.empty:
        st.markdown("#### 📈 Evolução Histórica dos Paradigmas de Incerteza")
        p_cols = [c for c in temp_paradigms.columns if c != "year"]
        fig_tp = px.line(
            temp_paradigms,
            x="year",
            y=p_cols,
            labels={
                "value": "Artigos / Ano",
                "year": "Ano de Publicação",
                "variable": "Paradigma",
            },
            color_discrete_sequence=CATEGORICAL_PALETTE,
        )
        fig_tp.update_layout(
            xaxis_title="Ano de Publicação",
            yaxis_title="Artigos / Ano",
            height=420,
            legend={"orientation": "h", "y": -0.25, "x": 0.0},
            margin={"l": 20, "r": 20, "t": 30, "b": 30},
        )
        render_chart(fig_tp)

    st.markdown("#### 📋 Síntese dos Paradigmas de Incerteza")
    disp_p = paradigms_df.copy()
    disp_p["pct_recent"] = disp_p["pct_recent"].astype(str) + "%"
    disp_p.columns = [
        "Paradigma de Incerteza",
        "Artigos no Corpus",
        "Publicações ≥ 2021",
        "Citações Médias",
    ]
    st.dataframe(disp_p, hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# Tab 4: Horizontes Temporais & Escalas
# ---------------------------------------------------------------------------


def _render_horizons_tab(df: pd.DataFrame) -> None:
    st.markdown("### ⏱️ Horizontes de Planejamento & Dinâmica Temporal")
    st.caption(
        "Mapeia como a literatura estrutura o horizonte temporal de expansão: "
        "desde o **Planejamento Estático** (ano-alvo único tipo *snapshot*) até a **Expansão Dinâmica Multi-Estágio** (*Multi-Year*), "
        "e a moderna **Co-Otimização Planejamento + Operação** com representação horária e dias representativos de demanda/geração."
    )

    h_res = planning_time_horizons_analysis(df)
    horizons_df = h_res["horizons_df"]

    if horizons_df.empty:
        st.info("Nenhum horizonte temporal detectado no corpus.")
        return

    top_h = horizons_df.iloc[0]["horizon"]
    total_art = horizons_df["articles"].sum()

    metric_row(
        [
            ("⏱️ Estrutura Mais Adotada", top_h, f"{horizons_df.iloc[0]['articles']} artigos"),
            (
                "🚀 Maior Momentum Recente",
                horizons_df.sort_values(by="pct_recent", ascending=False).iloc[0]["horizon"],
                "Maior % pós-2021",
            ),
            (
                "💡 Maior Impacto Citacional",
                horizons_df.sort_values(by="mean_citations", ascending=False).iloc[0]["horizon"],
                "Média de citações/artigo",
            ),
            ("📄 Artigos Classificados", str(total_art), "Horizonte identificado"),
        ]
    )

    col_hbar, col_hcite = st.columns([1, 1])

    with col_hbar:
        st.markdown("#### 📊 Volume por Estrutura de Horizonte")
        fig_h = px.bar(
            horizons_df.sort_values(by="articles", ascending=True),
            x="articles",
            y="horizon",
            orientation="h",
            color="pct_recent",
            color_continuous_scale="Blues",
            labels={
                "articles": "Artigos",
                "horizon": "Estrutura Temporal",
                "pct_recent": "% Recente (≥2021)",
            },
        )
        fig_h.update_layout(
            xaxis_title="Artigos no Corpus",
            yaxis_title="Estrutura Temporal",
            height=380,
            margin={"l": 20, "r": 20, "t": 30, "b": 30},
        )
        render_chart(fig_h)

    with col_hcite:
        st.markdown("#### 💡 Citações Médias por Horizonte Adotado")
        fig_hc = px.bar(
            horizons_df.sort_values(by="mean_citations", ascending=True),
            x="mean_citations",
            y="horizon",
            orientation="h",
            color="mean_citations",
            color_continuous_scale="Viridis",
            labels={
                "mean_citations": "Citações Médias",
                "horizon": "Estrutura Temporal",
            },
        )
        fig_hc.update_layout(
            xaxis_title="Citações Médias por Artigo",
            yaxis_title="Estrutura Temporal",
            height=380,
            margin={"l": 20, "r": 20, "t": 30, "b": 30},
        )
        render_chart(fig_hc)

    st.markdown(
        "> [!TIP]\n"
        "> **Evidência Metodológica**: A transição para redes descarbonizadas forçou a literatura a migrar de planejamentos estáticos "
        "> para a **Co-Otimização Planejamento + Operação**. Ativos de curta duração (como baterias BESS e resposta da demanda) "
        "> não podem ser dimensionados sem modelar a flexibilidade operativa sub-horária e dias típicos ao longo do ano."
    )

    st.markdown("#### 📋 Detalhamento dos Horizontes de Planejamento")
    disp_h = horizons_df.copy()
    disp_h["pct_recent"] = disp_h["pct_recent"].astype(str) + "%"
    disp_h.columns = [
        "Estrutura de Horizonte Temporal",
        "Artigos no Corpus",
        "Publicações ≥ 2021",
        "Citações Médias",
    ]
    st.dataframe(disp_h, hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# Tab 5: Benchmarks IEEE & Redes
# ---------------------------------------------------------------------------


def _render_feeders_tab(df: pd.DataFrame) -> None:
    st.markdown("### ⚡ Sistemas de Teste & Validação Empírica (IEEE Benchmarks)")
    st.caption(
        "Mapeia quais redes elétricas de teste são utilizadas para validação dos modelos teóricos. "
        "Diferencia alimentadores radiais padronizados do IEEE (33, 69 e 123 nós) de redes reais de concessionárias."
    )

    res = benchmark_feeders_analysis(df)
    feeders_df = res["feeders_df"]
    cross_matrix = res["cross_matrix"]

    if feeders_df.empty:
        st.info("Nenhum sistema de teste identificado no corpus.")
        return

    top_feeder = feeders_df.iloc[0]["feeder"]
    real_nets = feeders_df[feeders_df["feeder"].str.contains("Reais")]["articles"].sum()

    metric_row(
        [
            (
                "🔌 Benchmark Mais Utilizado",
                top_feeder,
                f"{feeders_df.iloc[0]['articles']} artigos",
            ),
            ("🏢 Validação em Redes Reais", f"{real_nets} artigos", "Estudos com concessionárias"),
            ("⚡ Sistemas Mapeados", str(len(feeders_df)), "Padrões IEEE e redes práticas"),
        ]
    )

    col_feed, col_cross = st.columns([1, 1.1])

    with col_feed:
        st.markdown("#### 🏆 Distribuição de Casos de Estudo")
        fig_f = px.bar(
            feeders_df.sort_values(by="articles", ascending=True),
            x="articles",
            y="feeder",
            orientation="h",
            color="articles",
            color_continuous_scale="Tealgrn",
            labels={"articles": "Artigos", "feeder": "Sistema de Teste"},
        )
        fig_f.update_layout(
            xaxis_title="Artigos no Corpus",
            yaxis_title="Sistema de Teste",
            height=440,
            margin={"l": 20, "r": 20, "t": 30, "b": 30},
        )
        render_chart(fig_f)

    with col_cross:
        st.markdown("#### 🧬 Matriz Cruzada: Benchmark × Recurso Modelado")
        if not cross_matrix.empty:
            fig_c = px.imshow(
                cross_matrix,
                text_auto=True,
                aspect="auto",
                color_continuous_scale="Purp",
                labels={
                    "x": "Recurso / Tecnologia",
                    "y": "Rede de Teste / Benchmark",
                    "color": "Artigos Conjuntos",
                },
            )
            fig_c.update_layout(
                xaxis_title="Recurso / Tecnologia",
                yaxis_title="Rede de Teste / Benchmark",
                height=440,
                margin={"l": 20, "r": 20, "t": 30, "b": 30},
            )
            render_chart(fig_c)

    st.markdown("#### 📋 Catálogo de Sistemas de Teste")
    disp_f = feeders_df.copy()
    disp_f["pct_recent"] = disp_f["pct_recent"].astype(str) + "%"
    disp_f.columns = [
        "Sistema de Teste / Rede",
        "Artigos no Corpus",
        "Publicações ≥ 2021",
        "Citações Médias",
    ]
    st.dataframe(disp_f, hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# Tab 6: Ferramental & Solvers Computacionais
# ---------------------------------------------------------------------------


def _render_solvers_tab(df: pd.DataFrame) -> None:
    st.markdown("### 💻 Ferramental Computacional, Modeladores & Solvers")
    st.caption(
        "Analisa os softwares matemáticos, plataformas de modelagem algébrica e simuladores especializados "
        "que viabilizam a implementação computacional das formulações teóricas na literatura de distribuição."
    )

    s_res = computational_solvers_analysis(df)
    solvers_df = s_res["solvers_df"]
    ecosystem_df = s_res["ecosystem_df"]

    if solvers_df.empty:
        st.info("Nenhuma menção explícita a solvers computacionais identificada no corpus.")
        return

    top_tool = solvers_df.iloc[0]["tool"]
    top_cat = ecosystem_df.iloc[0]["category"]

    metric_row(
        [
            ("💻 Ferramenta Mais Citada", top_tool, f"{solvers_df.iloc[0]['articles']} artigos"),
            (
                "📐 Ecossistema Líder",
                top_cat,
                f"{ecosystem_df.iloc[0]['articles']} referências",
            ),
            ("🛠️ Ferramentas Mapeadas", str(len(solvers_df)), "Solvers e simuladores"),
        ]
    )

    col_s1, col_s2 = st.columns([1.1, 0.9])

    with col_s1:
        st.markdown("#### 📊 Distribuição por Plataforma / Solver")
        fig_s = px.bar(
            solvers_df.sort_values(by="articles", ascending=True),
            x="articles",
            y="tool",
            orientation="h",
            color="category",
            color_discrete_sequence=CATEGORICAL_PALETTE,
            labels={
                "articles": "Artigos",
                "tool": "Software / Solver",
                "category": "Ecossistema",
            },
        )
        fig_s.update_layout(
            xaxis_title="Artigos no Corpus",
            yaxis_title="Software / Solver",
            height=440,
            margin={"l": 20, "r": 20, "t": 30, "b": 30},
        )
        render_chart(fig_s)

    with col_s2:
        st.markdown("#### 🧩 Participação por Categoria de Ferramental")
        if not ecosystem_df.empty:
            fig_pie = px.pie(
                ecosystem_df,
                names="category",
                values="articles",
                hole=0.45,
                color_discrete_sequence=CATEGORICAL_PALETTE,
            )
            fig_pie.update_layout(
                height=440,
                legend={"orientation": "h", "y": -0.15, "x": 0.0},
                margin={"l": 20, "r": 20, "t": 30, "b": 30},
            )
            render_chart(fig_pie)

    st.markdown("#### 📋 Detalhamento do Ecossistema Computacional")
    disp_s = solvers_df.copy()
    disp_s["pct_recent"] = disp_s["pct_recent"].astype(str) + "%"
    disp_s.columns = [
        "Software / Ferramenta",
        "Categoria de Software",
        "Artigos no Corpus",
        "Publicações ≥ 2021",
        "Citações Médias",
    ]
    st.dataframe(disp_s, hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# Tab 7: Liderança Científica & Carreira
# ---------------------------------------------------------------------------


def _render_authors_tab(df: pd.DataFrame) -> None:
    st.markdown("### 🎖️ Índices Avançados de Liderança Científica & Velocidade de Carreira")
    st.caption(
        "Avaliação formal do impacto individual com indicadores da cienciometria moderna: "
        "**h-index**, **g-index de Egghe (2006)**, **e-index de Zhang (2009)** e o "
        "**$m$-quotient de Hirsch** ($m = h / \\text{anos de carreira}$), que mede a velocidade de impacto por ano ativo."
    )

    auth_df = author_impact_advanced_indices(df, min_papers=2)
    m_df = author_m_quotient_analysis(df, min_papers=2)

    if auth_df.empty:
        st.info("Autores com produção mínima de 2 artigos não encontrados.")
        return

    top_g = auth_df.iloc[0]
    top_m = m_df.iloc[0] if not m_df.empty else None

    metric_row(
        [
            (
                "🥇 Maior g-index",
                f"{top_g['author']} (g={top_g['g_index']})",
                f"h-index: {top_g['h_index']}",
            ),
            (
                "🔥 Maior Excesso Citacional (e)",
                f"{auth_df.sort_values(by='e_index', ascending=False).iloc[0]['author']}",
                f"e={auth_df.sort_values(by='e_index', ascending=False).iloc[0]['e_index']:.1f}",
            ),
            (
                "⚡ Maior Velocidade (m-quotient)",
                f"{top_m['author']} (m={top_m['m_quotient']})" if top_m is not None else "N/A",
                "h-index por ano de carreira",
            ),
            ("👥 Pesquisadores Analisados", str(len(auth_df)), "≥ 2 artigos no corpus"),
        ]
    )

    col_scatter, col_ebar = st.columns([1.1, 0.9])

    with col_scatter:
        st.markdown("#### 🎯 Dispersão h-index vs. g-index (Egghe)")
        max_val = max(auth_df["g_index"].max(), auth_df["h_index"].max()) + 2

        t = theme_tokens()
        ref_line = t.get("reference_line_subtle", "rgba(180, 180, 180, 0.6)")
        border_color = t.get("point_border", "#FFFFFF")

        fig_hg = go.Figure()
        # 45-degree line (g = h)
        fig_hg.add_trace(
            go.Scatter(
                x=[0, max_val],
                y=[0, max_val],
                mode="lines",
                name="g = h (Produção Uniforme)",
                line={"dash": "dash", "color": ref_line, "width": 1.5},
            )
        )
        # Scatter points
        hover_hg = [
            f"<b>{r['author']}</b><br>• g-index: {r['g_index']}<br>• h-index: {r['h_index']}<br>• Artigos: {r['papers']}<br>• Citações: {r['total_citations']:,}<br>• e-index: {r['e_index']}"
            for _, r in auth_df.iterrows()
        ]
        fig_hg.add_trace(
            go.Scatter(
                x=auth_df["h_index"],
                y=auth_df["g_index"],
                mode="markers",
                marker={
                    "size": auth_df["papers"].clip(lower=6, upper=24),
                    "color": auth_df["g_h_diff"],
                    "colorscale": "Plasma",
                    "colorbar": {"title": "g - h"},
                    "opacity": 0.85,
                    "line": {"color": border_color, "width": 1},
                },
                hoverinfo="text",
                hovertext=hover_hg,
                name="Pesquisadores",
            )
        )
        fig_hg.update_layout(
            xaxis_title="h-index (Consistência)",
            yaxis_title="g-index de Egghe (Impacto com Blockbusters)",
            height=480,
            margin={"l": 20, "r": 20, "t": 30, "b": 30},
        )
        render_chart(fig_hg)

    with col_ebar:
        st.markdown("#### 🚀 Top 12 por Excesso Citacional (e-index de Zhang)")
        top_e = auth_df.sort_values(by="e_index", ascending=True).tail(12)
        fig_e = px.bar(
            top_e,
            x="e_index",
            y="author",
            orientation="h",
            color="total_citations",
            color_continuous_scale="Magma",
            labels={
                "e_index": "e-index de Zhang",
                "author": "Pesquisador",
                "total_citations": "Total Citações",
            },
        )
        fig_e.update_layout(
            xaxis_title="e-index de Zhang",
            yaxis_title="Pesquisador",
            height=480,
            margin={"l": 20, "r": 20, "t": 30, "b": 30},
        )
        render_chart(fig_e)

    if not m_df.empty:
        st.markdown(
            "#### ⚡ Top 12 em Velocidade Citacional por Ano de Carreira (m-quotient de Hirsch)"
        )
        top_m_plot = m_df.head(12).sort_values(by="m_quotient", ascending=True)
        fig_m = px.bar(
            top_m_plot,
            x="m_quotient",
            y="author",
            orientation="h",
            color="papers",
            color_continuous_scale="Tealgrn",
            labels={
                "m_quotient": "m-quotient (h-index / Anos de Carreira)",
                "author": "Pesquisador",
                "papers": "Artigos no Corpus",
            },
        )
        fig_m.update_layout(
            xaxis_title="m-quotient (h / Anos de Carreira)",
            yaxis_title="Pesquisador",
            height=420,
            margin={"l": 20, "r": 20, "t": 30, "b": 30},
        )
        render_chart(fig_m)

    st.markdown("#### 📋 Ranking Completo de Liderança Científica")
    disp_auth = auth_df.copy()
    if not m_df.empty:
        disp_auth = disp_auth.merge(
            m_df[["author", "first_year", "career_span_years", "m_quotient"]],
            on="author",
            how="left",
        )
        disp_auth.columns = [
            "Pesquisador",
            "Artigos",
            "Total Citações",
            "Média Citações",
            "h-index",
            "g-index (Egghe)",
            "e-index (Zhang)",
            "i10-index",
            "Diferença (g - h)",
            "1º Ano",
            "Anos de Carreira",
            "m-quotient",
        ]
    else:
        disp_auth.columns = [
            "Pesquisador",
            "Artigos",
            "Total Citações",
            "Média Citações",
            "h-index",
            "g-index (Egghe)",
            "e-index (Zhang)",
            "i10-index",
            "Diferença (g - h)",
        ]
    st.dataframe(disp_auth.head(30), hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# Tab 8: Longevidade & Estilometria Textual
# ---------------------------------------------------------------------------


def _render_longevity_and_text_tab(df: pd.DataFrame) -> None:
    st.markdown("### ⏳ Longevidade do Conhecimento, Artigos Evergreen & Estilometria")
    st.caption(
        "Mapeia a taxa de sobrevivência do impacto científico no tempo, quantifica a **Meia-Vida Citacional**, "
        "destaca os **Artigos Evergreen** e investiga as propriedades linguísticas e estilométricas dos resumos "
        "(Flesch-Kincaid e Riqueza Vocabular TTR)."
    )

    res_long = citation_longevity_and_decay(df)
    decay_curve = res_long["decay_curve"]
    evergreen_df = res_long["evergreen_df"]

    res_text = text_readability_and_stylometrics(df)
    temp_text = res_text["temporal_df"]
    sample_text = res_text["sample_df"]

    metric_row(
        [
            (
                "⌛ Meia-Vida Citacional",
                f"{res_long['half_life_years']:.1f} anos",
                "Tempo p/ 50% das citações",
            ),
            (
                "🌲 Artigos Evergreen",
                str(len(evergreen_df)),
                "Idade ≥ 10 anos & Citações ≥ 40",
            ),
            (
                "📚 Nível Flesch-Kincaid",
                f"{res_text['mean_fkgl']:.1f} anos",
                "Complexidade acadêmica",
            ),
            (
                "🧬 Riqueza Vocabular (TTR)",
                f"{res_text['mean_ttr']:.3f}",
                "Diversidade lexical média",
            ),
        ]
    )

    col_curv, col_fkgl = st.columns([1, 1])

    with col_curv:
        st.markdown("#### 📉 Curva Acumulada de Meia-Vida Citacional")
        if not decay_curve.empty:
            fig_decay = go.Figure()
            fig_decay.add_trace(
                go.Scatter(
                    x=decay_curve["age"],
                    y=decay_curve["cum_pct"],
                    mode="lines+markers",
                    name="Citações Acumuladas (%)",
                    line={"color": "#636EFA", "width": 2.5},
                )
            )
            fig_decay.add_hline(
                y=50,
                line_dash="dash",
                line_color="#EF553B",
                annotation_text=f"Meia-Vida = {res_long['half_life_years']:.0f} anos",
                annotation_position="bottom right",
            )
            fig_decay.update_layout(
                xaxis_title="Idade do Artigo (Anos decorridos desde publicação)",
                yaxis_title="Percentual Acumulado de Citações (%)",
                height=420,
                margin={"l": 20, "r": 20, "t": 30, "b": 30},
            )
            render_chart(fig_decay)

    with col_fkgl:
        st.markdown("#### 📈 Complexidade Textual Flesch-Kincaid por Ano")
        if not temp_text.empty:
            fig_f = px.line(
                temp_text,
                x="year",
                y="mean_fkgl",
                markers=True,
                labels={
                    "year": "Ano de Publicação",
                    "mean_fkgl": "Nível Flesch-Kincaid (Anos de Estudo)",
                },
                color_discrete_sequence=["#EF553B"],
            )
            fig_f.update_layout(
                xaxis_title="Ano de Publicação",
                yaxis_title="Nível Flesch-Kincaid (Anos de Estudo)",
                height=420,
                margin={"l": 20, "r": 20, "t": 30, "b": 30},
            )
            render_chart(fig_f)

    if not sample_text.empty:
        st.markdown("#### 🎯 Riqueza Vocabular (TTR) vs. Citações Recebidas")
        fig_s = px.scatter(
            sample_text.sample(min(400, len(sample_text)), random_state=42),
            x="ttr",
            y="citation_count",
            color="fre",
            color_continuous_scale="Blues",
            labels={
                "ttr": "Type-Token Ratio (Diversidade Lexical)",
                "citation_count": "Citações",
                "fre": "Flesch Ease",
            },
            opacity=0.75,
        )
        fig_s.update_layout(
            xaxis_title="Type-Token Ratio (Diversidade Lexical)",
            yaxis_title="Citações Recebidas",
            height=380,
            margin={"l": 20, "r": 20, "t": 30, "b": 30},
        )
        render_chart(fig_s)

    st.markdown("#### 🌲 Top Artigos Evergreen no Planejamento de Distribuição")
    if not evergreen_df.empty:
        display_cols = ["title", "year", "venue", "citation_count", "age", "annual_velocity"]
        article_table(
            evergreen_df.head(10),
            [c for c in display_cols if c in evergreen_df.columns],
            download_key="evergreen_articles_download",
        )
    else:
        st.info("Sem artigos evergreen suficientes para exibição.")
