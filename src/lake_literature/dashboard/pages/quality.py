"""🧩 Qualidade e RAG — riqueza de metadados, cobertura de texto completo e chunks."""

from __future__ import annotations

import re

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from lake_literature.dashboard import loaders
from lake_literature.dashboard.components import hero_banner, metric_row, page_header, render_chart, require_columns
from lake_literature.dashboard.search import semantic_search
from lake_literature.dashboard.theme import CATEGORICAL_PALETTE, CHART_HEIGHT, SOURCE_COLORS, theme_tokens
from lake_literature.transform.gold_articles import CHUNK_MAX_CHARS

SEARCH_DEMO_MAX_RESULTS = 10


def render() -> None:
    page_header(
        "🧩",
        "Qualidade e RAG",
        "Diagnóstico do corpus como fonte para RAG: metadados, texto completo e fragmentos (chunks).",
    )

    articles_df = loaders.require_articles()
    chunks_df = loaders.filtered_chunks()

    pdf_share = (
        articles_df["has_pdf"].fillna(False).astype(bool).mean()
        if "has_pdf" in articles_df.columns
        else 0.0
    )
    hero_banner(
        "Diagnóstico RAG",
        f"O corpus oferece <b>{pdf_share:.0%}</b> de cobertura de texto completo e "
        f"<b>{len(chunks_df):,}</b> chunks prontos para recuperação.",
    )

    _metadata_richness(articles_df)
    st.divider()
    _fulltext_coverage(articles_df, chunks_df)
    st.divider()
    _chunks(chunks_df)
    st.divider()
    _embedding_readiness(chunks_df)
    st.divider()
    _search_demo(chunks_df)


def _embedding_readiness(chunks_df: pd.DataFrame) -> None:
    st.subheader("🧠 Prontidão de embeddings")
    total = len(chunks_df)
    with_embedding = (
        int(chunks_df["embedding"].notna().sum()) if "embedding" in chunks_df.columns else 0
    )
    pending = total - with_embedding
    pct = (with_embedding / total * 100) if total else 0.0
    t = theme_tokens()

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=pct,
            number={"suffix": "%", "font": {"color": t["chart_annotation"]}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": t["chart_text"]},
                "bar": {"color": CATEGORICAL_PALETTE[0]},
                "bgcolor": t["chart_bg"],
                "borderwidth": 0,
            },
            title={"text": "% de chunks com embedding gerado", "font": {"color": t["chart_text"], "size": 14}},
        )
    )
    if with_embedding and "embed_model" in chunks_df.columns:
        model_used = chunks_df["embed_model"].dropna().mode()
        model_caption = (
            f"Gerados com `{model_used.iat[0]}` — a etapa `embed` do pipeline "
            "(`transform/embeddings.py`) roda 100% local via `fastembed`, sem chave de API."
        )
    else:
        model_caption = (
            "A coluna `embedding` existe no esquema (`gold_models.Chunk`) mas nenhum chunk foi processado "
            "ainda — este é o principal bloqueio para usar o corpus como base de um RAG real."
        )
    render_chart(
        fig,
        height=260,
        caption=f"{with_embedding:,} de {total:,} chunks têm embedding. {model_caption}",
    )

    if pending > 0:
        if st.button(f"🚀 Gerar embeddings agora ({pending:,} chunks pendentes)", key="generate_embeddings"):
            _run_embedding_generation(pending)


def _run_embedding_generation(pending: int) -> None:
    from lake_literature.db.engines import get_session
    from lake_literature.transform.embeddings import build_embeddings

    progress_bar = st.progress(0.0, text=f"Gerando embeddings (0/{pending})...")

    def on_progress(done: int, total_pending: int) -> None:
        progress_bar.progress(
            min(done / total_pending, 1.0), text=f"Gerando embeddings ({done:,}/{total_pending:,})..."
        )

    session = get_session("gold")
    try:
        with st.spinner("Carregando o modelo de embeddings (primeira execução baixa os pesos)..."):
            stats = build_embeddings(session, on_progress=on_progress)
    finally:
        session.close()

    st.success(f"{stats['embedded']:,} chunks embedados. Atualizando a página...")
    st.cache_data.clear()
    st.rerun()


def _fulltext_coverage(articles_df: pd.DataFrame, chunks_df: pd.DataFrame) -> None:
    st.subheader("📄 Cobertura de texto completo")
    if not require_columns(articles_df, ["has_pdf"]):
        return

    n_total = len(articles_df)
    n_with_pdf = int(articles_df["has_pdf"].fillna(False).astype(bool).sum())

    dois_with_fulltext = set()
    if not chunks_df.empty and "chunk_type" in chunks_df.columns and "doi" in chunks_df.columns:
        dois_with_fulltext = set(chunks_df.loc[chunks_df["chunk_type"] == "fulltext", "doi"].dropna())
    n_with_fulltext_chunks = (
        int(articles_df["doi"].isin(dois_with_fulltext).sum()) if "doi" in articles_df.columns else 0
    )
    n_pdf_no_chunks = n_with_pdf - n_with_fulltext_chunks

    funnel_df = pd.DataFrame(
        {
            "stage": ["Todos os artigos", "Com PDF vinculado", "Com chunks de texto completo"],
            "count": [n_total, n_with_pdf, n_with_fulltext_chunks],
        }
    )
    col_funnel, col_metrics = st.columns([2, 1])
    with col_funnel:
        fig = px.funnel(funnel_df, x="count", y="stage", title="Funil de disponibilidade de texto completo")
        fig.update_traces(marker_color=[CATEGORICAL_PALETTE[0], CATEGORICAL_PALETTE[3], CATEGORICAL_PALETTE[2]])
        render_chart(fig)
    with col_metrics:
        metric_row(
            [
                ("📎 Artigos com PDF", f"{n_with_pdf:,}", f"{n_with_pdf / n_total:.1%}" if n_total else None),
            ]
        )
        metric_row(
            [
                (
                    "⚠️ PDFs sem chunks de texto",
                    f"{max(n_pdf_no_chunks, 0):,}",
                    "extração falhou ou PDF vazio" if n_pdf_no_chunks > 0 else "todos processados",
                ),
            ]
        )
    st.caption(
        f"Apenas {n_with_pdf / n_total:.1%} dos artigos têm PDF — os PDFs do corpus vêm exclusivamente dos "
        "bulk-downloads do IEEE, então a Elsevier tem 0% de cobertura de texto completo. A extração de PDF "
        "(`gold_articles.py`) engole falhas silenciosamente, então um PDF que falhou é indistinguível de um "
        "PDF sem texto extraível — o card '⚠️ PDFs sem chunks' acima é o sinal disso."
    )


def _metadata_richness(articles_df: pd.DataFrame) -> None:
    st.subheader("🗂️ Riqueza de metadados por base")
    if not require_columns(articles_df, ["source"]):
        return

    richness = articles_df.copy()
    richness["abstract_len"] = (
        richness["abstract"].fillna("").astype(str).str.len()
        if "abstract" in richness
        else 0
    )
    richness["n_keywords"] = (
        richness["keywords"].apply(lambda k: len(k) if isinstance(k, list) else 0)
        if "keywords" in richness
        else 0
    )
    n_no_keywords = int((richness["n_keywords"] == 0).sum())
    n_no_abstract = int((richness["abstract_len"] == 0).sum())
    agg = (
        richness.groupby("source")
        .agg(mean_abstract=("abstract_len", "mean"), mean_keywords=("n_keywords", "mean"))
        .reset_index()
    )

    col_abs, col_kw = st.columns(2)
    with col_abs:
        fig = px.bar(
            agg,
            x="source",
            y="mean_abstract",
            color="source",
            color_discrete_map=SOURCE_COLORS,
            title="Comprimento médio do resumo",
            labels={"source": "Base", "mean_abstract": "Caracteres"},
        )
        fig.update_traces(hovertemplate="<b>%{x}</b>: %{y:,.0f} caracteres<extra></extra>")
        fig.update_layout(xaxis_title="", yaxis_title="Caracteres", showlegend=False)
        render_chart(fig, height=CHART_HEIGHT)
    with col_kw:
        fig = px.bar(
            agg,
            x="source",
            y="mean_keywords",
            color="source",
            color_discrete_map=SOURCE_COLORS,
            title="Média de palavras-chave por artigo",
            labels={"source": "Base", "mean_keywords": "Palavras-chave"},
        )
        fig.update_traces(hovertemplate="<b>%{x}</b>: %{y:.1f} termos<extra></extra>")
        fig.update_layout(xaxis_title="", yaxis_title="Palavras-chave", showlegend=False)
        render_chart(fig, height=CHART_HEIGHT)

    st.caption(
        f"⚠️ A aparente vantagem do IEEE na contagem de palavras-chave decorre da consolidação no estágio "
        "bronze de `Author Keywords` e `IEEE Terms` (vocabulário controlado) em um único campo sem "
        f"deduplicação, enquanto a Elsevier fornece apenas as palavras-chave indicadas pelos autores. "
        f"Hoje {n_no_keywords:,} artigos estão sem nenhuma keyword e {n_no_abstract:,} sem resumo."
    )


def _chunks(chunks_df: pd.DataFrame) -> None:
    st.subheader("🧩 Fragmentos (chunks) preparados para embedding")
    if chunks_df.empty:
        st.info(
            "`lit_gold.chunks` ainda não foi populada — execute a etapa `gold` do pipeline "
            "(botão na barra lateral ou `uv run lake-literature --stage gold`)."
        )
        return

    if not require_columns(chunks_df, ["chunk_type"], "A tabela de chunks não possui o campo `chunk_type`."):
        return
    by_type = chunks_df["chunk_type"].value_counts().rename_axis("type").reset_index(name="count")
    by_type["label_pt"] = by_type["type"].map({"abstract": "Resumo (Abstract)", "fulltext": "Texto Completo (Fulltext)"})

    col_type, col_len = st.columns(2)
    with col_type:
        fig = px.pie(by_type, names="label_pt", values="count", title="Proporção de chunks por tipo")
        fig.update_traces(
            texttemplate="<b>%{label}</b><br><b>%{value:,} (%{percent})</b>",
            hovertemplate="<b>%{label}</b>: %{value:,} chunks (%{percent})<extra></extra>",
        )
        render_chart(
            fig,
            height=CHART_HEIGHT,
            caption="`abstract` = 1 fragmento por artigo (título + palavras-chave + resumo); `fulltext` = "
            "fragmentos extraídos diretamente dos PDFs dos artigos disponíveis.",
        )
    with col_len:
        if require_columns(chunks_df, ["char_len"]):
            length_df = chunks_df.dropna(subset=["char_len"])
            # In overlay mode the last category painted sits on top -- draw
            # the smaller-volume chunk type last so it isn't hidden behind
            # the larger one wherever their bins overlap.
            type_order = (
                length_df["chunk_type"].value_counts().sort_values(ascending=False).index.tolist()
                if "chunk_type" in length_df.columns
                else None
            )
            fig = px.histogram(
                length_df,
                x="char_len",
                color="chunk_type" if "chunk_type" in length_df.columns else None,
                barmode="overlay",
                opacity=0.75,
                nbins=40,
                category_orders={"chunk_type": type_order} if type_order else None,
                title="Tamanho dos chunks (caracteres) por tipo",
                labels={"char_len": "Comprimento em caracteres", "chunk_type": "Tipo"},
            )
            fig.update_traces(hovertemplate="Tamanho: ~%{x} caracteres<br>Chunks: %{y:,}<extra></extra>")
            fig.update_layout(
                xaxis_title=f"Caracteres por fragmento (teto de chunking: {CHUNK_MAX_CHARS:,})",
                yaxis_title="Quantidade de chunks",
            )
            render_chart(
                fig,
                height=CHART_HEIGHT,
                caption=f"O eixo mostra até o teto de {CHUNK_MAX_CHARS:,} caracteres usado ao dividir o "
                "texto completo (`gold_articles.CHUNK_MAX_CHARS`); fragmentos excessivamente curtos perdem "
                "contexto semântico.",
            )

    if "doi" in chunks_df.columns:
        chunks_per_article = chunks_df.groupby("doi").size()
        fulltext_dois = (
            chunks_df.loc[chunks_df["chunk_type"] == "fulltext", "doi"].unique()
            if "chunk_type" in chunks_df.columns
            else []
        )
        fulltext_chunks_per_article = chunks_per_article.reindex(fulltext_dois)
        if not fulltext_chunks_per_article.empty:
            st.markdown("**Chunks por artigo (apenas os que têm texto completo)**")
            fig = px.histogram(
                fulltext_chunks_per_article.rename("n_chunks").reset_index(),
                x="n_chunks",
                nbins=20,
                labels={"n_chunks": "Chunks por artigo (abstract + fulltext)"},
            )
            fig.update_traces(marker_color=CATEGORICAL_PALETTE[1])
            render_chart(
                fig,
                height=CHART_HEIGHT,
                caption="Dimensiona o custo de gerar embeddings: artigos com PDFs longos geram mais chunks "
                "de texto completo.",
            )

    metric_row(
        [
            ("🧩 Total de fragmentos (chunks)", f"{len(chunks_df):,}", None),
            (
                "📄 DOIs distintos com fragmentos",
                f"{chunks_df['doi'].nunique():,}" if "doi" in chunks_df else "N/D",
                None,
            ),
        ]
    )


def _render_result_card(row: pd.Series, term_pattern: re.Pattern | None, score: float | None) -> None:
    text = str(row["text"])
    if term_pattern:
        match = term_pattern.search(text)
        idx = match.start() if match else 0
        match_len = (match.end() - match.start()) if match else 0
    else:
        idx, match_len = 0, 0
    start = max(idx - 120, 0)
    end = min(idx + match_len + 120, len(text))
    excerpt = ("…" if start > 0 else "") + text[start:end] + ("…" if end < len(text) else "")
    if term_pattern:
        excerpt = term_pattern.sub(lambda m: f"**{m.group(0)}**", excerpt)
    doi = row.get("doi")
    chunk_type = row.get("chunk_type", "")
    with st.container(border=True):
        header = f"**{chunk_type}**"
        if score is not None:
            header += f" · similaridade {score:.2f}"
        if doi:
            header += f" · [{doi}](https://doi.org/{doi})"
        st.markdown(header)
        st.caption(excerpt)


def _search_demo(chunks_df: pd.DataFrame) -> None:
    st.subheader("🔍 Busca nos chunks")
    has_embeddings = "embedding" in chunks_df.columns and chunks_df["embedding"].notna().any()

    if has_embeddings:
        st.caption(
            "Busca por similaridade vetorial real: a consulta é embedada com o mesmo modelo "
            "(`BAAI/bge-small-en-v1.5` via `fastembed`) usado para os chunks, e os resultados são "
            "ordenados por similaridade de cosseno (`dashboard/search.py`)."
        )
    else:
        st.caption(
            "Isto simula uma recuperação por palavra-chave, **não** uma busca semântica real — a coluna "
            "`embedding` ainda não foi preenchida (ver o indicador acima; rode a etapa `embed` do "
            "pipeline). Serve para mostrar, na prática, o formato dos trechos que um RAG real usaria como "
            "contexto de resposta."
        )
    if not require_columns(chunks_df, ["text"], "Nenhum chunk com texto disponível nesta camada/filtro."):
        return

    query = st.text_input(
        "Buscar (linguagem natural ou termo):" if has_embeddings else "Buscar termo nos chunks:",
        placeholder="ex.: distribution network, hosting capacity, monte carlo...",
    )
    if not query:
        return

    if has_embeddings:
        matches = semantic_search(query, chunks_df, top_k=SEARCH_DEMO_MAX_RESULTS)
        st.caption(f"Top {len(matches):,} chunks mais similares à consulta (de {len(chunks_df):,} disponíveis).")
    else:
        mask = chunks_df["text"].str.contains(query, case=False, na=False, regex=False)
        n_total_matches = int(mask.sum())
        matches = chunks_df.loc[mask].head(SEARCH_DEMO_MAX_RESULTS)
        st.caption(f"{n_total_matches:,} de {len(chunks_df):,} chunks contêm o termo buscado.")

    if matches.empty:
        return

    term_pattern = re.compile(re.escape(query), re.IGNORECASE)
    for _, row in matches.iterrows():
        score = float(row["score"]) if has_embeddings and "score" in row else None
        _render_result_card(row, term_pattern, score)

    if not has_embeddings and n_total_matches > SEARCH_DEMO_MAX_RESULTS:
        st.caption(f"Mostrando {SEARCH_DEMO_MAX_RESULTS} de {n_total_matches:,} resultados.")
