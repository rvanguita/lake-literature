"""🔮 Tendências & Previsão — projeção de volume de publicações (2027-2028) via regressão."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lake_literature.dashboard import loaders
from lake_literature.dashboard.analytics import explode_keywords
from lake_literature.dashboard.components import hero_banner, metric_row, page_header, render_chart
from lake_literature.dashboard.forecasting import (
    HOLDOUT_YEAR,
    ForecastResult,
    fit_and_forecast,
    yearly_counts,
)
from lake_literature.dashboard.theme import (
    CATEGORICAL_PALETTE,
    SOURCE_COLORS,
    SOURCE_LABELS,
    TOTAL_COLOR,
    hex_to_rgba,
    theme_tokens,
)

TOP_KEYWORDS_FORECAST = 10
TOP_KEYWORD_TRENDS = 5
MIN_KEYWORD_OCCURRENCES = 20

_MODEL_LABELS = {
    "linear": "Linear",
    "polynomial": "Polinomial (grau 2)",
    "log_linear": "Log-linear (crescimento exponencial)",
    "none": "—",
}


def render() -> None:
    page_header(
        "🔮",
        "Tendências & Previsão",
        "Projeção de volume de publicações para 2027-2028 a partir de modelos de regressão treinados "
        "em 2010-2025 e validados contra 2026.",
    )

    hero_banner(
        "⚠️ Esta página ignora o filtro global de ano da barra lateral",
        "Uma previsão de série temporal precisa do histórico completo, não de um recorte. Três modelos "
        "(linear, polinomial e log-linear) são treinados em 2010–2025, validados de duas formas — contra "
        "2026 e por validação cruzada nos anos 2023–2025 — e o melhor é escolhido antes de projetar 2027 e "
        f"2028. <b>{HOLDOUT_YEAR} é um ano parcial</b> (o corpus foi coletado no meio do ano), então o erro "
        "contra ele mede acerto sobre um ano ainda incompleto, não um ano fechado — por isso a validação "
        "cruzada nos anos completos anteriores pesa igualmente na escolha do modelo. O corpus também é "
        "deliberadamente incompleto (ver CLAUDE.md), então a curva reflete o que foi coletado, não "
        "necessariamente o volume real de publicações na área.",
    )

    _, articles_df = loaders.articles()
    if articles_df.empty:
        st.warning("Nenhum dado disponível ainda. Execute o pipeline e recarregue esta página.")
        return

    tab_total, tab_ieee, tab_elsevier, tab_keywords = st.tabs(
        ["🌐 Total", "🔷 IEEE", "🟠 Elsevier", "🏷️ Tópicos em Alta"]
    )
    for tab, label, source, color in (
        (tab_total, "Total", None, TOTAL_COLOR),
        (tab_ieee, SOURCE_LABELS["ieee"], "ieee", SOURCE_COLORS["ieee"]),
        (tab_elsevier, SOURCE_LABELS["elsevier"], "elsevier", SOURCE_COLORS["elsevier"]),
    ):
        with tab:
            series = yearly_counts(articles_df, source=source)
            result = fit_and_forecast(series)
            _render_series_forecast(label, color, result)

    with tab_keywords:
        _keyword_growth_ranking(articles_df)


def _render_series_forecast(label: str, color: str, result: ForecastResult) -> None:
    if result.insufficient_data:
        st.info(" ".join(result.notes) or "Dados insuficientes para uma previsão.")
        return

    partial_note = ""
    if result.holdout_actual is not None:
        err = abs(result.holdout_predicted - result.holdout_actual)
        partial_note = f"{err:,.1f} (vs. {HOLDOUT_YEAR}, parcial)"
    metric_row(
        [
            (
                "🧮 Modelo escolhido",
                _MODEL_LABELS.get(result.chosen_model, result.chosen_model),
                None,
            ),
            (
                "📉 MAE de validação",
                partial_note or "N/D",
                f"CV 2023–2025: {result.cv_mae:.1f}" if result.cv_mae == result.cv_mae else None,
            ),
            (
                "📈 R² (ajuste no treino)",
                f"{result.r2_train:.2f}" if result.r2_train == result.r2_train else "N/D",
                None,
            ),
            (
                f"🔮 Previsão {result.forecast_years[0]}",
                f"{result.forecast_values[0]:,.0f}",
                f"±{(result.forecast_upper[0] - result.forecast_values[0]):,.0f}",
            ),
            (
                f"🔮 Previsão {result.forecast_years[1]}",
                f"{result.forecast_values[1]:,.0f}",
                f"±{(result.forecast_upper[1] - result.forecast_values[1]):,.0f}",
            ),
        ]
    )

    fig = go.Figure()

    # Observed history (bars) -- includes the partial holdout year.
    fig.add_bar(
        x=result.history.index,
        y=result.history.values,
        name=f"{label} (observado)",
        marker_color=color,
        opacity=0.85,
    )

    # Fitted curve over the training + holdout range.
    fig.add_trace(
        go.Scatter(
            x=result.fitted_curve.index,
            y=result.fitted_curve.values,
            name="Modelo ajustado",
            mode="lines",
            line=dict(color=color, width=2, dash="dot"),
        )
    )

    # Forecast band (shaded) -- drawn before the forecast line so the line sits on top.
    band_years = list(result.forecast_years)
    fig.add_trace(
        go.Scatter(
            x=band_years + band_years[::-1],
            y=list(result.forecast_upper) + list(result.forecast_lower[::-1]),
            fill="toself",
            fillcolor=hex_to_rgba(TOTAL_COLOR, 0.18),
            line=dict(color="rgba(0,0,0,0)"),
            hoverinfo="skip",
            name="Intervalo de confiança (~95%)",
            showlegend=True,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=band_years,
            y=result.forecast_values,
            name="Previsão",
            mode="lines+markers",
            line=dict(color=TOTAL_COLOR, width=2.5, dash="dash"),
            marker=dict(size=9, symbol="diamond"),
            hovertemplate="Previsão %{x}: %{y:,.0f} artigos<extra></extra>",
        )
    )

    # Partial next-year actual (e.g. the handful of 2027 records already indexed) --
    # plotted separately so it's never mistaken for the forecast itself.
    next_year = band_years[0]
    if next_year in result.history.index and result.history.loc[next_year] > 0:
        # Fill with the vivid highlight color and outline in the chart's own
        # background -- a fixed white fill (the previous approach) disappears
        # against a white chart background in light mode.
        t = theme_tokens()
        fig.add_trace(
            go.Scatter(
                x=[next_year],
                y=[result.history.loc[next_year]],
                name=f"{next_year} (parcial/antecipado)",
                mode="markers",
                marker=dict(
                    size=13,
                    symbol="star",
                    color=TOTAL_COLOR,
                    line=dict(width=2, color=t["chart_bg"]),
                ),
                hovertemplate=f"{next_year} já tem %{{y:,.0f}} registros indexados (parcial)<extra></extra>",
            )
        )

    fig.update_layout(
        xaxis_title="Ano de publicação",
        yaxis_title="Quantidade de artigos",
        hovermode="x unified",
    )
    render_chart(
        fig,
        caption=f"Barras = observado (inclui {HOLDOUT_YEAR}, parcial). Linha pontilhada = ajuste do modelo "
        "no histórico. Losango tracejado + faixa sombreada = previsão e intervalo de confiança. Estrela = "
        "registros já indexados para o próximo ano, mostrados à parte por não serem o total final dele.",
    )

    with st.expander("📋 Comparação dos modelos candidatos"):
        table = result.model_comparison.copy()
        table["model"] = table["model"].map(_MODEL_LABELS)
        table = table.rename(
            columns={
                "model": "Modelo",
                "holdout_mae": f"MAE vs. {HOLDOUT_YEAR} (parcial)",
                "cv_mae": "MAE validação cruzada (2023–2025)",
                "combined_mae": "Score combinado (usado na escolha)",
            }
        )
        st.dataframe(table, hide_index=True, width="stretch")
        st.caption(
            "O modelo com menor score combinado é escolhido, depois re-treinado com todos os anos reais "
            f"disponíveis (até {HOLDOUT_YEAR}) antes de gerar a previsão acima."
        )


def _keyword_trend_lines(
    keywords: list[str], results_by_keyword: dict[str, ForecastResult]
) -> None:
    """Actual trajectory (solid) + forecast continuation (dashed) per topic.

    The ranking bar next to this only shows the net change between two
    points; this shows the real yearly shape leading up to it -- some
    "growing" topics rise steadily, others spike once and plateau, and that
    distinction doesn't survive a single before/after number.
    """
    fig = go.Figure()
    for i, kw in enumerate(keywords):
        result = results_by_keyword.get(kw)
        if result is None or result.insufficient_data:
            continue
        color = CATEGORICAL_PALETTE[i % len(CATEGORICAL_PALETTE)]

        fig.add_trace(
            go.Scatter(
                x=list(result.history.index),
                y=list(result.history.values),
                name=kw,
                legendgroup=kw,
                mode="lines",
                line=dict(color=color, width=2),
                hovertemplate=f"<b>{kw}</b><br>Ano %{{x}}: %{{y:.0f}} menções<extra></extra>",
            )
        )
        # Dashed continuation from the last real point into the forecast, so
        # the line doesn't visually jump -- not shown in the legend, since
        # it's the same topic as the solid trace right above it.
        forecast_x = [result.history.index[-1], *result.forecast_years]
        forecast_y = [result.history.values[-1], *result.forecast_values]
        fig.add_trace(
            go.Scatter(
                x=forecast_x,
                y=forecast_y,
                name=kw,
                legendgroup=kw,
                showlegend=False,
                mode="lines",
                line=dict(color=color, width=2, dash="dash"),
                hovertemplate=f"<b>{kw}</b> (previsto)<br>Ano %{{x}}: %{{y:.0f}} menções<extra></extra>",
            )
        )

    fig.update_layout(
        xaxis_title="Ano de publicação",
        yaxis_title="Menções por ano",
        hovermode="x unified",
    )
    render_chart(
        fig,
        caption="Sólido = histórico observado; tracejado = continuação prevista pelo mesmo modelo escolhido "
        "para cada termo. Mostra a trajetória real por trás do ranking ao lado, não só o ponto de chegada.",
    )


def _keyword_growth_ranking(articles_df: pd.DataFrame) -> None:
    st.subheader("🏷️ Tópicos com maior crescimento projetado")
    kw_exploded = explode_keywords(articles_df)
    if kw_exploded.empty or "year" not in kw_exploded.columns:
        st.info("Coluna 'keywords' não disponível nesta camada.")
        return

    counts = kw_exploded["keyword"].value_counts()
    eligible = counts[counts >= MIN_KEYWORD_OCCURRENCES].index.tolist()
    if not eligible:
        st.info(f"Nenhuma palavra-chave com pelo menos {MIN_KEYWORD_OCCURRENCES} ocorrências.")
        return

    rows = []
    results_by_keyword: dict[str, ForecastResult] = {}
    final_forecast_year = None
    for kw in eligible:
        kw_df = kw_exploded[kw_exploded["keyword"] == kw]
        series = kw_df.groupby(kw_df["year"].astype("Int64")).size()
        series.index = series.index.astype(int)
        result = fit_and_forecast(series)
        if result.insufficient_data:
            continue
        results_by_keyword[kw] = result
        final_forecast_year = result.forecast_years[-1]
        year_2025 = float(series.get(2025, series.tail(1).iloc[0] if len(series) else 0))
        year_forecast = float(result.forecast_values[-1])
        rows.append(
            {
                "keyword": kw,
                "2025 (real)": year_2025,
                f"{final_forecast_year} (previsto)": year_forecast,
                "variação": year_forecast - year_2025,
                "modelo": _MODEL_LABELS.get(result.chosen_model, result.chosen_model),
            }
        )

    if not rows:
        st.info("Não foi possível ajustar um modelo para nenhuma palavra-chave elegível.")
        return

    ranking = pd.DataFrame(rows).sort_values("variação", ascending=False)
    top = ranking.head(min(TOP_KEYWORDS_FORECAST, len(ranking))).sort_values("variação")

    sub_trend, sub_rank = st.tabs(["📈 Trajetórias", "🏆 Ranking de Crescimento"])
    with sub_trend:
        _keyword_trend_lines(
            ranking.head(TOP_KEYWORD_TRENDS)["keyword"].tolist(), results_by_keyword
        )
    with sub_rank:
        fig = go.Figure()
        fig.add_bar(
            x=top["variação"],
            y=top["keyword"],
            orientation="h",
            marker_color=[
                TOTAL_COLOR if v >= 0 else SOURCE_COLORS["ieee"] for v in top["variação"]
            ],
            hovertemplate=f"<b>%{{y}}</b><br>Variação projetada até {final_forecast_year}: %{{x:+.1f}} artigos/ano<extra></extra>",
        )
        fig.update_layout(
            xaxis_title=f"Variação (2025 → {final_forecast_year})",
            yaxis_title="",
        )
        render_chart(
            fig,
            caption=f"Mesmo motor de previsão da série de volume, aplicado a cada palavra-chave com pelo "
            f"menos {MIN_KEYWORD_OCCURRENCES} ocorrências no corpus. Mesmas ressalvas: {HOLDOUT_YEAR} é um "
            "ano parcial e o corpus é incompleto — leia como sinal direcional, não como número exato.",
        )

    with st.expander("📋 Tabela completa de tópicos avaliados"):
        st.dataframe(ranking.reset_index(drop=True), hide_index=True, width="stretch")
