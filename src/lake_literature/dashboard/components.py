"""Shared UI pieces used by more than one page (sidebar, headers, tables)."""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from lake_literature.dashboard import loaders
from lake_literature.dashboard.airflow_client import AirflowError
from lake_literature.dashboard.pipeline_control import (
    DAG_IDS,
    STAGE_LABELS,
    poll_run,
    trigger_stage,
)
from lake_literature.dashboard.theme import SOURCE_LABELS, polish_figure_layout, theme_tokens

logger = logging.getLogger(__name__)

_TERMINAL_STATES = ("success", "failed", "error")


def _refresh_runs() -> None:
    """Poll every non-terminal run against Airflow. Clears the data cache the
    first time a run is observed to have finished, so the stats reflect it
    without a second manual refresh.
    """
    runs = st.session_state.pipeline_runs
    became_success = False
    for stage, run_ref in list(runs.items()):
        prev_state = run_ref.get("state")
        if prev_state in _TERMINAL_STATES:
            continue
        try:
            updated = poll_run(run_ref)
        except AirflowError as exc:
            logger.warning("_refresh_runs: could not poll stage %r", stage, exc_info=True)
            updated = dict(run_ref, state="error", error=str(exc))
        runs[stage] = updated
        if updated.get("state") == "success" and prev_state != "success":
            became_success = True
    if became_success:
        st.cache_data.clear()


def _trigger(stage: str) -> None:
    try:
        st.session_state.pipeline_runs[stage] = trigger_stage(stage)
    except AirflowError as exc:
        logger.warning("_trigger: could not trigger stage %r", stage, exc_info=True)
        st.session_state.pipeline_runs[stage] = {
            "stage": stage,
            "dag_id": DAG_IDS.get(stage, stage),
            "dag_run_id": None,
            "state": "error",
            "error": str(exc),
        }


def _prepare_filter_state(articles_df: pd.DataFrame) -> tuple[list[int], list[str], list[str]]:
    """Keep persisted widget values valid when a new medallion layer appears."""
    years = (
        pd.to_numeric(articles_df.get("year", pd.Series(dtype="float64")), errors="coerce")
        .dropna()
        .astype(int)
    )
    year_options = sorted(years[(years >= 1900) & (years <= 2100)].unique().tolist())
    sources = (
        sorted(articles_df["source"].dropna().astype(str).unique().tolist())
        if "source" in articles_df
        else []
    )
    venues = (
        sorted(articles_df["venue"].dropna().astype(str).unique().tolist())
        if "venue" in articles_df
        else []
    )

    if year_options:
        bounds = (year_options[0], year_options[-1])
        current = st.session_state.get("global_year_range", bounds)
        if isinstance(current, (int, float)):
            current = (int(current), int(current))
            st.session_state.global_year_range = current
        if "global_year_range" in st.session_state and (
            not isinstance(current, (tuple, list))
            or len(current) != 2
            or current[0] < bounds[0]
            or current[1] > bounds[1]
        ):
            st.session_state.global_year_range = bounds
    else:
        st.session_state.pop("global_year_range", None)

    st.session_state.global_sources = [
        value for value in st.session_state.get("global_sources", []) if value in sources
    ]
    st.session_state.global_venues = [
        value for value in st.session_state.get("global_venues", []) if value in venues
    ]
    return year_options, sources, venues


def _render_relevance_filter() -> None:
    """Opt-in cut on the semantic relevance score.

    Defaults to off: the score is an aid to screening, not ground truth, so it
    must never silently change the numbers someone sees on first load. The
    threshold is expressed as a percentile of this corpus, which is easier to
    reason about than a raw cosine value.
    """
    signals = loaders.semantics()
    if signals.empty or "relevance_score" not in signals.columns:
        return

    st.checkbox(
        "Excluir artigos fora do escopo",
        key="exclude_offtopic",
        help=(
            "Usa o score de relevância semântica (`--stage semantic`) para descartar artigos "
            "distantes do tema da revisão — na prática, o grupo de logística/cadeia de "
            "suprimentos que a busca por *distribution system planning* trouxe junto."
        ),
    )
    if not st.session_state.get("exclude_offtopic"):
        st.session_state.pop("global_min_relevance", None)
        return

    percentile = st.slider(
        "Descartar abaixo do percentil",
        min_value=1,
        max_value=30,
        value=10,
        key="offtopic_percentile",
        help="10 remove os 10% menos relevantes do corpus.",
    )
    threshold = float(signals["relevance_score"].quantile(percentile / 100))
    st.session_state.global_min_relevance = threshold
    st.caption(f"Corte: score ≥ {threshold:.3f}")


def render_global_filters(articles_df: pd.DataFrame) -> None:
    """Render filters shared by every page and persist them in session state."""
    years, sources, venues = _prepare_filter_state(articles_df)
    st.subheader("🎯 Filtros globais")
    if years:
        if years[0] < years[-1]:
            slider_kwargs = {}
            if "global_year_range" not in st.session_state:
                slider_kwargs["value"] = (years[0], years[-1])
            st.slider(
                "Ano de publicação",
                min_value=years[0],
                max_value=years[-1],
                key="global_year_range",
                help="Aplica-se a todos os indicadores, gráficos, tabelas e exportações.",
                **slider_kwargs,
            )
        else:
            st.session_state.global_year_range = (years[0], years[0])
            st.caption(f"Ano de publicação: {years[0]}")
    else:
        st.caption("Ano de publicação não disponível nesta camada.")

    if sources:
        st.multiselect(
            "Fonte",
            options=sources,
            key="global_sources",
            format_func=lambda value: SOURCE_LABELS.get(value, value.title()),
        )
    else:
        st.caption("Fonte não disponível na camada ativa.")
    if venues:
        st.multiselect(
            "Periódico / evento",
            options=venues,
            key="global_venues",
            placeholder="Todos os periódicos",
        )
    else:
        st.caption("Periódico / evento não disponível na camada ativa.")

    _render_relevance_filter()

    if st.button("Limpar filtros", key="clear_global_filters", use_container_width=True):
        st.session_state.global_year_range = (years[0], years[-1]) if years else None
        st.session_state.global_sources = []
        st.session_state.global_venues = []
        st.session_state.pop("global_min_relevance", None)
        st.session_state.exclude_offtopic = False
        st.rerun()

    _, filtered = loaders.filtered_articles()
    if filtered.empty:
        st.warning("Os filtros atuais não retornam artigos.")
    elif len(filtered) != len(articles_df):
        st.caption(f"Exibindo **{len(filtered):,}** de **{len(articles_df):,} artigos")


def render_sidebar() -> None:
    """Pipeline status + Airflow controls; rendered on every page."""
    st.session_state.setdefault("pipeline_runs", {})
    _refresh_runs()

    layer, articles_df = loaders.articles()

    with st.sidebar:
        if not articles_df.empty:
            render_global_filters(articles_df)
            st.divider()
        with st.expander("📋 Contagem detalhada de linhas por tabela"):
            st.dataframe(loaders.row_counts(), hide_index=True, width="stretch")

        st.divider()
        st.subheader("⚙️ Executar pipeline (via Airflow)")

        for stage in ("raw", "bronze", "silver", "gold", "embed", "semantic"):
            if st.button(f"▶ Executar {STAGE_LABELS[stage]}", key=f"run_{stage}"):
                with st.spinner(f"Disparando {STAGE_LABELS[stage]} no Airflow..."):
                    _trigger(stage)

        if st.button("⏩ Executar tudo (raw→bronze→silver→gold→embed→semantic)", key="run_all"):
            with st.spinner("Disparando o pipeline completo no Airflow..."):
                _trigger("all")

        if st.session_state.pipeline_runs:
            with st.container(border=True):
                st.markdown("**Execuções disparadas**")
                for stage, run_ref in st.session_state.pipeline_runs.items():
                    label = STAGE_LABELS.get(stage, stage)
                    state = run_ref.get("state")
                    run_id = run_ref.get("dag_run_id")
                    if state == "success":
                        extra = ""
                        tasks = run_ref.get("task_instances") or []
                        if tasks:
                            n_ok = sum(1 for t in tasks if t.get("state") == "success")
                            extra = f" ({n_ok}/{len(tasks)} tarefas concluídas)"
                        st.success(f"{label}: concluído{extra}")
                    elif state == "failed":
                        st.error(
                            f"{label}: falhou (execução `{run_id}`, verifique os logs no Airflow)"
                        )
                    elif state == "error":
                        st.error(f"{label}: {run_ref.get('error', 'erro desconhecido')}")
                    else:
                        st.info(f"{label}: {state} (execução `{run_id}`)")

        st.divider()
        if st.button("🔄 Atualizar dados"):
            st.cache_data.clear()
            st.rerun()
        if layer != "none" and not articles_df.empty:
            _, filtered_df = loaders.filtered_articles()
            st.caption(f"{len(filtered_df):,}/{len(articles_df):,} artigos · camada **{layer}**")


def page_header(icon: str, title: str, description: str) -> None:
    """Consistent page title block."""
    st.title(f"{icon} {title}")
    st.caption(description)


def metric_row(metrics: list[tuple[str, str, str | None]]) -> None:
    """A bordered row of metrics: list of (label, value, delta|None)."""
    with st.container(border=True):
        cols = st.columns(len(metrics))
        for col, (label, value, delta) in zip(cols, metrics, strict=True):
            col.metric(label, value, delta)


def hero_banner(title: str, body_html: str) -> None:
    """Gradient executive-summary banner used at the top of a few pages."""
    t = theme_tokens()
    st.markdown(
        f"""
        <div style="
            background: {t["metric_bg"]};
            border: 1px solid {t["metric_border"]};
            border-radius: 0.9rem;
            padding: 1.1rem 1.4rem;
            margin-bottom: 1rem;
        ">
            <div style="font-size: 1.05rem; font-weight: 700; color: {t["metric_value"]}; margin-bottom: .35rem;">
                {title}
            </div>
            <div style="color: {t["muted"]}; font-size: .92rem; line-height: 1.5;">
                {body_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def require_columns(df: pd.DataFrame, cols: list[str], message: str | None = None) -> bool:
    """Guard a chart function against a layer that lacks required columns.

    Returns True (and renders nothing) if all `cols` are present; otherwise
    renders a consistent `st.info` and returns False so the caller can
    `return` early.
    """
    missing = [c for c in cols if c not in df.columns]
    if not missing:
        return True
    st.info(
        message
        or f"Coluna(s) {', '.join(f'`{c}`' for c in missing)} não disponível(is) nesta camada."
    )
    return False


def render_chart(fig, *, caption: str | None = None, height: int | None = None) -> None:
    """Apply the shared dark theme, render the figure, and add its caption.

    Replaces the `polish_figure_layout(fig); st.plotly_chart(...); st.caption(...)`
    triplet that used to be repeated in every chart function.
    """
    polish_figure_layout(fig, height=height)
    st.plotly_chart(fig, width="stretch")
    if caption:
        st.caption(caption)


# Shared table formatting for the "pick a reference" tables -- DOI becomes a
# clickable doi.org link.
_ARTICLE_TABLE_CONFIG = {
    "title": st.column_config.TextColumn("Título", width="large"),
    "year": st.column_config.NumberColumn("Ano", format="%d"),
    "venue": st.column_config.TextColumn("Periódico / Evento"),
    "source": st.column_config.TextColumn("Base"),
    "citation_count": st.column_config.NumberColumn("Citações", format="%d"),
    "reference_count": st.column_config.NumberColumn("Referências", format="%d"),
    "author_count": st.column_config.NumberColumn("Autores", format="%d"),
    "doi_link": st.column_config.LinkColumn("DOI", display_text=r"10\..*"),
}


def article_table(df: pd.DataFrame, columns: list[str], download_key: str = "") -> None:
    """Article table with clickable DOIs, formatted numbers and a CSV export."""
    table = df.copy()
    if "doi" in table.columns:
        table["doi_link"] = "https://doi.org/" + table["doi"].astype(str)
        columns = [c for c in columns if c != "doi"] + ["doi_link"]
    present = [c for c in columns if c in table.columns]
    st.dataframe(
        table[present],
        hide_index=True,
        width="stretch",
        column_config={k: v for k, v in _ARTICLE_TABLE_CONFIG.items() if k in present},
    )
    if download_key:
        st.download_button(
            "⬇️ Baixar como CSV",
            data=table[present].to_csv(index=False).encode("utf-8"),
            file_name=f"{download_key}.csv",
            mime="text/csv",
            key=f"dl_{download_key}",
        )
