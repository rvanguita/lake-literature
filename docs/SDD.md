# System Design Document — lake-literature

See [`../README.md`](../README.md) for a quick orientation, [`PRD.md`](PRD.md) for why this exists and
[`ROADMAP.md`](ROADMAP.md) for the measured improvement backlog.
`../CLAUDE.md` remains the canonical reference for source-data quirks (BibTeX parsing gotchas, IEEE/Elsevier
field differences, DOI format normalization) — this document cross-references it rather than repeating it.

## 1. Architecture overview

```
                 ┌─────────────┐       ┌──────────────┐
data/ieee/   ──▶ │             │       │  Streamlit   │──▶ browser (dashboard)
data/elsevier/──▶│  CLI stages │──MySQL│  dashboard   │
data/articles/──▶│ (pipeline.py)│      │              │──▶ Airflow REST API (trigger/poll)
                 └─────────────┘       └──────────────┘
                        ▲                      │
                        └──── BashOperator ────┘
                          (Airflow DAGs)
```

- **Storage**: one MySQL database per medallion layer (`raw`, `bronze`, `silver`, `gold` — named plainly
  after the layer, no prefix), same table names reused across databases where the schema carries forward.
  These databases are **shared with unrelated projects** on the same MySQL server (e.g. `bronze` also holds
  `fastf1_results`, `personal_expenses`); the pipeline only ever creates/touches its own `lit_`-prefixed
  tables within them. SQLAlchemy 2.0 declarative models, one `Base`/module set per layer under
  `src/lake_literature/db/`.
- **Compute**: pure Python/pandas transforms, no Spark or distributed processing — the corpus is 1,831
  articles and 6,235 chunks (measured 2026-09-17), so single-process batch jobs are sufficient. The one
  numerically heavy step is the `semantic` stage's PCA/t-SNE/KMeans over 1,831 × 384 floats, which runs
  in seconds on a laptop CPU.
- **Stages**: `raw → bronze → silver → gold → embed → semantic`, each a `run_<stage>()` in `pipeline.py`
  and each a 1:1 Airflow DAG. `semantic` is the screening/analysis stage: it reads the abstract
  embeddings and writes per-article relevance, theme and map coordinates (see §2.1, §3).
- **Orchestration**: Apache Airflow (`airflow/dags/lake_literature_dags.py`), used purely as a scheduler/UI
  layer over the same CLI the developer runs locally — DAG tasks are `BashOperator` calls to
  `uv run lake-literature --stage <stage>`, so pipeline logic has zero Airflow import dependency and behaves
  identically whether triggered from a terminal or from Airflow.
- **UI**: Streamlit multipage app (`src/lake_literature/dashboard/`), read-only against the four MySQL
  databases except for two "trigger a pipeline stage" actions that go through Airflow's REST API rather than
  running pipeline code in-process (see §5).
- **Deployment**: Docker Compose with two services (`dashboard`, `airflow`), see §6.

## 2. Data model

### 2.1 Layer-by-layer schema

**raw** (database `raw`, `src/lake_literature/db/raw_models.py`) — verbatim ingestion, one table per source
artifact type, nothing normalized or deduplicated:

| Table | Purpose | Key fields |
|---|---|---|
| `lit_source_files` | Manifest of every ingested file, for idempotent re-runs | `path` (unique), `source`, `kind`, `sha256`, `size_bytes`, `mtime` |
| `lit_config` | Parsed provenance from each source's `config.csv` | `source` (unique), `query_string`, `filters`, `year_range`, `search_url`, `raw_text` |
| `lit_ieee_csv_rows` | One row per line of `data/ieee/export*.csv` | `fields` (JSON blob of all CSV columns), `doi`, unique on `(source_file, row_index)` |
| `lit_bib_entries` | One row per BibTeX entry (either source) | `source`, `bib_key`, `entry_type`, `fields` (JSON), `doi`, unique on `(source, bib_key, source_file)` |
| `lit_pdf_files` | Inventory of `data/articles/*.pdf` | `filename` (unique), `path`, `sha256`, `size_bytes` |

**bronze** (database `bronze`, `db/bronze_models.py`) — cross-source consolidation begins here: IEEE
(csv+bib) and Elsevier (bib) unioned into one common, typed `lit_articles` schema. Pure pagination
duplicates within a source are collapsed; there is no cross-source dedup or quality filtering yet.

`lit_articles`: `source`, `source_id`, `record_type`, `doi`, `title`, `authors[]` (JSON), `year`, `venue`,
`volume`, `issue`, `pages`, `issn`, `url`, `abstract`, `keywords[]` (JSON), `citation_count`,
`reference_count`, `raw_bib_id`/`raw_csv_id` (back-references into raw), unique on `(source, source_id)`.

**silver** (database `silver`, `db/silver_models.py`) — cleaned, conformed, deduplicated: one row per
normalized DOI (the reliable cross-source join key — normalize by stripping the `https://doi.org/` prefix and
casefolding, per `CLAUDE.md`), with quality flags and a fuzzy-matched PDF link.

`lit_articles`: `doi` (unique), `sources[]` (JSON — which publisher(s) contributed), `record_type`, `title`,
`authors[]`, `year`, `venue`, `volume`, `issue`, `pages`, `url`, `abstract`, `keywords[]`, `citation_count`,
`reference_count`, quality flags (`has_abstract`, `has_doi`, `is_duplicate_merge`), PDF link
(`has_pdf`, `pdf_path`, `pdf_match_score`), `bronze_ids[]` (JSON provenance list).

**gold** (database `gold`, `db/gold_models.py`) — curated, RAG-ready: `lit_articles` is what a human or agent
scans to decide which paper to cite; `lit_chunks` is the RAG ingestion unit.

`lit_articles`: `doi` (unique), `sources[]`, `title`, `authors[]`, `year`, `venue`, `keywords[]`, `abstract`,
`citation_count`, `reference_count`, `url`, `has_pdf`, `pdf_path`, `silver_id` (back-reference).

`lit_chunks`: `doi` (value-FK to `lit_articles.doi`), `seq`, `chunk_type` (`abstract` | `fulltext`), `text`,
`char_len`, `embedding` (JSON, nullable), `embed_model` (nullable) — the latter two filled by the `embed`
stage; NULL until that stage has run at least once for a given chunk.

`lit_semantics` (one row per article, written by the `semantic` stage): `doi` (unique),
`relevance_score` (cosine to the review's topic anchor), `offtopic_score` (cosine to the logistics
anchor — nullable, since rows written before the contrastive anchor existed don't have it), `theme_id`,
`theme_label`, `map_x`/`map_y` (t-SNE coordinates, comparable only within one run), `embed_model`. The
screening signal is the derived margin `relevance_score - offtopic_score`, whose zero means "closer to
logistics than to the review's topic"; the dashboard cuts there.

`lit_duplicate_pairs`: `doi_a`, `doi_b`, `similarity` — distinct DOIs whose abstracts are near-identical
(cosine ≥ 0.95). Surfaced for review; nothing is merged automatically.

### 2.2 Provenance chain

```
raw.lit_bib_entries / raw.lit_ieee_csv_rows
        │  (raw_bib_id / raw_csv_id)
        ▼
bronze.lit_articles
        │  (bronze_ids[])
        ▼
silver.lit_articles  (one row per normalized DOI)
        │  (silver_id)
        ▼
gold.lit_articles  ──▶  gold.lit_chunks  ──▶  lit_chunks.embedding (embed stage)
                                                      │  (abstract chunks only)
                                                      ▼
                                          gold.lit_semantics + gold.lit_duplicate_pairs
                                                   (semantic stage)
```

Every layer keeps a back-reference to the layer below it, so any gold article or chunk can be traced back to
the exact raw source record(s) it was built from — important because raw ingestion is the only step touching
the filesystem; everything above it is a deterministic, rebuildable transform over MySQL data.

## 3. Ingestion & transform components

### `ingest/` (raw layer, `src/lake_literature/ingest/`)

- `raw_csv.py` — parses `data/ieee/export*.csv` into `lit_ieee_csv_rows`, keeping all columns as an opaque JSON
  blob plus an extracted `doi`.
- `raw_bib.py` — parses all `.bib` files from both `data/ieee/` and `data/elsevier/` using a real BibTeX
  parser (`bibtexparser`), required because IEEE's `.bib` files have no separator between entries (see
  `CLAUDE.md`) — naive line/`@`-splitting silently merges or truncates records.
- `raw_config.py` — parses each source's free-text `config.csv` into structured provenance fields.
- `raw_pdfs.py` — inventories `data/articles/*.pdf`.
- `hashing.py` — sha256 helper used by the `lit_source_files` manifest for idempotency.
- `enrichment.py` — shared helpers used when building bronze/silver records from raw JSON blobs.

### `transform/` (bronze/silver/gold/embed, `src/lake_literature/transform/`)

- `bronze_articles.py` — reads `raw.lit_bib_entries` + `raw.lit_ieee_csv_rows`, normalizes field names/types
  per source (see the IEEE-vs-Elsevier table in `CLAUDE.md`), writes `bronze.lit_articles`.
- `silver_articles.py` — reads `bronze.lit_articles`, normalizes and groups by DOI, merges duplicate bronze
  rows into one silver row per DOI, computes quality flags, fuzzy-matches titles against `raw.lit_pdf_files`
  (via `rapidfuzz`) to set `has_pdf`/`pdf_path`/`pdf_match_score`.
- `gold_articles.py` — reads `silver.lit_articles`, writes the curated `gold.lit_articles` + `gold.lit_chunks`
  (splits abstracts and, where a PDF is linked, full text extracted via `pypdf`, into passages).
- `embeddings.py` — the `embed` stage: loads `fastembed`'s `BAAI/bge-small-en-v1.5` ONNX model, embeds every
  `gold.lit_chunks` row where `embedding IS NULL`, writes the vector back as JSON plus the model name.
  Entirely local, no external API, no GPU requirement.
- `semantics.py` — the `semantic` stage, over the `abstract` chunks only (they exist for every article,
  whereas full text covers 5% of it). Scores each abstract against two anchors, `ANCHOR_TEXT` (the
  review's topic) and `OFF_ANCHOR_TEXT` (the logistics reading of the same ambiguous query), because a
  single anchor's two score distributions overlap and no percentile cut can separate them; clusters the
  corpus into `N_THEMES = 8` and projects it to 2D for the map, both over **one** shared
  `reduced_space()` (explicit L2 normalization, then PCA(50)) so a point's theme colour and its position
  on the map cannot disagree; and records near-duplicate abstract pairs. `k` is human-chosen, not
  optimized — silhouette is flat across k=6..14 on this corpus and density clustering finds only one
  continuum plus the logistics island.

## 4. Idempotency & re-run model

- **Raw layer**: `lit_source_files.sha256` + unique `path` is the re-ingestion guard — a file already recorded
  with a matching hash is skipped rather than re-inserted.
- **Cross-environment path stability**: `config.py`'s `relative_path()`/`absolute_path()` store paths relative
  to `REPO_ROOT` rather than absolute, because the same file has a different absolute path on the host
  (`/home/<user>/.../data/...`) vs. inside the Airflow container (`/opt/airflow/project/data/...`) — storing
  the absolute path would make the same file look like two different files and duplicate every row on a
  cross-environment run.
- **Bronze/silver/gold**: each stage's `build_*` function is a full rebuild-from-source-layer pass keyed on
  natural keys (`(source, source_id)` for bronze, `doi` for silver/gold) with `UniqueConstraint`s enforcing
  no duplicates at the database level.
- **Gold chunks are reconciled, not rebuilt.** The articles table is rebuilt like silver, but a chunk whose
  text is unchanged is left untouched so it keeps its vector (`transform/gold_articles.py`). This used to be
  a plain delete-and-rebuild, which silently discarded every embedding on each `gold` run — and with them the
  basis of `lit_semantics`. So re-running `gold` only invalidates the chunks whose text actually changed;
  `embed` then fills exactly those, and `semantic` has to be re-run after either.
- **Embed**: keyed on `lit_chunks.embedding IS NULL`, so re-running after a `gold` rebuild that added new chunks
  only processes the new ones. A run killed mid-way resumes cleanly, since each batch commits before the next.
- **Semantic**: truncates and rewrites the two tables it owns (`lit_semantics`, `lit_duplicate_pairs`) and
  never touches curated article rows. It also refuses to pretend: when fewer than 100% of the abstract chunks
  are embedded it still runs, but logs a warning naming the coverage, because the signals it writes describe
  only that subset.
- **Bootstrap**: `db/bootstrap.py` creates all four databases/tables if missing, called at the start of every
  `pipeline.run()`/`run_all()` invocation — safe to call repeatedly. Columns added to a table that already
  exists come from `_ADDITIVE_COLUMNS`, keyed by table name; every entry must be nullable and purely
  additive, since this runs unattended on every pipeline start.

## 5. Orchestration

`airflow/dags/lake_literature_dags.py` defines seven DAGs, all `schedule=None` (manual/API trigger only, since
the pipeline is meant to be run on demand from the dashboard, not on a cron):

- `lake_literature_raw`, `_bronze`, `_silver`, `_gold`, `_embed`, `_semantic` — one single-task DAG per stage,
  generated from the module's `STAGES` tuple, each task a `BashOperator` running
  `cd /opt/airflow/project && uv run lake-literature --stage <stage>`.
- `lake_literature_all` — the six tasks chained in stage order, for the dashboard's "run everything" action.

The dashboard never imports pipeline code to execute it directly; instead:

- `dashboard/airflow_client.py` — thin REST client wrapping Airflow's API (trigger a DAG run, poll its state,
  fetch task logs).
- `dashboard/pipeline_control.py` — glue between the "Camadas & Pipeline" / "Qualidade e RAG" pages and
  `airflow_client`, mapping dashboard buttons to DAG IDs and rendering run status.

This split means every pipeline run — whether started from a terminal, the dashboard, or the Airflow UI
directly — gets identical execution, and Airflow's own history/logs/retry UI is the single source of truth
for run status, rather than the dashboard maintaining its own run log.

## 6. Deployment topology

`docker-compose.yml` defines two services:

- **`dashboard`**: built from the repo's `Dockerfile`, exposes `8501`, reads `.env` for MySQL settings, and
  overrides `AIRFLOW_BASE_URL` to `http://airflow:8080` (the compose-network hostname) since `.env`'s own
  value (`http://localhost:8080`) is for the "Streamlit on host, Airflow in compose" case instead.
- **`airflow`**: built from `Dockerfile.airflow`, runs `airflow standalone` (single-container, no separate
  scheduler/webserver/DB), exposes `8080`. `AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_ALL_ADMINS=True` lets the
  dashboard hit Airflow's API without managing a password (a local/single-user setup, not intended for
  multi-user deployment). `UV_PROJECT_ENVIRONMENT=/opt/venv-airflow` keeps the container's uv-managed venv
  separate from the host's `.venv`, because the host venv's activation scripts embed host-specific absolute
  paths that would break inside the container.

Both services bind-mount `src/`, `main.py`, `pyproject.toml`, `uv.lock`, `README.md`, and `data/` from the
host into the `airflow` container (`dashboard` uses its own built image), so DAG runs execute the exact same
code as a local `uv run` without requiring an image rebuild on every code change.

`.env` (git-ignored, see `.env.example`) is the single configuration surface for both services:
`MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `AIRFLOW_BASE_URL`.

## 7. Retrieval

`dashboard/search.py` implements real vector similarity search over `gold.lit_chunks.embedding`, used by the
"Qualidade e RAG" page's search box:

- `_rank_by_similarity(query_vector, chunks_df, top_k)` — pure function, no Streamlit/model dependency: drops
  rows with a null `embedding`, stacks the rest into a matrix, ranks by `sklearn.metrics.pairwise.cosine_similarity`
  against `query_vector`, returns the top-k rows with an added `score` column. Unit tested directly in
  `tests/test_search.py` with hand-built vectors.
- `semantic_search(query, chunks_df, top_k)` — embeds `query` with the same `fastembed` model
  (`transform/embeddings.EMBED_MODEL_NAME`, `BAAI/bge-small-en-v1.5`) used to embed the chunks, then calls
  `_rank_by_similarity`. The model is loaded once per Streamlit process via `st.cache_resource`.

This is in-process cosine similarity over a pandas DataFrame — no vector database or ANN index. That's a
deliberate scope choice for the corpus's current size (a few thousand chunks fit comfortably in memory); a
real vector store (e.g. pgvector, FAISS) would be the next step if the corpus grows by an order of magnitude.
`quality.py::_search_demo` falls back to substring matching over `lit_chunks.text` when no chunk has an embedding
yet (e.g. right after `--stage gold` but before `--stage embed`), so the page never breaks on a fresh corpus.

## 8. Testing

`tests/` (pytest, `uv run pytest`) targets the parts of the pipeline with real logic to get wrong, using
in-memory SQLite sessions — one per medallion layer, mirroring the real one-database-per-layer design (see
`tests/conftest.py`), so nothing here depends on a live MySQL server:

105 tests across 12 files (measured 2026-09-17). Pipeline side:

- `test_bronze_articles.py` — `normalize_doi` (URL-prefix stripping, casefolding), author/keyword splitting,
  numeric coercion.
- `test_silver_articles.py` — `normalize_title`, `_merge_group` (dedup + primary-record selection), and an
  end-to-end `build_silver_articles` run asserting DOI dedup, no-DOI exclusion, and PDF fuzzy-linking.
- `test_gold_articles.py` — `_chunk_text` boundary/overlap behavior, `_build_abstract_text` assembly.
- `test_raw_bib.py` — BibTeX parsing including the IEEE no-separator case, and manifest-driven skipping.
- `test_semantics.py` — relevance/contrastive-margin arithmetic, near-duplicate pairing, theme discovery
  and labelling rules, `reduced_space` normalization and component capping.

Dashboard side (pure functions only, no Streamlit runtime):

- `test_analytics.py` / `test_analytics_authors.py` — aggregation and author-identity folding.
- `test_search.py` — `_rank_by_similarity` ranking, embedding-null exclusion, `top_k` truncation.
- `test_forecasting.py`, `test_qualis.py` — trend fitting and Qualis venue matching.
- `test_charts.py` — the axis-naming contract of the shared figure builders.
- `test_theme.py` — the chart chrome Streamlit would otherwise overwrite (background/font on the figure,
  not only on the template).

Explicitly not covered: real MySQL connectivity, Airflow DAGs, the Streamlit UI itself, and file parsing
against the real (gitignored) `data/` corpus — those stay manually verified. See
[`ROADMAP.md`](ROADMAP.md) §9 for the specific gaps worth closing first.

## 9. Cross-cutting concerns

- **DOI normalization**: strip the `https://doi.org/` prefix, casefold, before any comparison or dedup — see
  `CLAUDE.md` for why (IEEE stores bare DOIs, Elsevier stores full URLs).
- **Source normalization**: the full IEEE-vs-Elsevier field mapping (entry type, page size/pagination,
  keyword separator, venue field differences) lives in `CLAUDE.md` and is implemented in
  `transform/bronze_articles.py` — not duplicated here.
- **BibTeX parsing**: must use a real parser (`bibtexparser`) or deliberate `}@`-splitting; IEEE's `.bib`
  files have no separator between entries, so naive line-oriented parsing silently corrupts records. Code
  tested only against Elsevier's (correctly separated) files will appear to work and then fail on IEEE.
- **PDF matching**: `data/articles/*.pdf` filenames are a lossy, punctuation-stripped encoding of the article
  title, so `silver_articles.py` matches by normalized/fuzzy title comparison (`rapidfuzz`), not exact string
  equality, and records a confidence score (`pdf_match_score`) rather than a binary match.
- **Incomplete corpus is expected**: IEEE's CSV reports more search hits than the downloaded `.bib` entries,
  and PDF count is smaller still — this is a property of how the corpus was assembled, not a pipeline bug to
  "fix" by inventing missing records.
- **Tooling**: `uv run pytest` (in-memory SQLite, no MySQL needed) and `uv run ruff check --fix && uv run
  ruff format` are the two commands; `.claude/settings.json` hooks run them automatically on edit, and
  `pre-commit` adds gitleaks plus a guard that keeps documentation-only commits off `main`.
- **Ambiguity of the search term**: "distribution system planning" also matches logistics/supply-chain work,
  which is why the `semantic` stage scores every abstract against two anchors instead of one. Screening is a
  methodological step of the review, so nothing is auto-deleted: articles below the margin's zero are
  surfaced for a human, and an article with no score is never filtered out.
