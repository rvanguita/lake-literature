# lake-literature

`lake-literature` turns bibliographic exports on **"distribution system planning"** (electric power
distribution networks), collected by hand from IEEE Xplore and Elsevier/ScienceDirect, into a clean,
deduplicated, queryable corpus — with the eventual goal of a RAG-ready dataset that helps decide which papers
to cite when writing a new article on the topic.

For the full product rationale see [`docs/PRD.md`](docs/PRD.md); for the system design see
[`docs/SDD.md`](docs/SDD.md); for the exact quirks of the source data (BibTeX parsing gotchas, DOI format
differences, lossy PDF filename matching) see [`CLAUDE.md`](CLAUDE.md).

## What it does

Two publisher exports are consolidated through a **medallion architecture** — five stages, four of them each
backed by their own MySQL database and built with SQLAlchemy:

```
raw       verbatim ingestion of every source file (CSV rows, BibTeX entries, PDF inventory)
   ↓
bronze    IEEE (CSV + .bib) and Elsevier (.bib) unioned into one common article schema
   ↓
silver    deduplicated by normalized DOI, quality-flagged, linked to PDFs by fuzzy title match
   ↓
gold      curated articles + RAG-ready text chunks (abstract chunks for everything, full-text
          chunks for the subset with a linked PDF)
   ↓
embed     fills gold.chunks.embedding for every chunk, entirely locally via fastembed (ONNX
          runtime, BAAI/bge-small-en-v1.5) — no API key, no GPU required
```

DOI is the only reliable cross-source identifier: stripping the `https://doi.org/` prefix and casefolding it
is what makes deduplication possible, because the two sources otherwise disagree on entry format, field names,
and separators.

A **Streamlit dashboard** (`src/lake_literature/dashboard/`) visualizes the corpus at every stage:

| Page | What it shows |
|---|---|
| Visão Geral | headline corpus counts and composition |
| Produção ao Longo do Tempo | publication trends by year, IEEE vs. Elsevier |
| Tópicos e Periódicos | keyword statistics with an interactive filter/explorer, venue breakdown |
| Destaques e Impacto | citation distribution, most-cited/most-relevant articles |
| Pesquisadores | author-level stats and collaboration view |
| Tendências & Previsão | forecasting of publication/topic trends |
| Camadas & Pipeline | per-layer record counts and pipeline run status, with buttons to trigger a stage |
| Qualidade e RAG | data-quality flags plus RAG-chunk/embedding-readiness gauge, with a button to run the `embed` stage directly |
| Configuração da Busca | the provenance recorded in each source's `config.csv` (query, filters, search URL) |

Pipeline execution is orchestrated by **Apache Airflow**: one DAG per stage
(`lake_literature_raw/bronze/silver/gold/embed`, defined in `airflow/dags/lake_literature_dags.py`) plus a
combined `lake_literature_all` DAG that chains all five. The dashboard's "Camadas & Pipeline" and "Qualidade e
RAG" pages trigger and poll these DAG runs through Airflow's REST API (`dashboard/airflow_client.py`,
`dashboard/pipeline_control.py`) instead of running the pipeline in-process, so every run gets proper history,
logs, and per-task status in the Airflow UI.

## Data sources

| | IEEE Xplore | ScienceDirect / Elsevier |
|---|---|---|
| Format | metadata CSV + paginated `.bib` files | paginated `.bib` files only |
| Full text | ~96 PDFs (from the bulk-download zips) | none |

The corpus (`data/`) is not checked into git — it's raw publisher output assembled manually, treated as
read-only input by the pipeline. See [`CLAUDE.md`](CLAUDE.md) for the parsing gotchas specific to each source
(BibTeX entries with no separator between them, lossy PDF-to-title matching, DOI format differences, etc.).

## Quick start

Requires [uv](https://docs.astral.sh/uv/) (Python 3.13) and access to a MySQL server.

```bash
uv sync                                     # create/refresh .venv from uv.lock
cp .env.example .env                        # fill in MYSQL_HOST/PORT/USER/PASSWORD/DB_PREFIX

uv run lake-literature --stage all         # run the full pipeline (raw -> bronze -> silver -> gold -> embed)
uv run lake-literature --stage embed       # or run just the embedding stage on its own
uv run streamlit run main.py                # dashboard at http://localhost:8501
```

### With Airflow orchestration

```bash
docker compose up -d
```

This starts two services: `airflow` (a single-container `airflow standalone` instance at
`http://localhost:8080`, DAGs pre-loaded from `airflow/dags/`) and `dashboard` (Streamlit at
`http://localhost:8501`, wired to trigger those DAGs). Both read MySQL connection settings from `.env`, which
neither service bakes into its image.

## Git hooks

Depois de clonar, instale os hooks uma vez:

```bash
uv tool install pre-commit   # ou: pip install pre-commit
pre-commit install
```

Isso ativa dois checks em todo `git commit`:
- **gitleaks** — varre o diff staged em busca de segredos (senhas, API keys, tokens, private keys) e bloqueia o commit se encontrar algo.
- **block-docs-on-main** (`scripts/git-hooks/check-docs-branch.sh`) — bloqueia commits que só tocam documentação (`docs/`, `*.md`, `README*`, `CLAUDE.md`) quando feitos direto na `main`, pedindo para criar uma branch (`git checkout -b docs/<assunto>`) antes.

Se você usa o Claude Code neste projeto, o snapshot automático de sessão (hook global `auto-pr.sh`, que commita/pusha com `--no-verify` ao final de cada turno) também roda sua própria varredura de segredo antes de commitar — se encontrar algo, aborta sem commitar nem dar push, para que os dois caminhos (commit manual e automático) fiquem cobertos.

## Project layout

```
src/lake_literature/
  config.py             env/settings (MySQL + Airflow base URL)
  db/                    SQLAlchemy models and engines, one module set per medallion layer
                          (raw_models, bronze_models, silver_models, gold_models, engines, bootstrap)
  ingest/                raw-layer loaders (raw_csv, raw_bib, raw_pdfs, raw_config, enrichment, hashing)
  transform/             bronze/silver/gold builders + embeddings.py (the `embed` stage)
  pipeline.py            CLI entrypoint (`lake-literature --stage ...`)
  dashboard/
    app.py                Streamlit entry point, page registry, navigation
    pages/                one module per page (overview, production, topics, highlights,
                           researchers, forecasting, pipeline_layers, quality, search_config)
    airflow_client.py      thin REST client for triggering/polling Airflow DAG runs
    pipeline_control.py    dashboard-side glue between pages and airflow_client
    analytics.py, charts.py, data.py, loaders.py, forecasting.py, theme.py, components.py
airflow/dags/            DAG definitions (thin wrappers around `uv run lake-literature --stage X`)
docs/                     PRD.md and SDD.md
main.py                  root Streamlit entry point (`import lake_literature.dashboard.app`)
```

## Status

`gold.chunks.embedding` is populated by the `embed` stage (`transform/embeddings.py`, `BAAI/bge-small-en-v1.5`
via `fastembed`) and is idempotent — re-running it only embeds chunks still missing a vector, so it's safe to
call after every `--stage gold` run. The dashboard's "Qualidade e RAG" page has a gauge showing embedding
coverage and a button to trigger the stage directly. That same page's search box now runs real vector
similarity search (`dashboard/search.py`, cosine similarity via scikit-learn over `chunks.embedding`) once
embeddings exist, falling back to keyword matching only before the `embed` stage has run.

A pytest suite lives under `tests/` (`uv run pytest`), covering the pure transform logic and the
bronze→silver dedup/PDF-linking flow against in-memory SQLite. There is no linter/formatter configured yet.
