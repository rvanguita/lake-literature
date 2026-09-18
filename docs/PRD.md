# Product Requirements Document — lake-research-map

See [`../README.md`](../README.md) for a quick orientation, [`SDD.md`](SDD.md) for how this is built, and
[`ROADMAP.md`](ROADMAP.md) for the strategic research and improvement backlog.

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
  and embed it locally with zero-copy binary storage (`LargeBinary` float32) with no external API dependency.
- Score every article against both readings of the ambiguous query, so relevance screening — a core step of
  a systematic literature review — is a visible, reversible decision with a defensible threshold rather than
  a hidden filter.
- Support active learning and stratified sampling for formal screening calibration, ensuring high sensitivity
  ($\ge 98\%$ recall) in Systematic Literature Reviews.
- Make corpus composition, data quality, and pipeline health visible and actionable through a dashboard,
  without requiring anyone to query MySQL directly.
- Provide advanced cienciometric, statistical, and machine learning capabilities: heavy-tail citation modeling,
  age-normalized citation cohorts, non-parametric Mann-Kendall trend tests, Louvain community detection,
  Small-World network efficiency, Bradford's and Zipf's bibliometric laws, GLM econometric determinants,
  dynamic c-TF-IDF topic modeling, Bass diffusion, and Isolation Forest anomaly detection.
- Make every pipeline stage re-runnable on demand (via CLI or Airflow) as new export files are added, recording
  every execution run in `lit_pipeline_runs`.

## 3. Non-goals

- Automated paper discovery or web-scraping against paywalled interfaces. The corpus is hand-assembled from
  publisher search UIs; this project starts from that manual export, not before it.
- Full literature summarization or automatic paper generation. The tool surfaces candidates, empirical metrics,
  and evidence; writing the citing article stays a human task.
- Multi-tenant or multi-topic support. The pipeline and dashboard are scoped to this one corpus and topic.
- Writing to production MySQL databases from dashboard pages. All pages are strictly read-only against the
  database layer; user interventions are captured as exportable datasets or through explicit CLI stages.

## 4. Users

- **Primary user**: the researcher/author assembling the corpus, screening papers, and deciding what to cite
  (also the operator running the pipeline and dashboard locally).
- **Secondary/future user**: an LLM agent consuming `gold.lit_chunks` + binary embeddings to answer "which papers
  support claim X" via dense passage retrieval.

## 5. Use cases / user stories

1. As the researcher, I add new export files to `data/ieee/` or `data/elsevier/` and re-run the pipeline so
   the corpus reflects the latest search results, without creating duplicate records for files already
   ingested.
2. As the researcher, I open the dashboard's "Visão Geral" page to see how many unique articles exist, how
   many come from each publisher, and how many overlap.
3. As the researcher, I use "Destaques e Impacto" to inspect the most-cited papers, evaluate heavy-tail
   distributions (Power-Law vs. Log-Normal), identify age-normalized high-velocity papers, and examine
   econometric determinants of citations via Poisson GLMs.
4. As the researcher, I use "Tópicos e Periódicos" to see keyword vocabularies, verify Bradford's scattering
   zones, test Zipf's Law rank-frequency regression, track dynamic c-TF-IDF topic vocabularies across historical
   epochs, and test topic trends via non-parametric Mann-Kendall tests.
5. As the researcher, I use "Qualidade e RAG" to check how many articles are missing abstracts or DOIs, how
   many have a linked PDF, audit bibliometric anomalies via Isolation Forest, and trigger semantic search over
   binary-stored vectors with accelerated indexing.
6. As the researcher, I use "Camadas & Pipeline" to inspect the execution history of every pipeline run
   (`lit_pipeline_runs`), check dropped bronze records (`lit_rejected`), and trigger stage DAGs.
7. As the researcher, I use "Configuração da Busca" to recall exactly which query, filters, and year range
   produced the current corpus, so I can reproduce or extend the search later.
8. As the researcher, I use "Semântica & Relevância" to screen the corpus: the contrastive margin separates
   distribution planning from logistics, the multi-perspective map toggles dynamically between t-SNE, PCA 2D,
   and UMAP, semantic novelty scores reveal interdisciplinary boundary-spanning papers, and Active Learning
   prioritizes borderline articles ($|\Delta| \approx 0$).
9. As the researcher, I use "Pesquisadores" to see prolific authors, explore co-authorship networks clustered
   by Louvain communities, analyze Small-World network efficiency ($\sigma$), inspect PageRank and Closeness
   centralities, and correlate team cognitive distance with citation impact.
10. As the researcher, I use "Tendências & Previsão" to project volume via quantile regression (P10/P50/P90)
    and estimate technology lifecycles and peak years via Bass Diffusion modeling.
11. As the researcher, I generate a stratified screening sample (~100 articles) across margin strata to calibrate
    the SLR decision threshold defensibly before manuscript submission.
12. As an LLM agent, I query `gold.lit_chunks` by binary embedding similarity to retrieve the passages most
    relevant to a citation query and return their source DOIs.
13. As the researcher, I use "Cienciometria Estratégica" (`pages/strategic.py`) to position research topics
    on Callon's Strategic Diagram (density vs. centrality), explore keyword co-occurrence topologies, evaluate
    thematic centroid distances in $\mathbb{R}^{384}$, analyze 5-axis maturity radar profiles, track Shannon
    thematic entropy, and examine international research collaboration networks.
14. As the researcher, I use "Evidências Metodológicas" (`pages/synthesis.py`) to synthesize optimization paradigms
    (MILP, SOCP, MINLP, AI), map multi-objective trade-offs, cross-reference uncertainty models with physical
    DER resources, compare multi-stage vs. static planning horizons, benchmark against standard IEEE test feeders,
    identify algebraic solvers and simulators, evaluate career velocity ($m$-quotient, $h/g/e$-indices), and measure
    literature half-life and text stylometrics.
15. As the researcher, I use "Frentes Tecnológicas & Disrupção" (`pages/frontiers.py`) to assess theoretical youth
    via Price's Index, detect delayed-recognition Sleeping Beauties ($B$ coefficient), measure scientific disruption
    via the $CD$ index, evaluate the Open Access Citation Advantage (OACA), and track technological burst timelines
    via Kleinberg's algorithm.

## 6. Functional requirements

### Pipeline (CLI: `uv run lake-research-map --stage <raw|bronze|silver|gold|embed|semantic|all>`)

- `raw`: ingest `config.csv`, IEEE CSV rows, all BibTeX entries (both sources), and the PDF inventory,
  verbatim, keyed for idempotent re-ingestion (`lit_source_files` manifest, sha256-based).
- `bronze`: union IEEE and Elsevier records into one typed `bronze.lit_articles` schema; collapse pure
  pagination duplicates within a source; apply automated OpenAlex citation enrichment (`ingest/openalex.py`)
  cached in `data/enrichment_cache.json`.
- `silver`: deduplicate bronze articles by normalized DOI into one row per paper (`silver.lit_articles`);
  compute quality flags (`has_abstract`, `has_doi`, `is_duplicate_merge`); explicitly flag non-article
  records (`is_non_article`); persist dropped records lacking a valid DOI into `silver.lit_rejected` for
  SLR auditability; fuzzy-match against `data/articles/*.pdf` and record `has_pdf`/`pdf_path`/`pdf_match_score`.
- `gold`: produce the curated, RAG-facing `gold.lit_articles` table plus `gold.lit_chunks` (abstract chunks for
  every article, full-text chunks for PDF-linked ones), carrying `is_non_article`. Record stage execution
  metadata into `gold.lit_pipeline_runs`.
- `embed`: fill `gold.lit_chunks.embedding_bin` (binary float32) and `gold.lit_chunks.embedding` (JSON fallback)
  locally via `fastembed` (`BAAI/bge-small-en-v1.5`); safe to re-run after every `gold` run without re-embedding
  unchanged chunks.
- `semantic`: from abstract embeddings, write `gold.lit_semantics` (contrastive relevance scores, discovered
  theme, 2D map coordinates) and `gold.lit_duplicate_pairs` (near-identical abstracts under distinct DOIs).
  Provides multi-projection support (t-SNE, UMAP, PCA 2D), 2D KDE density contours, and thematic centroid
  drift tracking across chronological epochs.
- `all`: run all six stages in order, bootstrapping all four MySQL databases first and recording run metrics.

### Dashboard (Streamlit, `uv run streamlit run main.py` or `docker compose up dashboard`)

Thirteen modular pages reading from the medallion MySQL layers:
- Reads binary embeddings first via `np.frombuffer` for fast vector search, clustering, and multi-projections.
- Discloses coverage and separates abstract vs. fulltext chunks in RAG metrics.
- Excludes title-only records from screening margin percentiles and highlights them with warning badges.
- Displays full pipeline run history and rejected records audit tables.
- Strict **chart deduplication and tab hygiene**: every tab across specialized pages features unique, non-redundant visual perspectives, reserving cross-cutting summaries exclusively to the "Visão Geral" overview page.
- Native **dark/light theme responsiveness**: transparent polar/radar backgrounds (`paper_bgcolor='rgba(0,0,0,0)'`, `polar_bgcolor='rgba(0,0,0,0)'`) and modern `width="stretch"` layout throughout.
- Renders advanced statistical and ML panels: Methodological synthesis across 8 analytical dimensions
  (mathematical complexity spectrum MILP/SOCP/MINLP/AI, multi-objective co-optimization taxonomy of costs/losses/reliability/emissions/resilience,
  uncertainty paradigms cross-referenced with physical DER resources, multi-stage vs. static planning time horizons,
  IEEE benchmark test feeders, computational modeling environments and exact solvers GAMS/CPLEX/Gurobi/MATLAB/OpenDSS,
  scientific career velocity m-quotient alongside Hirsch h-index, Egghe's g-index, and Zhang's e-index, and citation longevity
  with text stylometrics), Callon's Strategic Diagram (1991), keyword co-occurrence graphs, thematic centroid similarity heatmaps,
  multi-criteria maturity radars, Spearman cross-correlations, Shannon thematic entropy, international collaboration networks,
  Price's Index (1965) of theoretical recency, Sleeping Beauties delayed-recognition detection (Ke et al. 2015), Wu et al. (Nature 2019)
  CD disruption index, Open Access citation advantage (OACA), Kleinberg (2002) technological burst detection, heavy-tail MLE fits,
  age-normalized percentiles, Mann-Kendall tests, Bradford and Zipf laws, Louvain communities, Small-World coefficients,
  dynamic c-TF-IDF topics, Isolation Forest audits, Bass diffusion NLS models, structural break / changepoints tests,
  conceptual atypicality (Uzzi et al. 2013), and Hybrid Retrieval (BM25 Okapi + Dense BGE-Small with Reciprocal Rank Fusion).

### Orchestration (Airflow, `docker compose up -d`)

Seven DAGs (`lake_research_map_raw/bronze/silver/gold/embed/semantic` + `lake_research_map_all`), manual/API-triggered only
(no cron schedule), each task shelling out to the same CLI entrypoint used for local runs — so pipeline
behavior is identical whether triggered locally or from Airflow. Verified with automated import tests.

## 7. Success metrics / acceptance signals

- **Zero duplicate DOIs** in `silver.lit_articles`/`gold.lit_articles` after a full pipeline run over the corpus.
- **Idempotent re-runs**: running `--stage all` twice in a row on an unchanged `data/` directory does not
  alter record counts in any layer.
- **Zero chart duplication**: each tab within specialized analytical pages provides a unique analytical angle without redundant charts across tabs.
- **Binary embedding efficiency**: `gold.lit_chunks.embedding_bin` reduces storage footprint from ~50 MB to ~9 MB
  and eliminates per-read JSON parsing overhead, accelerating in-memory vector search by 5–10x.
- **Hybrid Retrieval Performance**: Reciprocal Rank Fusion combines exact keyword match (BM25) with dense semantic
  proximities, achieving zero-compromise retrieval for both technical codes and conceptual queries.
- **Defensible screening threshold**: stratified sampling and PR curve calibration guarantee a sensitivity
  target $\ge 98\%$ on the SLR screening boundary.
- **Auditability of exclusions**: every dropped record is persisted with timestamp and reason in `silver.lit_rejected`.
- **Pipeline observability**: 100% of pipeline executions are logged in `gold.lit_pipeline_runs` with wall-clock
  durations and per-stage stats dictionaries.
- **Dashboard agreement**: page-level aggregations match direct queries against MySQL; t-SNE nearest neighbors
  share theme color with $>70\%$ agreement.

## 8. Testing & Validation

186 automated unit and integration tests across 22 test files (executed via `uv run pytest` against in-memory
SQLite sessions, independent of live MySQL servers):
- Ingestion, parsing, and OpenAlex enrichment clients.
- Medallion transforms, DOI normalization, deduplication, and additive schema bootstrap.
- Reconciled chunk management, vector dual-write, binary-first loading, and accelerated vector indexing.
- Semantic contrastive scoring, theme discovery, UMAP/PCA/t-SNE projections, semantic novelty, and SLR calibration.
- Dashboard analytical functions, Callon's strategic diagram, keyword co-occurrence networks, thematic centroid similarity, maturity radars, multivariate Spearman correlation matrices, Shannon thematic entropy, and geographic collaboration.
- Optimization taxonomy and complexity spectrum, objective function co-optimization, uncertainty paradigms cross-matrices, planning horizons, solver tooling, IEEE benchmark test feeders, author career velocity (m-quotient) and impact indices (h/g/e/i10), text stylometrics, and citation longevity.
- Price's index theoretical recency, Sleeping Beauties delayed recognition ($B$ coefficient), Wu et al. CD disruption index, Open Access citation advantage, and Kleinberg technological bursts.
- Structural breaks and changepoints (Chow test), Uzzi et al. conceptual atypicality analysis, and venue semantic clustering.
- Heavy-tail MLE fits, Mann-Kendall trend tests, Zipf's law, and network graph algorithms (Louvain, PageRank, Closeness, Small-World).
- Machine learning models: dynamic topic c-TF-IDF, Isolation Forest bibliometric anomaly detection, quantile forecasts, Bass diffusion NLS, and Hybrid BM25/RRF search.
- Airflow DAG module import and structural validation.
