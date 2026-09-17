# Product Requirements Document — lake-literature

See [`../README.md`](../README.md) for a quick orientation, [`SDD.md`](SDD.md) for how this is built and
[`ROADMAP.md`](ROADMAP.md) for what is still worth improving.

## 1. Problem statement

Writing a new article on *distribution system planning* requires knowing, out of **1,831** candidate papers
scattered across publisher databases, which ones are actually worth citing. Doing this by hand from raw IEEE
Xplore and ScienceDirect search exports is unmanageable:

- The two publishers export different formats (CSV+BibTeX vs. BibTeX-only), different field names, different
  DOI formats, and different pagination conventions — see the comparison table in `CLAUDE.md`.
- A paper indexed by both publishers would survive deduplication twice without a reliable join key. (Measured
  on the current corpus, that overlap is currently **zero** — 1,529 articles come from Elsevier only and 302
  from IEEE only — so DOI dedup is insurance the design needs, not the dominant problem today. What the
  corpus *does* contain is 18 near-identical abstracts published under distinct DOIs, which no join key can
  catch; the `semantic` stage surfaces those separately.)
- Counts never line up across the pipeline: 304 IEEE CSV rows and 1,815 BibTeX entries ingest to 1,836 bronze
  records, 1,831 survive DOI deduplication, and only 96 have a PDF (5.2%). The corpus is inherently partial —
  a fact the pipeline has to represent, not paper over.
- The query is ambiguous: "distribution system planning" also matches logistics and supply-chain work.
  Roughly a tenth of what the search returned is off-topic in exactly that way, so relevance screening is
  part of the product, not a post-hoc filter.
- There is no single place to see corpus composition, quality, and coverage at a glance, or to know which
  papers have full text available for deeper analysis.

## 2. Goals

- Ingest both publisher exports verbatim, without loss, so every downstream layer can be rebuilt without
  re-touching the filesystem.
- Produce one deduplicated, quality-flagged article record per paper (keyed on normalized DOI), regardless of
  which publisher(s) it came from.
- Link each deduplicated article to its PDF when one exists in the local corpus, using fuzzy title matching
  since PDF filenames are a lossy encoding of the title.
- Chunk article text (abstracts always, full text when a PDF is linked) into a form suitable for retrieval,
  and embed it locally with no external API dependency.
- Score every article against both readings of the ambiguous query, so relevance screening — a core step of
  a systematic literature review — is a visible, reversible decision with a defensible threshold rather than
  a hidden filter.
- Make corpus composition, data quality, and pipeline health visible and actionable through a dashboard,
  without requiring anyone to query MySQL directly.
- Make every pipeline stage re-runnable on demand (via CLI or Airflow) as new export files are added, without
  duplicating existing records.

## 3. Non-goals

- Automated paper discovery or downloading. The corpus is deliberately hand-assembled from publisher search
  UIs; this project starts from that manual export, not before it.
- Full literature summarization or article drafting. The tool surfaces candidates and evidence; writing the
  citing article stays a human task.
- Multi-tenant or multi-topic support. The pipeline and dashboard are scoped to this one corpus and topic.
- A production-grade retrieval/RAG API. The `embed` stage prepares the data; wiring an actual
  nearest-neighbor query service is future work (see §7).

## 4. Users

- **Primary user**: the researcher/author assembling the corpus and deciding what to cite (also the operator
  running the pipeline and dashboard locally).
- **Secondary/future user**: an LLM agent consuming `gold.lit_chunks` + embeddings to answer "which papers support
  claim X" — this is the direction the `embed` stage exists to enable, even though no agent-facing retrieval
  API exists yet.

## 5. Use cases / user stories

1. As the researcher, I add new export files to `data/ieee/` or `data/elsevier/` and re-run the pipeline so
   the corpus reflects the latest search results, without creating duplicate records for files already
   ingested.
2. As the researcher, I open the dashboard's "Visão Geral" page to see how many unique articles exist, how
   many come from each publisher, and how many overlap.
3. As the researcher, I use "Destaques e Impacto" to find the most-cited or most-relevant papers before
   deciding what to read next.
4. As the researcher, I use "Tópicos e Periódicos" to see which keywords and venues dominate the corpus, to
   check whether my search terms were broad/narrow enough.
5. As the researcher, I use "Qualidade e RAG" to check how many articles are missing abstracts or DOIs, how
   many have a linked PDF, and how much of the corpus has been embedded — and trigger the `embed` stage
   directly from there.
6. As the researcher, I use "Camadas & Pipeline" to see per-layer record counts and trigger a specific stage
   (or the full pipeline) after updating the corpus, and watch its status without leaving the dashboard.
7. As the researcher, I use "Configuração da Busca" to recall exactly which query, filters, and year range
   produced the current corpus, so I can reproduce or extend the search later.
8. As the researcher, I use "Semântica & Relevância" to screen the corpus: the margin histogram shows how
   much of it leans to logistics rather than to the review's topic, the map shows where those articles sit,
   and the table lists the ones below the cut so I can review them before discarding anything.
9. As the researcher, I use "Pesquisadores" to see who publishes most in the corpus and who co-authors with
   whom, knowing the author-identity caveat the page discloses.
10. As the researcher, I use "Tendências & Previsão" to see where publication volume and keyword attention
    are heading, with the current (partial) year labelled as such.
11. (Future) As an LLM agent, I query `gold.lit_chunks` by embedding similarity to retrieve the passages most
    relevant to a citation question and return their source DOIs.

## 6. Functional requirements

### Pipeline (CLI: `uv run lake-literature --stage <raw|bronze|silver|gold|embed|semantic|all>`)

- `raw`: ingest `config.csv`, IEEE CSV rows, all BibTeX entries (both sources), and the PDF inventory,
  verbatim, keyed for idempotent re-ingestion (`lit_source_files` manifest, sha256-based).
- `bronze`: union IEEE and Elsevier records into one typed `bronze.lit_articles` schema; collapse pure
  pagination duplicates within a source; no cross-source dedup yet.
- `silver`: deduplicate bronze articles by normalized DOI into one row per paper (`silver.lit_articles`);
  compute quality flags (`has_abstract`, `has_doi`, `is_duplicate_merge`); fuzzy-match against
  `data/articles/*.pdf` and record `has_pdf`/`pdf_path`/`pdf_match_score`.
- `gold`: produce the curated, RAG-facing `gold.lit_articles` table plus `gold.lit_chunks` (abstract chunks for
  every article, full-text chunks for PDF-linked ones).
- `embed`: fill `gold.lit_chunks.embedding`/`gold.lit_chunks.embed_model` for chunks that don't have one yet;
  safe to re-run after every `gold` run without re-embedding existing chunks.
- `semantic`: from the abstract embeddings, write `gold.lit_semantics` (relevance against the topic anchor
  and against the logistics anchor, discovered theme, 2D map coordinates) and `gold.lit_duplicate_pairs`
  (near-identical abstracts under distinct DOIs). Owns and rewrites only those two tables.
- `all`: run all six stages in order, bootstrapping all four MySQL databases first.

### Dashboard (Streamlit, `uv run streamlit run main.py` or `docker compose up dashboard`)

Ten pages as listed in the README's page table, each reading from the relevant layer's MySQL database. The
"Camadas & Pipeline" and "Qualidade e RAG" pages additionally act as a control surface: they trigger Airflow
DAG runs and poll status, rather than running pipeline code in-process. The sidebar's relevance filter is
global and opt-in: turning it on cuts at the screening margin's zero, and an article with no score is never
removed by it.

### Orchestration (Airflow, `docker compose up -d`)

Seven DAGs (`lake_literature_raw/bronze/silver/gold/embed/semantic` + `lake_literature_all`), manual/API-triggered only
(no cron schedule), each task shelling out to the same CLI entrypoint used for local runs — so pipeline
behavior is identical whether triggered locally or from Airflow.

## 7. Success metrics / acceptance signals

- **No duplicate DOIs** in `silver.lit_articles`/`gold.lit_articles` after a full pipeline run over the
  current corpus.
- **Idempotent re-runs**: running `--stage all` twice in a row on an unchanged `data/` directory does not
  change row counts in any layer.
- **PDF-link precision**: `silver.lit_articles.has_pdf` is true only for articles whose fuzzy-matched PDF is
  actually about that article (spot-checked manually; `pdf_match_score` gives a per-row confidence signal).
- **Embedding coverage**: the "Qualidade e RAG" gauge reaches 100% after running `--stage embed` to
  completion, and stays there on subsequent `gold` reruns until new chunks are added.
- **Dashboard correctness**: page-level counts (e.g. total articles, IEEE vs. Elsevier split) match direct
  queries against the corresponding MySQL database.
- **Screening separates the two readings of the query**: the contrastive margin puts the logistics theme
  below zero and everything else above it. Measured on the current corpus, 165 articles (9%) fall below the
  cut and 145 of them sit in the logistics theme, with at most 12 in any other — and no theme other than
  logistics has a negative mean margin.
- **The map agrees with the themes**: a point's nearest neighbours on the semantic map mostly share its
  theme colour (0.72 over the 15 nearest, up from 0.65 when clustering and projection used different
  spaces). This is a readability signal, not a clustering-quality claim: silhouette on this corpus is flat,
  because the themes genuinely overlap.

## 8. Out of scope for this iteration / open questions

The measured improvement backlog lives in [`ROADMAP.md`](ROADMAP.md) — storage format of the embeddings,
validating the screening threshold against hand labels, pipeline run history, and the rest. This section
keeps only the standing scope decisions.

- **Retrieval**: implemented. The "Qualidade e RAG" dashboard page runs real cosine-similarity search over
  `gold.lit_chunks.embedding` (`dashboard/search.py`) once the `embed` stage has populated it, falling back to keyword
  matching only when no chunk has an embedding yet. This is in-process similarity over a pandas DataFrame, not
  a persisted vector index — acceptable at the corpus's current size (a few thousand chunks), but would need a
  real vector store if the corpus grew by an order of magnitude or more.
- **Corpus refresh automation**: adding new export files to `data/` is still a manual step; there is no
  scheduled or triggered re-scrape. Remains an explicit non-goal, see §3.
- **Testing**: 105 tests under `tests/` (see SDD §8) run against in-memory SQLite rather than real MySQL,
  covering the transforms, the semantic stage's pure functions and the dashboard's analytics/chart/theme
  contracts. They do not cover Airflow DAGs, the Streamlit UI itself, or file parsing against the real
  (gitignored) `data/` corpus — those remain manually verified.
