# Roadmap — lake-literature

Improvement backlog for the pipeline and dashboard. See [`../README.md`](../README.md) for orientation,
[`PRD.md`](PRD.md) for why the project exists and [`SDD.md`](SDD.md) for how it is built.

Every item here carries the measurement that motivated it, taken from the live corpus on **2026-09-17**
(1,831 articles, 6,235 chunks, all embedded). Numbers age; re-measure before acting on an item rather
than trusting the figure below. Ordering is by impact on the review's output, not by effort.

## High impact

### 1. Embeddings are stored as JSON text

`gold.lit_chunks` occupies **50 MB on disk for 6,235 vectors** — roughly 8 KB per 384-dimension vector,
against ~1.5 KB for the same numbers as float32 binary. Every read pays the parse too: the dashboard's
similarity search and the `semantic` stage both load the full column and `json.loads` it row by row.

Move the vector to a binary column (`LargeBinary` + `np.frombuffer`), added through the additive
migration in `db/bootstrap.py` and backfilled from the JSON column, which stays until the switch is
proven. Touches `db/gold_models.py`, `transform/embeddings.py`, `transform/semantics.py` and
`dashboard/search.py`.

### 2. Relevance screening is validated against pseudo-labels

The contrastive margin reports ROC AUC 0.995, but the "ground truth" it is scored against is the
corpus's own logistics cluster — the same embeddings that produced the score. That is circular enough
to be indicative only, and `transform/semantics.py` says so.

Hand-label a stratified sample (~100 articles, sampled across the margin's range) and recompute
precision/recall against real labels, then calibrate the cut from that instead of accepting zero as a
given. This is a methodological requirement of the SLR, not only an engineering nicety: the screening
decision has to be defensible in the write-up.

### 3. There is no pipeline run history

Stage statistics only reach `print` and the Airflow task log. The "Camadas & Pipeline" page therefore
computes its funnel live from current row counts, and nothing in the system can answer "what changed
between the last two runs" — exactly the question a corpus refresh raises.

Add a `lit_pipeline_runs` table written by `pipeline.py` (stage, started/finished, row counts, the stats
dict each `run_*` already returns), and read it on that page.

### 4. 108 records are not articles

Measured by `record_type`: 105 Elsevier `incollection` plus 3 IEEE `book`/`inbook` — book front matter
("Preface", "Index") ingested as if it were a paper. Today only the semantic score catches them, after
the fact and by proxy.

Flag them explicitly at silver, where `record_type` is already carried, combined with the
missing/short-abstract signal, so the exclusion is a stated rule rather than a side effect of a cosine
threshold.

## Medium

### 5. Full text covers 5.2% of the corpus but 70% of the chunks

96 of 1,831 articles have a linked PDF, and those 96 produce **4,404 of the 6,235 chunks**. Any
chunk-level statistic on the dashboard ("Qualidade e RAG" chunk sizes, embedding counts) describes that
5% of the corpus, not the corpus.

Split those charts by `chunk_type` and state the coverage next to them, the way the IEEE-only fields
already disclose their ~17%.

### 6. 31 articles have no abstract

`silver.lit_articles.has_abstract` is true for 1,800 of 1,831. For the other 31, the "abstract" chunk is
just title + keywords, so their relevance score comes from a much weaker vector than everyone else's —
and it is presented on the same scale.

Mark them in the screening table and exclude them from the margin's percentile statistics, rather than
letting a title-only vector be compared against a full abstract's.

### 7. Rejected records exist only as a counter

Five bronze rows are dropped at silver for having no DOI (1,836 → 1,831). The count is returned in the
stage's stats dict and then lost. Persist the rejects (a `lit_rejected` table, or a written report) so
the exclusion is auditable — an SLR has to be able to say what it threw away and why.

### 8. Elsevier citation counts come from a hand-built file

`data/enrichment_cache.json` is maintained by hand and re-applied after every bronze build
(`ingest/enrichment.py`). Crossref and OpenAlex both serve citation and reference counts by DOI without
an API key; a cached enrichment step would replace the manual file.

This is a product decision, not only a technical one: the project deliberately avoids external APIs for
embedding. Fetching public bibliographic metadata is a different trade-off and should be taken
knowingly.

### 9. Test gaps

105 tests cover the transforms, the dashboard's pure analytics and the chart/theme contracts. Three
gaps stand out:

- nothing imports `airflow/dags/lake_literature_dags.py`, so a broken DAG only surfaces in the Airflow
  UI — a one-line import test would catch it in CI;
- `db/bootstrap.py` has no test at all, despite its additive-column map having just changed shape
  (keyed by table now);
- `transform/semantics.py::build_semantics` can't be exercised end to end because `_embed_anchors`
  loads fastembed internally; injecting the anchor vectors would make the whole stage testable against
  the SQLite fixtures.

## Low / noted

### 10. Near-duplicates are surfaced but never merged

`lit_duplicate_pairs` holds 18 pairs of near-identical abstracts under distinct DOIs. The dashboard
lists them and stops there, because pages are read-only by contract. Acting on them needs a product
decision about where a reviewer's judgement would be stored.

### 11. `loaders.articles()` reads the whole silver table per rerun

Cached for 60 s and ~3.5 MB per read, which is fine at 1,831 rows. If the corpus grows another order of
magnitude, push the year/source filters into SQL instead of filtering the frame in pandas.

### 12. Airflow runs as a single all-admin container

`airflow standalone` with `AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_ALL_ADMINS=True` suits one person running
this locally, and the SDD says so. It is not a configuration to expose beyond that.
