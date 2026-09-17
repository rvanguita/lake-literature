"""🔎 Configuração da Busca — a query, os filtros e o intervalo de anos usados em cada base."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from lake_literature.dashboard import loaders
from lake_literature.dashboard.components import hero_banner, page_header
from lake_literature.dashboard.theme import OTHER_COLOR, SOURCE_COLORS, SOURCE_LABELS
from lake_literature.ingest.raw_upload import (
    SOURCE_UPLOAD_SPECS,
    RawUploadError,
    ingest_uploaded_file,
    save_uploaded_file,
)


def render() -> None:
    page_header(
        "🔎",
        "Configuração da Busca",
        "A query booleana, os filtros e o intervalo de anos usados em cada publisher para montar este corpus.",
    )

    configs_df = loaders.search_configs()
    if configs_df.empty:
        st.info(
            "`raw.config` ainda não foi populada — execute a etapa `raw` do pipeline "
            "(botão na barra lateral ou `uv run lake-literature --stage raw`)."
        )
        return

    hero_banner(
        "Provenance, não dado do corpus",
        "Isto é o registro da <b>busca que gerou</b> cada export (`config.csv` de cada base, ver "
        "`CLAUDE.md`) — não uma tabela de artigos. Repetir a mesma busca hoje nos sites dos "
        "publishers pode retornar resultados diferentes dos capturados aqui.",
    )

    sources = list(configs_df["source"])
    tabs = st.tabs([f"{_SOURCE_EMOJI.get(s, '📰')} {SOURCE_LABELS.get(s, s)}" for s in sources])
    for tab, (_, row) in zip(tabs, configs_df.iterrows(), strict=True):
        with tab:
            _source_card(row)


_SOURCE_EMOJI = {"ieee": "🔷", "elsevier": "🟠"}


def _source_card(row: pd.Series) -> None:
    source = row.get("source", "")
    label = SOURCE_LABELS.get(source, source)
    color = SOURCE_COLORS.get(source, OTHER_COLOR)

    st.markdown(
        f'<span style="color:{color}; font-weight:700; font-size:1.1rem;">● {label}</span>',
        unsafe_allow_html=True,
    )

    query_string = row.get("query_string") or "—"
    st.caption("Query")
    st.code(query_string, language=None, wrap_lines=True)

    col_filters, col_years = st.columns(2)
    with col_filters:
        st.caption("Filtros aplicados")
        st.write(row.get("filters") or "—")
    with col_years:
        st.caption("Intervalo de anos")
        st.write(row.get("year_range") or "—")

    search_url = row.get("search_url")
    if search_url:
        st.markdown(f"🔗 [Abrir esta busca no site original]({search_url})")

    with st.expander("Texto bruto do config.csv"):
        st.text(row.get("raw_text") or "—")
        st.caption(f"Arquivo de origem: `{row.get('source_file') or '—'}`")

    _upload_section(source)


def _upload_section(source: str) -> None:
    specs = SOURCE_UPLOAD_SPECS.get(source, {})
    if not specs:
        return
    extensions = sorted(specs)

    with st.expander("⬆️ Enviar novo arquivo para a camada raw"):
        st.caption(
            f"Aceita {', '.join(f'`.{ext}`' for ext in extensions)} — o arquivo é salvo em "
            f"`data/{source}/` e processado pelo mesmo loader do pipeline (idempotente por hash)."
        )
        uploaded = st.file_uploader(
            "Arquivo", type=extensions, key=f"raw_upload_{source}", label_visibility="collapsed"
        )
        if uploaded is not None and st.button("Processar upload", key=f"raw_upload_btn_{source}"):
            try:
                path = save_uploaded_file(source, uploaded.name, uploaded.getvalue())
                stats = ingest_uploaded_file(path)
            except RawUploadError as exc:
                st.error(str(exc))
            else:
                st.cache_data.clear()
                st.success(f"Arquivo salvo em `{path}` e processado: {stats}")
