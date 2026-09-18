# System Design Document — lake-literature

See [`../README.md`](../README.md) for a quick orientation, [`PRD.md`](PRD.md) for domain motivation, and
[`ROADMAP.md`](ROADMAP.md) for the strategic research and improvement backlog.
`../CLAUDE.md` remains the canonical reference for source-data quirks (BibTeX parsing gotchas, IEEE/Elsevier
field differences, DOI format normalization) — this document cross-references it rather than repeating it.

## 1. Architecture overview

```
                 ┌──────────────┐       ┌──────────────┐
data/ieee/   ──▶ │              │       │  Streamlit   │──▶ browser (dashboard)
data/elsevier/──▶│  CLI stages  │──MySQL│  dashboard   │
data/articles/──▶│ (pipeline.py)│       │              │──▶ Airflow REST API (trigger/poll)
                 └──────────────┘       └──────────────┘
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
  articles and 6,235 chunks (measured 2026-09-17), so single-process batch jobs are sufficient. Embeddings
  use local ONNX-accelerated inference (`fastembed`), and vector representations are serialized as raw
  float32 bytes (`LargeBinary`), eliminating JSON parsing overhead.
- **Stages**: `raw → bronze → silver → gold → embed → semantic`, each a `run_<stage>()` in `pipeline.py`
  wrapped by `_record_run()` to persist execution metadata into `gold.lit_pipeline_runs`. Each stage maps
  1:1 to an Airflow DAG.
- **Orchestration**: Apache Airflow (`airflow/dags/lake_literature_dags.py`), used purely as a scheduler/UI
  layer over the same CLI the developer runs locally — DAG tasks are `BashOperator` calls to
  `uv run lake-literature --stage <stage>`, so pipeline logic has zero Airflow import dependency and behaves
  identically whether triggered from a terminal or from Airflow. Verified in CI via `tests/test_dag_import.py`.
- **UI**: Streamlit multipage app (`src/lake_literature/dashboard/`), read-only against the four MySQL
  databases except for pipeline trigger actions routed through Airflow's REST API.
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
Automatic enrichment from OpenAlex API is applied to backfill citation counts and reference counts.

`lit_articles`: `source`, `source_id`, `record_type`, `doi`, `title`, `authors[]` (JSON), `year`, `venue`,
`volume`, `issue`, `pages`, `issn`, `url`, `abstract`, `keywords[]` (JSON), `citation_count`,
`reference_count`, `raw_bib_id`/`raw_csv_id` (back-references into raw), unique on `(source, source_id)`.

**silver** (database `silver`, `db/silver_models.py`) — cleaned, conformed, deduplicated: one row per
normalized DOI (the reliable cross-source join key — normalize by stripping the `https://doi.org/` prefix and
casefolding, per `CLAUDE.md`), with quality flags, explicit non-article tagging, and a fuzzy-matched PDF link.

`lit_articles`: `doi` (unique), `sources[]` (JSON — which publisher(s) contributed), `record_type`, `title`,
`authors[]`, `year`, `venue`, `volume`, `issue`, `pages`, `url`, `abstract`, `keywords[]`, `citation_count`,
`reference_count`, quality flags (`has_abstract`, `has_doi`, `is_duplicate_merge`), `is_non_article` (boolean,
flagging front matter, prefaces, and book chapters), PDF link (`has_pdf`, `pdf_path`, `pdf_match_score`),
`bronze_ids[]` (JSON provenance list).

`lit_rejected`: audit log of dropped bronze records lacking a valid DOI: `bronze_id`, `source`, `source_id`,
`title`, `reason` (e.g. `'no_doi'`), `rejected_at`.

**gold** (database `gold`, `db/gold_models.py`) — curated, RAG-ready: `lit_articles` is what a human or agent
scans to decide which paper to cite; `lit_chunks` is the RAG ingestion unit.

`lit_articles`: `doi` (unique), `sources[]`, `title`, `authors[]`, `year`, `venue`, `keywords[]`, `abstract`,
`citation_count`, `reference_count`, `url`, `has_pdf`, `pdf_path`, `is_non_article`, `silver_id` (back-reference).

`lit_chunks`: `doi` (value-FK to `lit_articles.doi`), `seq`, `chunk_type` (`abstract` | `fulltext`), `text`,
`char_len`, `embedding` (JSON, legacy compatibility), `embedding_bin` (LargeBinary, raw float32 bytes for
fast vector search), `embed_model` (String(128)).

`lit_semantics` (one row per article, written by the `semantic` stage): `doi` (unique),
`relevance_score` (cosine to the review's topic anchor), `offtopic_score` (cosine to the logistics
anchor), `theme_id`, `theme_label`, `map_x`/`map_y` (2D coordinates), `embed_model`. The screening signal
is the derived contrastive margin `relevance_score - offtopic_score`, whose zero marks the boundary between
distribution planning and logistics.

`lit_duplicate_pairs`: `doi_a`, `doi_b`, `similarity` — distinct DOIs whose abstracts are near-identical
(cosine ≥ 0.95).

`lit_pipeline_runs`: execution history table written by `pipeline.py`: `id`, `stage`, `started_at`,
`finished_at`, `duration_seconds`, `stats` (JSON), `status` (`'success'` | `'error'`), `error_message`.

### 2.2 Provenance chain

```
raw.lit_bib_entries / raw.lit_ieee_csv_rows
        │  (raw_bib_id / raw_csv_id)
        ▼
bronze.lit_articles ──▶ data/enrichment_cache.json (OpenAlex enrichment)
        │  (bronze_ids[])
        ├──▶ silver.lit_rejected (audit of dropped rows with no DOI)
        ▼
silver.lit_articles  (one row per normalized DOI, carries is_non_article)
        │  (silver_id)
        ▼
gold.lit_articles  ──▶  gold.lit_chunks  ──▶  lit_chunks.embedding_bin (embed stage)
        ▲                      │                 (LargeBinary float32)
        │                      ▼
lit_pipeline_runs     gold.lit_semantics + gold.lit_duplicate_pairs
(run tracking)                 (semantic stage: UMAP/PCA/t-SNE & drift)
```

## 3. Ingestion & transform components

### `ingest/` (raw layer, `src/lake_literature/ingest/`)

- `raw_csv.py` — parses `data/ieee/export*.csv` into `lit_ieee_csv_rows`.
- `raw_bib.py` — parses all `.bib` files from both sources using `bibtexparser`, handling IEEE's no-separator
  entries cleanly.
- `raw_config.py` — parses search provenance from `config.csv`.
- `raw_pdfs.py` — inventories `data/articles/*.pdf`.
- `hashing.py` — sha256 helper for `lit_source_files` manifest idempotency.
- `enrichment.py` — loads `data/enrichment_cache.json` for bronze upsert backfill.
- `openalex.py` — automated client fetching citation and reference counts from OpenAlex REST API.

### `transform/` (bronze/silver/gold/embed/semantic, `src/lake_literature/transform/`)

- `bronze_articles.py` — normalizes raw records into `bronze.lit_articles`.
- `silver_articles.py` — dedup by DOI, sets quality flags, identifies non-articles (`_is_non_article`),
  persists dropped rows into `silver.lit_rejected`, and fuzzy-matches PDFs via `rapidfuzz`.
- `gold_articles.py` — writes curated `gold.lit_articles` and reconciles `gold.lit_chunks` (invalidation-aware,
  nulling `embedding` and `embedding_bin` only when chunk text changed).
- `embeddings.py` — embeds missing chunks via `fastembed` (`BAAI/bge-small-en-v1.5`), writing both `embedding`
  (JSON) and `embedding_bin` (`np.ndarray.tobytes()`).
- `semantics.py` — reads binary embeddings first; calculates contrastive relevance margins; discovers themes;
  projects coordinates via t-SNE, UMAP (`project_umap`), or PCA (`project_pca_2d`); computes thematic
  centroids (`compute_thematic_centroids`) and chronological drift trajectories (`compute_temporal_drift`);
  and scores semantic novelty (`compute_semantic_novelty`). Accepts injected anchor vectors for tests.
- `screening_calibration.py` — generates stratified evaluation samples (`generate_stratified_screening_sample`)
  across 4 margin strata and evaluates threshold sensitivity/specificity for SLR auditability.

## 4. Idempotency & re-run model

- **Raw layer**: `lit_source_files.sha256` + unique `path` skips unchanged files.
- **Bronze/silver/gold**: `build_*` functions use natural keys (`(source, source_id)` for bronze, `doi` for
  silver/gold) with `UniqueConstraint`s.
- **Gold chunks**: reconciled against text hash, so unchanged text keeps its vector and avoids re-embedding.
- **Embed**: processes only `embedding_bin IS NULL` or `embedding IS NULL`.
- **Semantic**: rewrites `lit_semantics` and `lit_duplicate_pairs` atomically.
- **Bootstrap**: `db/bootstrap.py` creates missing tables and applies additive columns defined in
  `_ADDITIVE_COLUMNS` (`is_non_article`, `embedding_bin`, etc.) across all databases.

## 5. Orchestration

`airflow/dags/lake_literature_dags.py` defines seven DAGs, all `schedule=None` (manual/API trigger only):
- `lake_literature_raw/bronze/silver/gold/embed/semantic` and `lake_literature_all`.
- Executed via `BashOperator` invoking `uv run lake-literature --stage <stage>`.
- Client integration via `dashboard/airflow_client.py` and `dashboard/pipeline_control.py`.

## 6. Deployment topology

`docker-compose.yml` defines two services:
- **`dashboard`**: Streamlit on `:8501`, connecting to MySQL and Airflow REST API.
- **`airflow`**: Standalone Airflow on `:8080`, running DAGs with bind-mounted repo codebase.

## 7. Retrieval & Advanced Analytics

The analytical engine separates pure statistical/mathematical computation (`analytics.py`, `forecasting.py`)
from the UI layer (`pages/`), enabling independent unit testing without a Streamlit or MySQL runtime:

### 7.1 Retrieval, Embeddings & Manifold Geometry
- `dashboard/search.py`:
  - `semantic_search`: in-process vector similarity search supporting both `gold.lit_chunks.embedding_bin`
    (zero-copy `np.frombuffer(dtype=np.float32)`) and JSON fallbacks.
  - `build_vector_index` and `search_vector_index`: Faiss (IndexFlatIP / IndexFlatL2) and accelerated linear retrieval.
  - `bm25_search`: pure NumPy/Python BM25 Okapi lexical search for exact acronym and network name matching.
  - `hybrid_search_rrf`: Reciprocal Rank Fusion ($RRF(d) = \sum \frac{1}{60 + \text{rank}(d)}$) combining dense vectors and BM25.
- `dashboard/loaders.py`:
  - `abstract_embeddings`: cached zero-copy matrix loading ($\mathbb{R}^{N \times 384}$) directly from database binary BLOBs.
  - `alternative_projections`: cached PCA 2D and UMAP manifold coordinates for interactive projection toggling.
  - `semantic_novelty_scores`: Cosine Outlier Factor measuring distance to global corpus centroid and k-NN dispersion.

### 7.2 Core Bibliometrics & Heavy-Tail Distribution Fitting
- `analytics.py`:
  - `valid_years`, `source_counts_by`, `cumulative_by_source`, `cumulative_by_category`, `cumulative_by_venue`, `source_means`: foundational data transforms.
  - `fit_heavy_tail_distributions`: MLE fits for Power-Law (Pareto), Log-Normal, and Exponential distributions with Kolmogorov-Smirnov goodness-of-fit testing.
  - `age_normalized_citations`: annualized citation velocity ($c / \text{age}$) and cohort-relative z-scores/percentiles.
  - `mann_kendall_trend`: vectorized non-parametric monotonic trend test ($S, z, p$) with Sen's robust slope estimator.
  - `lotka_law_analysis`: author productivity distribution fitted via Weighted Least Squares (WLS) on log-log coordinates ($f(x) = C / x^\alpha$).
  - `bradford_zones`: concentric scattering zone partitioning ($1 : k : k^2$) across journal venues.
  - `zipf_law_analysis`: word frequency-rank power-law regression on technical vocabulary ($\gamma \approx -1$, $R^2$).
  - `citation_determinants_glm`: Poisson GLM regression estimating Incidence Rate Ratio (IRR) for publication year, team size, references, and venue prestige.

### 7.3 Complex Networks, Author Trajectories & Collaboration
- `analytics.py`:
  - `author_year_matrix`, `researchers_by_year`, `cumulative_researchers`: longitudinal author presence and influx tracking.
  - `author_productivity_trend`: linear trend slope fitted over contiguous career horizons (inactivity gaps filled with zeros to avoid artificial positive bias).
  - `output_impact_correlation`: Pearson and Spearman correlations between author publication volume and mean citation impact.
  - `coauthorship_community_detection`: Louvain modularity clustering utilizing edge weights (`weight="weight"`) reflecting collaboration intensity.
  - `graph_advanced_metrics`: Betweenness and Closeness centralities computed with inverted weights ($d = 1/w$) reflecting communication efficiency, alongside PageRank, density, clustering, and Small-World topology ($\sigma = \frac{C/C_{rand}}{L/L_{rand}}$).
  - `analyze_coauthorship_partners`: breakdown of local vs. global recurrent and occasional coauthors.

### 7.4 Strategic Scientometrics, Semantic Space & Topic Dynamics
- `analytics.py`:
  - `callon_strategic_diagram`: Callon's Strategic Diagram (1991) positioning themes by internal density (cohesion) vs. external centrality across 4 quadrants.
  - `keyword_cooccurrence_graph`: Jaccard-weighted keyword co-occurrence network with Louvain semantic communities and Fruchterman-Reingold layout.
  - `thematic_centroids_similarity`: vectorized cosine similarity matrix ($C \cdot C^T$) between thematic centroids in $\mathbb{R}^{384}$.
  - `thematic_radar_metrics`: 5-axis normalized maturity profiles (Recent Momentum, Theoretical Density, Citation Impact, Scope Adherence, Team Size).
  - `multivariate_correlation_matrix`: pairwise Spearman rank correlation matrix across 7 bibliometric and semantic dimensions.
  - `shannon_thematic_entropy`: longitudinal Shannon information entropy ($H = -\sum p_i \log_2 p_i$) and Gini-Simpson diversity.
  - `geographic_collaboration_stats`: country productivity ranking, international coauthorship share, and bilateral collaboration matrices.
  - `dynamic_topic_ctfidf`: class-based dynamic TF-IDF with shared global vocabulary tracking distinctive topic terminology across historical epochs.
  - `detect_bibliometric_anomalies`: Isolation Forest outlier detection across multidimensional features with automated diagnostic rationales.
  - `detect_structural_breaks`: CUSUM and Chow F-test changepoint detection uncovering historic regime shifts and inflection points.
  - `conceptual_atypicality_analysis`: Brian Uzzi et al. (Science 2013) atypicality model quantifying rare keyword pairings and correlating with top 5% citations.
  - `venue_semantic_clusters`: k-means ontological clustering of publication venues based on average $\mathbb{R}^{384}$ embeddings.

### 7.5 Methodological Synthesis, Solvers & Optimization Taxonomies
- `analytics.py`:
  - `optimization_methods_taxonomy`: pre-compiled regex identification and longitudinal tracking of 9 mathematical paradigms.
  - `objective_functions_taxonomy`: extraction of 6 objective families (Costs, Losses, Reliability, Voltage, Emissions, Resilience), co-optimization matrix, and mono vs. multi-objective temporal ratio.
  - `uncertainty_paradigms_analysis`: categorization of uncertainty modeling (Stochastic, Robust, Fuzzy, DRO, Chance-Constrained) cross-referenced with DER physical resources.
  - `planning_time_horizons_analysis`: taxonomy of planning horizons (Multi-Stage Dynamic Expansion, Co-Optimization with Representative Days, Static).
  - `computational_solvers_analysis`: mapping of algebraic modelers (GAMS, AMPL, Pyomo), exact solvers (CPLEX, Gurobi, MOSEK), scripting environments, and power simulators (OpenDSS, DIgSILENT).
  - `mathematical_complexity_spectrum`: classification of formulation complexity (MILP, SOCP/SDP, MINLP/NLP, Metaheuristics, AI/RL).
  - `benchmark_feeders_analysis`: IEEE benchmark feeder usage (33, 69, 123-bus, real utility grids) cross-referenced with DER resources.
  - `author_impact_advanced_indices`: Hirsch $h$-index, Egghe $g$-index, Zhang $e$-index excess, and $i10$-index.
  - `author_m_quotient_analysis`: Hirsch career velocity ($m = h / \Delta \text{years}$) evaluating academic trajectory pace.
  - `text_readability_and_stylometrics`: linguistic complexity via Flesch Reading Ease (FRE), Flesch-Kincaid Grade Level (FKGL), and Type-Token Ratio (TTR).
  - `citation_longevity_and_decay`: citation half-life calculation and identification of Evergreen fundamental papers.

### 7.6 Technological Frontiers, Disruption & Predictive Modeling
- `analytics.py`:
  - `price_index_analysis`: Derek de Solla Price's (1965) Index of theoretical youth (% references $\le 5$ years old).
  - `sleeping_beauties_detection`: delayed recognition detection and Beauty Coefficient ($B$) computation (Ke et al., 2015).
  - `disruption_index_estimation`: $CD$ disruption index calculation and team size correlation testing (Wu, Wang & Evans, Nature 2019).
  - `open_access_impact_analysis`: Open Access Citation Advantage (OACA) and licensing dynamics.
  - `technological_burst_detection`: Jon Kleinberg's (2002) burst detection modeling technology surges, peaks, and contemporary active frontiers.
- `dashboard/forecasting.py`:
  - `fit_and_forecast`: candidate regression benchmarking with expanding prediction intervals ($\sigma \sqrt{h}$) and rolling-origin cross-validation.
  - `fit_quantile_forecast`: asymmetric Quantile Regression for P10, P50 (median), and P90 uncertainty bounds.
  - `fit_bass_diffusion_nls`: continuous Non-Linear Least Squares Bass diffusion fitting via `scipy.optimize.curve_fit` with physical parameter bounds ($p, q > 0, m \ge \max Y$).

### 7.7 Dashboard UI Architecture & Visual Contracts
- **Zero Chart Duplication Contract**: All 13 pages adhere to a strict non-repetition policy across tabs:
  - `overview.py`: Executive macro overview; does not repeat exhaustive analytical charts from deep-dive pages.
  - `production.py`: 3 chronological tabs (`Volume Anual`, `Crescimento Acumulado`, `Estratos CAPES/Qualis`).
  - `topics.py`: Unified venue ranking with volume/impact toggle, unified CAPES/Qualis selector, Bradford zones, Semantic centroids, Zipf's law, c-TF-IDF, conceptual atypicality, and Chow structural breaks.
  - `highlights.py`: 2 tabs (`Fundamentação Teórica` and `Dinâmica de Citações & Econometria`).
  - `researchers.py`: Author Hub with 6 tabs (`Produtividade & Ranking`, `Liderança Científica`, `Trajetória Temporal`, `Colaboração & Redes`, `Linhas de Pesquisa`, `Leis Bibliométricas`).
  - `synthesis.py`: 7 engineering optimization tabs (MILP/SOCP, Pareto Objectives, Uncertainty vs DERs, Planning Horizons, IEEE Feeders, Solvers/Simulators, Citation Longevity).
  - `frontiers.py`: 5 innovation tabs (Price Index, Sleeping Beauties, CD Disruption Index, OACA, Kleinberg Bursts).
  - `forecasting.py`: Volume forecasts, topic trajectories, and continuous Bass NLS diffusion.
  - `semantics.py`: Screening margin, multi-projection 2D map, discovered themes, novelty score, duplicate pairs.
- **Visual & Polar Chart Theme Contract**:
  - All Plotly charts implement dynamic theme tokens (`theme_color`, `chart_theme_tokens`, `apply_chart_theme`).
  - Polar and Radar charts (`thematic_radar_chart`) explicitly configure `paper_bgcolor="rgba(0,0,0,0)"` and `polar_bgcolor="rgba(0,0,0,0)"`, ensuring 100% transparent backgrounds and eliminating unsightly white bounding boxes in Streamlit dark mode.
  - All layout containers and components enforce `width="stretch"`.

## 8. Testing

`tests/` (pytest, `uv run pytest`) executes against in-memory SQLite sessions (one per medallion layer,
defined in `tests/conftest.py`), requiring zero MySQL server connectivity:

**186 tests across 22 test files**:
1. `test_raw_bib.py` — BibTeX parsing without separators, hash manifest idempotency.
2. `test_bronze_articles.py` — DOI normalization, author/keyword splitting, type coercion.
3. `test_silver_articles.py` — Title normalization, primary record merging, non-article flagging, PDF linking.
4. `test_gold_articles.py` — Text chunking, overlap boundaries, chunk reconciliation, embedding retention.
5. `test_semantics.py` — Relevance scores, contrastive margin, near-duplicates, theme discovery, injected anchors.
6. `test_advanced_semantics.py` — PCA 2D, UMAP fallback, thematic centroids, temporal drift, semantic novelty / COF.
7. `test_advanced_statistics.py` — Heavy-tail MLE & KS, age normalization, Mann-Kendall, Lotka, Bradford, Zipf's law, Louvain, PageRank, Closeness, Small-World, GLM.
8. `test_advanced_ml.py` — Dynamic topic c-TF-IDF, Isolation Forest bibliometric anomaly detection, Quantile forecasting bounds, Bass diffusion parameter estimation.
9. `test_strategic_analytics.py` — Callon's strategic diagram, keyword co-occurrence, centroid similarity, radar metrics, Spearman matrix, Shannon entropy, geographic collaboration.
10. `test_synthesis_analytics.py` — Optimization taxonomy, IEEE benchmark feeders, author h/g/e/m-indices, stylometrics, citation longevity, objective functions, uncertainty paradigms, planning horizons, solvers, and complexity spectrum.
11. `test_frontiers_analytics.py` — Price's index, sleeping beauties, disruption CD index, open access citation advantage, and Kleinberg burst detection.
12. `test_screening_calibration.py` — Stratified sampling across margin strata, threshold sensitivity/specificity.
13. `test_openalex_enrichment.py` — OpenAlex REST response parsing, incremental cache updates.
14. `test_dag_import.py` — Airflow DAG module import and structural validation with mocked SDK.
15. `test_bootstrap.py` — Additive column map validation and SQLite table generation.
16. `test_analytics.py` — Core aggregation contracts, layer funnels, and data transformations.
17. `test_analytics_authors.py` — Author identity canonicalization, matrix pivoting, and productivity slopes.
18. `test_search.py` — Binary vector parsing, ranking order, null exclusion, top-k truncation, vector index building and retrieval.
19. `test_forecasting.py` — Candidate model fitting, rolling-origin cross-validation, and Bass diffusion.
20. `test_qualis.py` — CAPES/Qualis venue fuzzy matching, stratification tiers, and color mappings.
21. `test_charts.py` — Plotly chart axis naming contracts, Lorenz curves, and polymorphic metric rows.
22. `test_theme.py` — Dark/Light theme token contracts, contrast rules, transparent polar background contracts, and CSS chrome isolation.
