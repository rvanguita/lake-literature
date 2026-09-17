# lake-literature

Writing a new article on **"distribution system planning"** (electric power distribution networks) means
knowing, out of several hundred candidate papers scattered across publisher databases, which ones are
actually worth citing. `lake-literature` turns hand-assembled bibliographic exports from IEEE Xplore and
Elsevier/ScienceDirect into a clean, deduplicated, RAG-ready corpus that answers that question — without
anyone having to query MySQL directly.

For the full product rationale see [`docs/PRD.md`](docs/PRD.md); for the system design see
[`docs/SDD.md`](docs/SDD.md); for the exact quirks of the source data (BibTeX parsing gotchas, DOI format
differences, lossy PDF filename matching) see [`CLAUDE.md`](CLAUDE.md).

![Pipeline architecture: IEEE Xplore and Elsevier/ScienceDirect flowing through the raw, bronze, silver, gold and embed layers, orchestrated by Apache Airflow, feeding the Streamlit dashboard](docs/images/architecture.svg)

## Why this exists

Doing this by hand from raw publisher exports is unmanageable:

- The two publishers export different formats (CSV+BibTeX vs. BibTeX-only), different field names, different
  DOI formats, and different pagination conventions.
- A paper indexed by both publishers would survive deduplication twice without a reliable join key — DOI,
  normalized, is that key. (On the current corpus that overlap happens to be zero: 1,529 articles from
  Elsevier, 302 from IEEE, none in both. The duplication that *does* exist is 18 near-identical abstracts
  under distinct DOIs, which the `semantic` stage surfaces instead.)
- Counts never line up: 304 IEEE CSV rows and 1,815 BibTeX entries ingest to 1,836 bronze records, 1,831
  survive DOI deduplication, and 96 have a PDF. The corpus is inherently partial — a fact the pipeline has
  to represent, not paper over.
- The query itself is ambiguous: "distribution system planning" also matches logistics and supply-chain
  work, so screening the corpus for relevance is part of the job, not an afterthought.
- There was no single place to see corpus composition, quality, and coverage at a glance, or to know which
  papers have full text available for deeper analysis.

## Data sources

| | IEEE Xplore | ScienceDirect / Elsevier |
|---|---|---|
| Format | metadata CSV + paginated `.bib` files | paginated `.bib` files only |
| Full text | ~96 PDFs (from the bulk-download zips) | none |

The corpus (`data/`) is not checked into git — it's raw publisher output assembled manually, treated as
read-only input by the pipeline. See [`CLAUDE.md`](CLAUDE.md) for the parsing gotchas specific to each source
(BibTeX entries with no separator between them, lossy PDF-to-title matching, DOI format differences, etc.).

## Dashboard

A **Streamlit dashboard** (`src/lake_literature/dashboard/`) visualizes the corpus at every pipeline stage,
across ten pages:

| Page | What it shows |
|---|---|
| Overview | headline corpus counts, source distribution, publication-year spread, bibliometric correlations, editorial concentration |
| Output Over Time | volume by year and by CAPES/Qualis tier, cumulative growth by periódico, IEEE vs. Elsevier comparison, author-team-size trends |
| Topics & Venues | periódico ranking, CAPES/Qualis classification, keyword statistics with an interactive filter/explorer, keyword-share evolution |
| Highlights & Impact | reference-count distribution, citation impact, collaboration, author/venue rankings |
| Researchers | canonicalized author ranking, production over time, co-authorship network, per-topic research-line leaders, concentration/Gini analysis |
| Semantics & Relevance | relevance screening against both readings of the query, the semantic map of the corpus, automatically discovered themes, near-duplicate abstracts |
| Trends & Forecast | regression-based forecasts of publication volume (per source) and of keyword-level growth |
| Layers & Pipeline | funnel + per-layer record counts and drift checks, with buttons to trigger a pipeline stage |
| Quality & RAG | metadata richness, full-text coverage, chunk/embedding readiness, with a button to run the `embed` stage directly |
| Search Configuration | the provenance recorded in each source's `config.csv` (query, filters, search URL) |

Every page's charts are organized into tabs — several with a further layer of sub-tabs — so each page stays
one screen instead of an endless scroll. Page labels in the running app are in Portuguese; the table above
uses their English meaning.

Pipeline execution is orchestrated by **Apache Airflow**: one DAG per stage
(`lake_literature_raw/bronze/silver/gold/embed/semantic`, defined in `airflow/dags/lake_literature_dags.py`)
plus a combined `lake_literature_all` DAG that chains all six. The "Camadas & Pipeline" and "Qualidade e RAG"
dashboard pages trigger and poll these DAG runs through Airflow's REST API
(`dashboard/airflow_client.py`, `dashboard/pipeline_control.py`) instead of running the pipeline in-process,
so every run gets proper history, logs, and per-task status in the Airflow UI.

## Storage

The two publisher exports are consolidated through a **medallion architecture** — raw → bronze → silver →
gold → embed — with SQLAlchemy models. Each of the four medallion layers (`raw`, `bronze`, `silver`, `gold`)
lives in its own MySQL database, named plainly after the layer. **Those databases are shared with unrelated
projects on the same MySQL server** — the pipeline only ever creates or touches its own `lit_`-prefixed
tables within them, never anything else it finds there.

DOI is the only reliable cross-source identifier: stripping the `https://doi.org/` prefix and casefolding it
is what makes deduplication possible, because the two sources otherwise disagree on entry format, field
names, and separators.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) (Python 3.13) and access to a MySQL server.

```bash
uv sync                                     # create/refresh .venv from uv.lock
cp .env.example .env                        # fill in MYSQL_HOST/PORT/USER/PASSWORD

uv run lake-literature --stage all         # full pipeline (raw -> bronze -> silver -> gold -> embed -> semantic)
uv run lake-literature --stage embed       # or run just one stage on its own
uv run lake-literature --stage semantic    # relevance screening, themes and the semantic map
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

## Testing & linting

```bash
uv run pytest        # tests/ — pure transform logic + bronze/silver/gold builders against in-memory SQLite
uv run ruff check     # lint (E, F, I, UP, B rulesets; see pyproject.toml)
```

The suite (`tests/`) covers DOI normalization, bronze/silver dedup and merge logic, PDF fuzzy-matching, gold
chunking, CAPES/Qualis venue matching, author-analytics helpers, and vector-similarity ranking — all against
in-memory SQLite, so none of it needs a live MySQL server. It does not cover Airflow DAGs, the Streamlit UI,
or file parsing against the real (gitignored) `data/` corpus — those stay manually verified.

## Git hooks

After cloning, install the hooks once:

```bash
uv tool install pre-commit   # or: pip install pre-commit
pre-commit install
```

This enables two checks on every `git commit`:
- **gitleaks** — scans the staged diff for secrets (passwords, API keys, tokens, private keys) and blocks the
  commit if it finds anything.
- **block-docs-on-main** (`scripts/git-hooks/check-docs-branch.sh`) — blocks commits that touch only
  documentation (`docs/`, `*.md`, `README*`, `CLAUDE.md`) when made directly on `main`, asking you to create a
  branch (`git checkout -b docs/<topic>`) first.

If you use Claude Code on this project, the automatic session snapshot (the global `auto-pr.sh` hook, which
commits/pushes with `--no-verify` at the end of every turn) also runs its own secret scan before committing —
if it finds anything, it aborts without committing or pushing, so both paths (manual and automatic commits)
are covered.

`main` is a protected branch on GitHub: force-pushes and branch deletion are disabled.

## Project layout

```
src/lake_literature/
  config.py             env/settings (MySQL + Airflow base URL)
  db/                    SQLAlchemy models and engines, one module set per medallion layer
                          (raw_models, bronze_models, silver_models, gold_models, engines, bootstrap)
  ingest/                raw-layer loaders (raw_csv, raw_bib, raw_pdfs, raw_config, enrichment, hashing)
  transform/             bronze/silver/gold builders + embeddings.py (`embed`) + semantics.py (`semantic`)
  pipeline.py            CLI entrypoint (`lake-literature --stage ...`)
  dashboard/
    app.py                Streamlit entry point, page registry, navigation
    pages/                one module per page (overview, production, topics, highlights,
                           researchers, semantics, forecasting, pipeline_layers, quality,
                           search_config)
    airflow_client.py      thin REST client for triggering/polling Airflow DAG runs
    pipeline_control.py    dashboard-side glue between pages and airflow_client
    analytics.py, charts.py, data.py, loaders.py, forecasting.py, theme.py, components.py
airflow/dags/            DAG definitions (thin wrappers around `uv run lake-literature --stage X`)
docs/                     PRD.md, SDD.md, ROADMAP.md, images/architecture.svg
scripts/git-hooks/        local pre-commit hook scripts
tests/                    pytest suite (in-memory SQLite, no MySQL needed)
main.py                  root Streamlit entry point (`import lake_literature.dashboard.app`)
```

## Status

- **No duplicate DOIs** in `silver`/`gold`'s `lit_articles` after a full pipeline run over the current corpus.
- **Idempotent re-runs**: running `--stage all` twice in a row on unchanged `data/` doesn't change row counts.
- **Embedding coverage**: `gold.lit_chunks.embedding` is filled by the `embed` stage
  (`transform/embeddings.py`, `BAAI/bge-small-en-v1.5` via `fastembed`, entirely local) and is idempotent —
  re-running only embeds chunks still missing a vector. The "Qualidade e RAG" dashboard page has a gauge for
  this and a button to trigger the stage directly.
- **Retrieval**: implemented as in-process cosine similarity over `gold.lit_chunks.embedding`
  (`dashboard/search.py`, scikit-learn) — not a persisted vector index. Acceptable at the corpus's current
  size (a few thousand chunks); a real vector store (pgvector, FAISS) would be the next step at an order of
  magnitude more data. Falls back to keyword matching before the `embed` stage has run.
- **Relevance screening**: every article is scored against the review's topic *and* against the logistics
  reading of the same ambiguous query; the margin between them is the screening signal, and its zero is the
  cut. On the current corpus 165 of 1,831 articles (9%) fall below it, 145 of them inside the logistics
  theme. Nothing is deleted automatically — the sidebar filter is opt-in and never removes an unscored
  article.
- **Corpus refresh remains manual**: adding new export files to `data/` and re-running the pipeline is a
  deliberate, unautomated step — there is no scheduled or triggered re-scrape (see PRD §3 for the full list
  of non-goals).
- **What's next**: the measured improvement backlog lives in [`docs/ROADMAP.md`](docs/ROADMAP.md).
