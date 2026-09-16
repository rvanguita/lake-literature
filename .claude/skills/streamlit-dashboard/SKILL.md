---
name: streamlit-dashboard
description: Conventions for the lake-literature Streamlit dashboard (src/lake_literature/dashboard/) — page contract, chart contract, theme tokens, aggregation rules, and data pitfalls. Use whenever adding or editing a dashboard page, chart, or shared helper.
---

# lake-literature Streamlit dashboard

This dashboard grew past 2,600 lines with real duplication before a refactor
(see git history around "Refatoração do dashboard + novas análises"). These
rules exist to keep it from drifting back.

## Page contract

- One module per page under `dashboard/pages/`, exposing a single zero-arg
  `render() -> None`.
- Register it in `dashboard/app.py`'s `PAGES` list — `(render_fn, title, icon,
  url_path)` — and it's automatically wired into `st.navigation`.
- Start every page with `articles_df = loaders.require_articles()` (or
  `loaders.filtered_chunks()` for chunk-only pages). This applies the global
  sidebar filters and handles the empty-state / `st.stop()` case — don't
  reimplement either.
- `render_sidebar()` runs before `navigation.run()` in `app.py`, so global
  filter state (`global_year_range`, `global_sources`, `global_venues`) is
  already in `st.session_state` by the time your page renders.
- **Exception: `pages/forecasting.py` calls `loaders.articles()` directly,
  not `require_articles()`.** A time-series forecast needs the full year
  history to fit a trend — applying the sidebar's global year filter would
  silently truncate the training data. It says so in its own `hero_banner`.
  Any other page that needs the *entire* corpus regardless of sidebar state
  should follow the same pattern (and disclose it the same way) rather than
  quietly ignoring `require_articles()`.

## Chart contract

- **Never add a reference/guide line to a chart** — no `add_hline`,
  `add_vline`, `add_shape`, `add_hrect`/`add_vrect`, or benchmark
  annotations. This was ripped out of `theme.py` (`add_source_layers`) on
  purpose: it covered the data with dotted lines and text boxes. If a mean or
  benchmark matters, put it in a `metric_row` card or the chart's `caption`
  instead.
- Build the figure with a helper from `dashboard/charts.py` when the shape
  matches: `source_bars`/`source_lines` for IEEE/Elsevier/Total comparisons,
  `topn_hbar` for ranked top-N bars, `stacked_area` for composition-over-time.
  Add a new builder there rather than hand-rolling `px`/`go` calls in a page
  a second time.
- Compute the data for a chart in `dashboard/analytics.py` (pure pandas, no
  `streamlit` import) — not inline in the page function. Reuse
  `valid_years`, `source_counts_by`, `cumulative_by_source`,
  `cumulative_by_venue`, `source_means`, `explode_authors`,
  `explode_keywords`, `canonical_author` before writing a new groupby.
- Finish every chart with `components.render_chart(fig, caption=..., height=...)`
  — it applies `polish_figure_layout` and calls `st.plotly_chart` +
  `st.caption` in one place. Don't call `polish_figure_layout` /
  `st.plotly_chart` directly in a page.
- Guard missing columns with `components.require_columns(df, [...], message)`
  instead of a bespoke `st.info(...)`.
- "Total" is a **real series/trace** (`TOTAL_COLOR`, `TOTAL_LABEL` from
  `theme.py`), not a reference line. `source_counts_by`/`cumulative_by_source`
  already return an explicit `total` column for this.

## Theme tokens (`dashboard/theme.py`)

- `SOURCE_COLORS` / `SOURCE_LABELS` — IEEE blue / Elsevier orange, from each
  publisher's brand guidelines. Use these, don't invent new colors for the
  same two publishers.
- `CATEGORICAL_PALETTE` — the dataviz skill's 8-slot CVD-checked palette, for
  charts with many sub-categories (venues, keywords, network nodes).
- `TOTAL_COLOR` / `TOTAL_LABEL` — a vivid magenta/pink (`#ff2e77`), chosen to
  stand out against both `SOURCE_COLORS`. It used to be a dull gray and
  nearly disappeared next to the two saturated brand colors — don't revert
  it to a neutral tone.
- `OTHER_COLOR` — always for the catch-all "Outros" bucket, via
  `venue_color_map(order, others_label=...)`.
- `CHART_HEIGHT` — the shared height for side-by-side chart pairs.
- New chart-design decisions (color formula, mark selection, KPI-tile layout)
  should go through the `dataviz` skill first; this dashboard's palette
  already came from it.

### Light/dark theme support

The dashboard has **its own** dark/light control — a radio in the sidebar
(`theme.render_theme_toggle()`, called at the very top of `app.main()`,
before `apply_dashboard_theme()`) — deliberately **not** Streamlit's built-in
theme toggle or `st.context.theme.type`. That API's own docstring says the
theme type "may be incorrect ... when the app is first loaded within a
session" and "when the user changes the theme in the settings menu" (see
Streamlit GitHub issue #11920) — i.e. it's unreliable at exactly the two
moments a user would notice. An earlier version of this dashboard used it
and light mode intermittently didn't apply; don't reintroduce that.

The single source of truth is `st.session_state["dashboard_theme_mode"]`
(`"dark"` by default, so a fresh session looks exactly like before this
existed). `theme._active_theme_type()` reads that key, `theme._tokens()`
returns the matching palette (`_DARK_TOKENS` / `_LIGHT_TOKENS`), and
`apply_dashboard_theme()` / `polish_figure_layout()` build their CSS /
Plotly `paper_bgcolor`/`plot_bgcolor`/font/grid colors from it. **Never
hardcode a hex color for chart backgrounds or the injected CSS** — add a new
token to both dicts instead, or the color will be wrong in one of the two
themes. A data color scale (e.g. `color_continuous_scale` on a heatmap or
scatter) is not chrome and is fine to hardcode — it colors marks by value,
not the page/chart background.

### Avoiding title/legend overlap

Plotly places a horizontal top legend at a fixed `y` regardless of how many
lines the chart's own title wraps to, so a title + legend combination can
overlap (this happened with `source_bars`/`source_lines` charts once titles
got long). Two rules keep this from recurring:

1. **Don't set a Plotly-level `title` when the page already has an
   `st.subheader`/`st.markdown` header directly above the chart** — that's
   true for most charts in this dashboard. Only give a chart its own title
   when it sits in a column next to a sibling chart under one shared
   subheader (e.g. `production._venue_comparison`'s IEEE/Elsevier pair) or
   the title carries dynamic information the header doesn't (e.g. the
   Pearson-r value in `highlights._references_vs_citations`).
2. `polish_figure_layout()` still defends against the collision when a title
   *is* set: it detects `fig.layout.title.text` and reserves more top margin
   and a higher legend `y` automatically. Don't work around this by hardcoding
   your own `margin`/`legend.y` in a page — extend the function if the
   spacing ever needs to change.

## Aggregation rule

Pure pandas logic lives in `dashboard/analytics.py` (no Streamlit import, so
it's testable/cacheable independently). UI-facing caching wrappers live in
`dashboard/loaders.py` with `@st.cache_data(ttl=60)`; raw SQL against the
medallion databases lives in `dashboard/data.py`. A page function should
mostly be: call a loader, call an analytics function, call a chart builder,
call `render_chart`.

## Data pitfalls specific to this corpus

- `citation_count` / `reference_count` are **NULL for "not collected", never
  0**. Elsevier's counts come from an offline enrichment cache
  (`data/enrichment_cache.json`, applied in `ingest/enrichment.py` during the
  bronze stage) — don't treat a null as zero impact.
- `gold.articles` has a `sources` column (JSON list, mirrors silver) — added
  so gold can be split IEEE/Elsevier like every other layer. If you add a new
  gold column, check whether bronze/silver need the same for source-breakdown
  charts to keep working across all three layers.
- IEEE keyword counts are inflated: bronze concatenates `Author Keywords`
  with `IEEE Terms` without deduplicating (`transform/bronze_articles.py`).
  Don't present "IEEE has richer keywords" as a finding without this caveat.
- Author names are **not the same identity across sources**: IEEE exports
  initials (`J. Liu`), Elsevier full names (`Junyong Liu`), IEEE's own `.bib`
  uses `Last, First`. `analytics.canonical_author` folds these to `"initial
  surname"` — a real simplification that can also merge distinct people who
  share an initial+surname. Any author-identity chart must disclose this
  (see `hero_banner` on the Pesquisadores page for the wording to reuse).
- `year` ranges 1926–2027 (2027 = in-press). Use `analytics.valid_years` with
  an explicit window rather than a bare `pd.to_numeric` — a stray old/future
  row will otherwise dominate any trend/rate calculation.
- There is no pipeline run-history table. Stage stats
  (`pipeline.py`'s `run_raw`/`run_bronze`/etc.) only go to `print` and Airflow
  task logs; silver/gold are truncated and rebuilt every run. Any
  "camadas/funil" chart is computed live from current row counts, not from a
  persisted history — say so in the page rather than implying otherwise.
- The **current year in the corpus is always a partial year** — it's
  collected by hand mid-year, not a closed dataset. `dashboard/forecasting.py`
  (used by `pages/forecasting.py`) treats its `HOLDOUT_YEAR` this way
  explicitly: it's used for model validation but every note/label calls it
  "parcial" rather than presenting it as a finished year. Any new
  year-over-year comparison involving the current year should do the same.
- Forecasting uses plain regression (`sklearn.linear_model.LinearRegression`,
  optionally with `PolynomialFeatures`, plus a log-linear fit for exponential
  growth), not a heavier model — the usable series is short (~16 yearly
  points from `MIN_TRAIN_YEAR = 2010` onward). Don't reach for a model class
  that needs more data than the corpus has just because it's "more ML."
- `lit_gold.chunks.embedding` is filled by the `embed` pipeline stage
  (`transform/embeddings.py`, via `fastembed`'s local ONNX model
  `BAAI/bge-small-en-v1.5`, no API key), not automatically by `--stage gold`.
  It's idempotent — only `embedding IS NULL` rows are processed — so a chunk
  never gets re-embedded, and a partial run (killed mid-way) resumes cleanly
  since each batch commits before the next one starts. If the embeddings
  gauge on Qualidade e RAG ever reads 0% again, it means this stage hasn't
  run yet for the current chunks, not that something is broken.
