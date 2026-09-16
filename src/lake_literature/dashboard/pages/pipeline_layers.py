"""🏗️ Camadas & Pipeline — o funil raw → bronze → silver → gold, camada a camada."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from lake_literature.dashboard import loaders
from lake_literature.dashboard.components import hero_banner, metric_row, page_header, render_chart
from lake_literature.dashboard.theme import (
    CATEGORICAL_PALETTE,
    OTHER_COLOR,
    SOURCE_COLORS,
    SOURCE_LABELS,
    TOTAL_COLOR,
    hex_to_rgba,
)

LAYER_ORDER = ("raw", "bronze", "silver", "gold")


def render() -> None:
    page_header(
        "🏗️",
        "Camadas & Pipeline",
        "O funil raw → bronze → silver → gold: quanto sobrevive em cada etapa, por que, e onde a "
        "cobertura de metadados melhora ou piora.",
    )

    hero_banner(
        "Sem histórico de execuções",
        "Não existe uma tabela de histórico de runs no pipeline — as estatísticas de cada estágio só vão "
        "para <code>print</code> e para os logs do Airflow, e silver/gold são truncadas e reconstruídas a "
        "cada execução. Todos os números desta página são calculados ao vivo a partir do estado atual das "
        "quatro bases MySQL.",
    )

    funnel_df = loaders.layer_funnel()
    row_counts = loaders.row_counts()

    if funnel_df.empty or funnel_df[["raw", "bronze", "silver", "gold"]].sum().sum() == 0:
        st.warning(
            "Nenhum dado encontrado em nenhuma camada ainda. Execute o pipeline "
            "(`uv run lake-literature --stage all`) e recarregue esta página."
        )
        return

    _headline_metrics(funnel_df)
    st.divider()
    _sankey_funnel(funnel_df)
    st.divider()
    _retention_by_stage(funnel_df)
    st.divider()
    _drift_check(funnel_df)
    st.divider()
    _metadata_coverage_by_layer()
    st.divider()
    with st.expander("📋 Contagem bruta por tabela (todas as camadas)"):
        st.dataframe(row_counts, hide_index=True, width="stretch")


def _headline_metrics(funnel_df: pd.DataFrame) -> None:
    totals = funnel_df[["raw", "bronze", "silver", "gold"]].sum()
    dropped = int(funnel_df["dropped_no_doi"].sum())
    metric_row(
        [
            ("📥 Raw", f"{int(totals['raw']):,}", "linhas CSV + entradas bib"),
            ("🥉 Bronze", f"{int(totals['bronze']):,}", None),
            (
                "🥈 Silver",
                f"{int(totals['silver']):,}",
                f"−{dropped} sem DOI" if dropped else "sem perdas",
            ),
            ("🥇 Gold", f"{int(totals['gold']):,}", None),
        ]
    )


def _sankey_funnel(funnel_df: pd.DataFrame) -> None:
    st.subheader("Funil raw → bronze → silver → gold")

    labels = []
    label_index: dict[str, int] = {}

    def _idx(label: str) -> int:
        if label not in label_index:
            label_index[label] = len(labels)
            labels.append(label)
        return label_index[label]

    sources, targets, values, link_colors = [], [], [], []
    for _, row in funnel_df.iterrows():
        src_label = SOURCE_LABELS.get(row["source"], row["source"])
        color = SOURCE_COLORS.get(row["source"], OTHER_COLOR)

        raw_node = _idx(f"Raw ({src_label})")
        bronze_node = _idx(f"Bronze ({src_label})")
        silver_node = _idx(f"Silver ({src_label})")
        gold_node = _idx(f"Gold ({src_label})")
        dropped_node = _idx("Descartado (sem DOI)")

        if row["raw"] > 0:
            sources.append(raw_node)
            targets.append(bronze_node)
            values.append(row["raw"])
            link_colors.append(color)

        kept_to_silver = max(row["bronze"] - row["dropped_no_doi"], 0)
        if kept_to_silver > 0:
            sources.append(bronze_node)
            targets.append(silver_node)
            values.append(kept_to_silver)
            link_colors.append(color)
        if row["dropped_no_doi"] > 0:
            sources.append(bronze_node)
            targets.append(dropped_node)
            values.append(row["dropped_no_doi"])
            link_colors.append(OTHER_COLOR)

        if row["gold"] > 0:
            sources.append(silver_node)
            targets.append(gold_node)
            values.append(row["gold"])
            link_colors.append(color)

    fig = go.Figure(
        go.Sankey(
            node=dict(
                label=labels,
                pad=18,
                thickness=16,
                color=CATEGORICAL_PALETTE[0],
                line=dict(color="rgba(255,255,255,0.15)", width=0.5),
            ),
            link=dict(
                source=sources,
                target=targets,
                value=values,
                color=[hex_to_rgba(c, 0.55) for c in link_colors],
            ),
        )
    )
    fig.update_layout(title="Volume de artigos por etapa e por base, com as perdas rotuladas")
    render_chart(
        fig,
        caption="A perda visível ('Descartado (sem DOI)') acontece no silver: artigos bronze sem DOI "
        "normalizado nunca chegam a formar um registro silver (`silver_articles.py`). Bronze pode conter "
        "mais linhas que a soma direta do raw porque é upsert-only e nunca remove linhas órfãs (ver o "
        "painel de drift abaixo).",
    )


def _retention_by_stage(funnel_df: pd.DataFrame) -> None:
    st.subheader("Retenção por etapa e por base")
    long_df = funnel_df.melt(
        id_vars="source",
        value_vars=["raw", "bronze", "silver", "gold"],
        var_name="layer",
        value_name="count",
    )
    long_df["layer"] = pd.Categorical(long_df["layer"], categories=LAYER_ORDER, ordered=True)
    long_df = long_df.sort_values("layer")

    fig = go.Figure()
    for src in ("ieee", "elsevier"):
        sub = long_df[long_df["source"] == src]
        fig.add_bar(
            x=sub["layer"],
            y=sub["count"],
            name=SOURCE_LABELS.get(src, src),
            marker_color=SOURCE_COLORS.get(src),
        )
    fig.update_layout(barmode="stack")

    totals = long_df.groupby("layer", observed=True)["count"].sum().reindex(LAYER_ORDER)
    fig.add_trace(
        go.Scatter(
            x=list(LAYER_ORDER),
            y=totals.values,
            name="Total",
            mode="lines+markers",
            line=dict(color=TOTAL_COLOR, width=2.5),
            marker=dict(size=8),
        )
    )
    fig.update_layout(xaxis_title="Camada", yaxis_title="Artigos")
    render_chart(
        fig,
        caption="Bronze deduplica apenas dentro de cada fonte (chave `(source, source_id)`); silver e gold "
        "então convergem para o mesmo total porque não há sobreposição de DOI entre IEEE e Elsevier neste "
        "corpus.",
    )


def _drift_check(funnel_df: pd.DataFrame) -> None:
    st.subheader("⚠️ Verificação de drift: bronze vs. raw")
    drift = funnel_df.copy()
    drift["drift"] = drift["bronze"] - drift["raw"]
    drift_display = drift[["source", "raw", "bronze", "drift"]].copy()
    drift_display["source"] = drift_display["source"].map(lambda s: SOURCE_LABELS.get(s, s))

    has_drift = (drift["drift"] != 0).any()
    st.dataframe(drift_display, hide_index=True, width="stretch")
    if has_drift:
        st.warning(
            "Bronze diverge do raw para pelo menos uma base. Bronze é upsert-only e nunca remove linhas "
            "órfãs (`_upsert` em `bronze_articles.py`) — se um arquivo `.bib`/CSV for removido de `data/`, "
            "suas linhas bronze permanecem. Um `bronze > raw` positivo é esse sintoma; investigue antes de "
            "confiar nas contagens de bronze como espelho fiel do raw atual."
        )
    else:
        st.success("Bronze e raw estão alinhados para as duas bases — sem sinal de drift.")


def _metadata_coverage_by_layer() -> None:
    st.subheader("Cobertura de metadados por camada")
    by_layer = loaders.articles_by_layer()

    fields = ["doi", "abstract", "keywords", "citation_count", "has_pdf"]
    field_labels = {
        "doi": "DOI",
        "abstract": "Resumo",
        "keywords": "Palavras-chave",
        "citation_count": "Citações",
        "has_pdf": "PDF vinculado",
    }
    rows = []
    for layer in ("bronze", "silver", "gold"):
        df = by_layer.get(layer, pd.DataFrame())
        if df.empty:
            continue
        for field in fields:
            if field not in df.columns:
                continue
            if field in ("keywords",):
                pct = df[field].apply(lambda v: isinstance(v, list) and len(v) > 0).mean()
            elif field == "has_pdf":
                pct = df[field].fillna(False).astype(bool).mean()
            else:
                pct = df[field].notna().mean()
                if df[field].dtype == object:
                    pct = df[field].fillna("").astype(str).str.strip().ne("").mean()
            rows.append({"layer": layer, "field": field_labels[field], "coverage": pct * 100})

    if not rows:
        st.info("Nenhuma camada com dados suficientes para comparar cobertura de metadados.")
        return

    coverage_df = pd.DataFrame(rows)
    coverage_df["layer"] = pd.Categorical(
        coverage_df["layer"], categories=["bronze", "silver", "gold"], ordered=True
    )
    fig = px.bar(
        coverage_df.sort_values("layer"),
        x="field",
        y="coverage",
        color="layer",
        barmode="group",
        color_discrete_sequence=[
            CATEGORICAL_PALETTE[1],
            CATEGORICAL_PALETTE[0],
            CATEGORICAL_PALETTE[2],
        ],
        labels={"field": "", "coverage": "% preenchido", "layer": "Camada"},
    )
    fig.update_traces(hovertemplate="<b>%{x}</b><br>%{data.name}: %{y:.1f}%<extra></extra>")
    render_chart(
        fig,
        caption="Mostra o que cada camada ganha e perde: gold projeta silver descartando `issn`, `volume`, "
        "`issue`, `pages` e as flags de qualidade — mas mantém `sources` (adicionado nesta refatoração) "
        "para permitir a quebra IEEE/Elsevier também no gold.",
    )
