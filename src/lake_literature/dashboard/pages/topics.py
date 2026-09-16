"""🏷️ Tópicos e Periódicos — onde o corpus publica, sobre o que, e como os temas evoluíram."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from lake_literature.dashboard import loaders
from lake_literature.dashboard.analytics import (
    cumulative_by_source,
    explode_keywords,
    source_counts_by,
    valid_years,
)
from lake_literature.dashboard.charts import (
    source_bars,
    source_lines,
    source_topn_hbar,
    stacked_area,
    topn_hbar,
)
from lake_literature.dashboard.components import (
    article_table,
    metric_row,
    page_header,
    render_chart,
    require_columns,
)
from lake_literature.dashboard.qualis import MATCH_THRESHOLD, NOT_CLASSIFIED, QUALIS_AREA
from lake_literature.dashboard.theme import CATEGORICAL_PALETTE, TREND_DOWN_COLOR, TREND_UP_COLOR

TOP_KEYWORDS_TREND = 12
TREND_MIN_YEAR = 2010
MIN_KEYWORD_OCCURRENCES = 15


def render() -> None:
    page_header(
        "🏷️",
        "Tópicos e Periódicos",
        "Concentração editorial, vocabulário temático do corpus e evolução temporal dos tópicos de pesquisa.",
    )

    articles_df = loaders.require_articles()

    col_venues, col_keywords = st.columns(2)
    with col_venues:
        _top_venues(articles_df)
    with col_keywords:
        _top_keywords(articles_df)

    st.divider()
    _capes_qualis_section(articles_df)

    if not require_columns(articles_df, ["keywords"]):
        return

    kw_lists = articles_df["keywords"].apply(
        lambda kws: sorted({str(k).strip().lower() for k in kws if str(k).strip()})
    )
    all_keywords = sorted({k for kws in kw_lists for k in kws})
    if not all_keywords:
        st.info("Nenhuma palavra-chave identificada nesta camada.")
        return

    st.divider()
    _keyword_stats(kw_lists, all_keywords)

    st.divider()
    _keyword_explorer(articles_df, kw_lists, all_keywords)

    st.divider()
    _keyword_trends(articles_df)


def _top_venues(articles_df: pd.DataFrame) -> None:
    st.subheader("Periódicos e Eventos")
    if not require_columns(articles_df, ["venue"]) or not articles_df["venue"].notna().any():
        return

    top_venues = articles_df["venue"].dropna().value_counts().head(15)
    modal_source = None
    if "source" in articles_df.columns:
        modal_source = (
            articles_df.dropna(subset=["venue"])
            .groupby("venue")["source"]
            .agg(lambda s: s.mode().iat[0])
        )

    fig = topn_hbar(
        top_venues,
        color_by=modal_source,
        x_title="Quantidade de artigos",
    )
    fig.update_traces(hovertemplate="<b>%{y}</b><br>%{x:,} artigos publicados<extra></extra>")
    render_chart(
        fig,
        caption="Concentração editorial do corpus — cada periódico é colorido pela base predominante dos "
        "artigos publicados nele.",
    )


def _top_keywords(articles_df: pd.DataFrame) -> None:
    st.subheader("Palavras-Chave")
    if not require_columns(articles_df, ["keywords"]):
        return

    kw_exploded = explode_keywords(articles_df)
    if kw_exploded.empty:
        st.info("Nenhuma palavra-chave identificada nesta camada.")
        return

    top_20_kw = kw_exploded["keyword"].value_counts().head(20).index.tolist()
    filtered_kw = kw_exploded[kw_exploded["keyword"].isin(top_20_kw)]

    if "source" in filtered_kw.columns:
        grouped = filtered_kw.groupby(["keyword", "source"]).size().unstack(fill_value=0)
        for s in ("ieee", "elsevier"):
            if s not in grouped.columns:
                grouped[s] = 0
        grouped["total"] = grouped.sum(axis=1)
    else:
        grouped = filtered_kw.groupby("keyword").size().to_frame(name="total")
        grouped["ieee"] = 0
        grouped["elsevier"] = 0

    fig = topn_hbar(
        grouped["total"], x_title="Quantidade de artigos", title="Top 20 palavras-chave"
    )
    for trace in fig.data:
        breakdown = grouped.loc[list(trace.y), ["ieee", "elsevier"]].to_numpy()
        trace.customdata = breakdown
        trace.hovertemplate = (
            "<b>%{y}</b><br>"
            "Total de artigos: %{x:,}<br>"
            "• Artigos IEEE: %{customdata[0]:,}<br>"
            "• Artigos Elsevier: %{customdata[1]:,}<extra></extra>"
        )
    render_chart(
        fig,
        caption="Tópicos mais recorrentes no corpus. Passe o mouse sobre as barras para conferir a divisão "
        "exata entre IEEE e Elsevier.",
    )


def _keyword_stats(kw_lists: pd.Series, all_keywords: list[str]) -> None:
    st.subheader("Estatísticas do Vocabulário")
    kw_counts = kw_lists.apply(len)
    metric_row(
        [
            ("🏷️ Palavras-chave únicas", f"{len(all_keywords):,}", None),
            ("📊 Média de termos por artigo", f"{kw_counts.mean():.1f}", None),
            ("🚫 Artigos sem palavras-chave", f"{(kw_counts == 0).mean():.0%}", None),
        ]
    )


def _keyword_explorer(
    articles_df: pd.DataFrame, kw_lists: pd.Series, all_keywords: list[str]
) -> None:
    st.subheader("🔎 Explorador: filtrar artigos por palavra-chave")
    selected = st.multiselect(
        "Selecione um ou mais termos (serão exibidos artigos que contenham qualquer um deles):",
        options=all_keywords,
    )
    if not selected:
        st.caption("Selecione palavras-chave acima para filtrar os artigos correspondentes.")
        return

    selected_set = set(selected)
    mask = kw_lists.apply(lambda kws: bool(set(kws) & selected_set))
    filtered = articles_df.loc[mask]
    st.caption(f"{len(filtered):,} artigos encontrados")

    if "citation_count" in filtered.columns:
        filtered = filtered.sort_values("citation_count", ascending=False, na_position="last")
    article_table(
        filtered,
        ["title", "year", "venue", "source", "citation_count", "reference_count", "doi"],
        download_key="artigos_por_palavra_chave",
    )


def _keyword_trends(articles_df: pd.DataFrame) -> None:
    st.subheader("📈 Evolução temporal dos tópicos")

    kw_year = explode_keywords(articles_df)
    if kw_year.empty or "year" not in kw_year.columns:
        st.info("Dados insuficientes para analisar tendências temporais.")
        return
    kw_year["year"] = valid_years(kw_year, lo=TREND_MIN_YEAR, hi=2026)
    kw_year = kw_year.dropna(subset=["year"]).astype({"year": int})
    if len(kw_year) < 30:
        st.info(
            f"Dados insuficientes a partir de {TREND_MIN_YEAR} para analisar tendências temporais."
        )
        return

    col_share, col_slope = st.columns(2)

    with col_share:
        _topic_share_area(kw_year)

    with col_slope:
        _rising_falling(kw_year)

    st.divider()
    _first_appearance(kw_year)


def _topic_share_area(kw_year: pd.DataFrame) -> None:
    st.markdown("**Participação anual das principais palavras-chave**")
    top_terms = kw_year["keyword"].value_counts().head(TOP_KEYWORDS_TREND).index.tolist()
    scoped = kw_year[kw_year["keyword"].isin(top_terms)]
    by_year_kw = scoped.groupby(["year", "keyword"]).size().reset_index(name="count")

    color_map = {
        kw: CATEGORICAL_PALETTE[i % len(CATEGORICAL_PALETTE)] for i, kw in enumerate(top_terms)
    }
    fig = stacked_area(
        by_year_kw,
        x="year",
        y="count",
        color="keyword",
        color_map=color_map,
        title=f"Participação (%) das top {TOP_KEYWORDS_TREND} palavras-chave por ano",
        groupnorm="percent",
    )
    fig.update_layout(
        xaxis_title=f"Ano de publicação (desde {TREND_MIN_YEAR})",
        yaxis_title="Participação entre as menções do ano (%)",
        legend_title_text="Palavra-chave",
    )
    render_chart(
        fig,
        caption=f"Área 100% empilhada: mostra como o peso relativo de cada termo mudou ano a ano, entre as "
        f"top {TOP_KEYWORDS_TREND} palavras-chave do corpus.",
    )


def _rising_falling(kw_year: pd.DataFrame) -> None:
    st.markdown("**Termos em ascensão vs. em declínio**")
    counts = kw_year["keyword"].value_counts()
    eligible = counts[counts >= MIN_KEYWORD_OCCURRENCES].index

    by_year_total = kw_year.groupby("year").size()
    slopes = {}
    for kw in eligible:
        yearly = kw_year[kw_year["keyword"] == kw].groupby("year").size()
        share = (yearly / by_year_total.reindex(yearly.index)).fillna(0.0) * 100
        if len(share) < 3:
            continue
        x = share.index.to_numpy(dtype=float)
        y = share.to_numpy(dtype=float)
        slope = np.polyfit(x - x.mean(), y, 1)[0]
        slopes[kw] = slope

    if not slopes:
        st.info(
            f"Nenhum termo com pelo menos {MIN_KEYWORD_OCCURRENCES} ocorrências para calcular tendência."
        )
        return

    slope_series = pd.Series(slopes).sort_values()
    top_slopes = pd.concat([slope_series.head(7), slope_series.tail(7)]).drop_duplicates()
    df = top_slopes.rename_axis("keyword").reset_index(name="slope")
    df["direction"] = df["slope"].apply(lambda s: "Em Alta" if s >= 0 else "Em Queda")
    df = df.sort_values("slope")

    fig = px.bar(
        df,
        x="slope",
        y="keyword",
        orientation="h",
        color="direction",
        color_discrete_map={"Em Alta": TREND_UP_COLOR, "Em Queda": TREND_DOWN_COLOR},
        title="Inclinação da participação anual (regressão linear)",
        labels={
            "slope": "Variação anual na participação (p.p./ano)",
            "keyword": "",
            "direction": "Tendência",
        },
    )
    fig.update_traces(hovertemplate="<b>%{y}</b><br>%{x:+.2f} p.p./ano<extra></extra>")
    fig.update_layout(legend_title_text="Tendência")
    render_chart(
        fig,
        caption=f"Inclinação da participação percentual anual de cada termo (mínimo {MIN_KEYWORD_OCCURRENCES} "
        "ocorrências no período), estimada por regressão linear simples.",
    )


def _first_appearance(kw_year: pd.DataFrame) -> None:
    st.markdown("**Vocabulário novo vs. fundacional**")
    counts = kw_year["keyword"].value_counts()
    eligible = counts[counts >= MIN_KEYWORD_OCCURRENCES]
    if eligible.empty:
        st.info(f"Nenhum termo com pelo menos {MIN_KEYWORD_OCCURRENCES} ocorrências.")
        return

    first_year = kw_year[kw_year["keyword"].isin(eligible.index)].groupby("keyword")["year"].min()
    df = pd.DataFrame({"first_year": first_year, "count": eligible}).reset_index(names="keyword")

    # Many terms share the same first_year (61 eligible terms here, ~39 of them
    # clustered in just 2010-2011) -- always-on text labels for every point pile
    # up and become unreadable. Identification moves to hover; only a handful
    # of standout points (highest volume + most recent debut) get a permanent
    # label, since those are the ones actually worth calling out visually and
    # are few enough not to collide.
    fig = px.scatter(
        df,
        x="first_year",
        y="count",
        hover_name="keyword",
        color="first_year",
        color_continuous_scale=["#4a3aa7", "#eda100", "#1baf7a"],
        labels={
            "first_year": "Ano da primeira menção no corpus",
            "count": "Menções totais no período",
        },
    )
    fig.update_traces(
        marker=dict(size=10, line=dict(width=1, color="rgba(255,255,255,0.4)")),
        hovertemplate="<b>%{hovertext}</b><br>1ª menção: %{x}<br>%{y:,} menções totais<extra></extra>",
    )
    fig.update_layout(coloraxis_showscale=False)

    highlight = pd.concat([df.nlargest(4, "count"), df.nlargest(4, "first_year")]).drop_duplicates(
        subset="keyword"
    )
    for idx, (_, row) in enumerate(highlight.iterrows()):
        fig.add_annotation(
            x=row["first_year"],
            y=row["count"],
            text=row["keyword"],
            showarrow=True,
            arrowhead=0,
            arrowcolor="rgba(148,163,184,0.5)",
            ax=0,
            ay=-22 if idx % 2 == 0 else 22,
            font=dict(size=10),
        )

    render_chart(
        fig,
        caption="Termos no canto superior direito são vocabulário recente que já ganhou volume; termos à "
        "esquerda com contagem alta são vocabulário fundacional da área. Passe o mouse sobre qualquer ponto "
        "para ver o termo; os rótulos fixos destacam apenas os pontos mais extremos (maior volume e estreia "
        "mais recente), para não sobrepor os demais.",
    )


def _capes_qualis_section(articles_df: pd.DataFrame) -> None:
    st.subheader("🎓 Classificação CAPES/Qualis")
    if not require_columns(articles_df, ["venue"]) or not articles_df["venue"].notna().any():
        return

    venues = sorted(articles_df["venue"].dropna().unique())
    match_df = loaders.venue_qualis_map(tuple(venues))
    match_df["estrato"] = match_df["estrato"].fillna(NOT_CLASSIFIED)

    counts = articles_df["venue"].value_counts()
    match_df["articles"] = match_df["venue"].map(counts).fillna(0).astype(int)
    match_df = match_df.sort_values("articles", ascending=False)

    n_classified = int((match_df["estrato"] != NOT_CLASSIFIED).sum())
    a1_venues = match_df.loc[match_df["estrato"] == "A1", "venue"]
    a1_articles_df = articles_df[articles_df["venue"].isin(a1_venues)]
    pct_a1 = (len(a1_articles_df) / len(articles_df) * 100) if len(articles_df) else 0.0

    metric_row(
        [
            ("📚 Periódicos classificados", f"{n_classified}/{len(match_df)}", None),
            ("🥇 Periódicos A1", f"{len(a1_venues)}", None),
            ("📄 Artigos em periódicos A1", f"{len(a1_articles_df):,}", f"{pct_a1:.1f}% do corpus"),
        ]
    )

    st.caption(
        f"Classificação oficial CAPES/Qualis (quadriênio 2017-2020, área **{QUALIS_AREA}** -- a "
        "última avaliação por periódico; a partir de 2025-2028 a CAPES passa a avaliar por artigo, não "
        "mais por veículo). Cada periódico do corpus é casado com o título de referência por "
        f"similaridade textual (corte de {MATCH_THRESHOLD:.0f}%), já que grafias variam entre bases "
        "(ex.: `&` vs. `and`, sufixos `(Print)`/`(Online)`). Um periódico não encontrado com confiança "
        f'suficiente aparece como "{NOT_CLASSIFIED}" -- nunca como uma nota adivinhada.'
    )
    st.dataframe(
        match_df.rename(
            columns={
                "venue": "Periódico (corpus)",
                "matched_title": "Título casado (CAPES)",
                "estrato": "Estrato",
                "score": "Similaridade (%)",
                "articles": "Artigos",
            }
        ),
        hide_index=True,
        width="stretch",
    )

    if a1_articles_df.empty:
        st.info("Nenhum artigo em periódico classificado A1 nesta camada/filtro.")
        return

    st.markdown("#### Análise -- somente periódicos A1")
    col_year, col_cum = st.columns(2)
    with col_year:
        years_df = a1_articles_df.copy()
        years_df["year"] = valid_years(years_df)
        years_df = years_df.dropna(subset=["year"]).astype({"year": int})
        by_year = source_counts_by(years_df, "year").sort_values("year")
        if by_year.empty:
            st.info("Sem anos válidos para este gráfico.")
        else:
            fig = source_bars(by_year, "year", total_line=True)
            fig.update_layout(
                hovermode="x unified", xaxis_title="Ano de publicação", yaxis_title="Artigos"
            )
            render_chart(fig, caption="Volume anual de artigos publicados em periódicos A1.")
    with col_cum:
        cum = cumulative_by_source(a1_articles_df)
        if cum.empty:
            st.info("Sem anos válidos para o acumulado.")
        else:
            fig = source_lines(
                cum, "year", title="Acumulado em periódicos A1", y_title="Artigos acumulados"
            )
            fig.update_layout(xaxis_title="Ano de publicação")
            render_chart(
                fig,
                caption=f"Ao final do período, {int(cum['total'].iloc[-1]):,} artigos acumulados em "
                "periódicos A1.",
            )

    top_a1 = (
        source_counts_by(a1_articles_df, "venue").sort_values("total", ascending=False).head(15)
    )
    fig = source_topn_hbar(top_a1, "venue", x_title="Artigos")
    render_chart(fig, caption="Periódicos A1 mais publicados pelo corpus.")
