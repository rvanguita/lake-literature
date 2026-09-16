# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`lake-literature` — a systematic-literature-review pipeline over bibliographic exports on the topic
*"distribution system planning"* (electric power distribution networks). The corpus is assembled by hand from
publisher search UIs and then processed locally with pandas.

`src/lake_literature/` now holds a full medallion pipeline (raw → bronze → silver → gold, one MySQL database
per layer via SQLAlchemy — see `pipeline.py`, `db/`, `ingest/`, `transform/`) plus a Streamlit dashboard
(`dashboard/`). The corpus under `data/` is still the substantial input the pipeline consumes.

## Commands

Managed by [uv](https://docs.astral.sh/uv/) (Python 3.13, `uv_build` backend, src layout).

```bash
uv sync                                    # create/refresh .venv from uv.lock
uv run streamlit run main.py               # launch the dashboard from the repo root
uv run lake-literature --stage all        # run the full raw->bronze->silver->gold pipeline
uv run lake-literature --stage <layer>    # run a single stage (raw|bronze|silver|gold)
uv run python -c '...'                     # anything else inside the project venv
uv add <pkg>                               # add a dependency (updates pyproject.toml + uv.lock)
uv run pytest                              # run the test suite (tests/, in-memory SQLite, no MySQL needed)
docker compose up -d                       # dashboard container, port 8501, reads .env for MySQL
```

Tests live under `tests/` (pytest, added as a dev dependency). They cover pure transform logic
(`normalize_doi`, `_chunk_text`, `_merge_group`, ...) plus small end-to-end runs of `build_silver_articles`
against in-memory SQLite sessions — one per medallion layer, mirroring the real one-database-per-layer setup.
No linter/formatter is configured yet.

`main.py` at the repo root is the Streamlit entry point (`import lake_literature.dashboard.app` for its side
effects) — it is not the place for ad-hoc pandas exploration anymore; do that in a notebook/interactive cell
instead. MySQL connection settings live in `.env` (git-ignored; see `.env.example`).

## Data corpus (`data/`, gitignored)

`data/` is excluded from git, so it exists only on this machine and paths referenced in code will not resolve for
anyone else. Treat it as read-only input: it is raw publisher output, re-downloading it is manual and tedious.

```
data/ieee/       IEEE Xplore export: one metadata CSV + paginated .bib files + bulk-download*.zip of PDFs
data/elsevier/   ScienceDirect export: paginated .bib files only (no CSV, no PDFs)
data/articles/   ~96 PDFs, extracted from the IEEE bulk-download zips
data/sciencedirect.zip   original archive that data/elsevier/ was unpacked from
```

**`config.csv` is provenance, not data.** Each source directory has one, and it holds the free-text record of the
search that produced that export — query string, filters, year range, and the full search URL. It is not a
parseable table; never feed it to `pd.read_csv` expecting columns. When the corpus is refreshed, update the
matching `config.csv` so the search is reproducible.

### The two sources are not interchangeable

Anything that merges IEEE and Elsevier records has to normalize these differences:

| | IEEE Xplore | ScienceDirect / Elsevier |
|---|---|---|
| Metadata | `export*.csv` (28 columns: `Document Title`, `Authors`, `Abstract`, `DOI`, `Author Keywords`, `IEEE Terms`, …) plus `.bib` | `.bib` only |
| Entry type | `@ARTICLE` | `@article` |
| Page size | 25 entries per `.bib` | 100 entries per `.bib` (URL `offset=` drives pagination) |
| `doi` field | bare DOI — `10.1109/TPWRS.2024.3418651` | full URL — `https://doi.org/10.1016/j.ijepes.2020.106042` |
| `keywords` | `;`-separated | `,`-separated |
| Venue field | `journal` | `journal`, plus `url` and sometimes `note` |
| Full text | yes, PDFs in the zips | none |

DOI is the only reliable cross-source join/dedup key — strip the `https://doi.org/` prefix and casefold before
comparing, or the same paper indexed by both publishers will survive deduplication twice.

### BibTeX parsing gotcha

The IEEE `.bib` files are written with **no separator between entries** — one entry's closing brace is immediately
followed by the next `@ARTICLE{`, on the same line:

```
  month={Feb},}@ARTICLE{10854892,
```

Line-oriented or naive split-on-`@` parsing will silently merge or truncate records. Use a real BibTeX parser
(e.g. `bibtexparser`) or split on `}@` deliberately. Elsevier's files do put each entry on its own lines, so code
tested only against `data/elsevier/` will appear to work and then fail on IEEE.

### PDF filenames

PDFs in `data/articles/` are named after the article title with punctuation replaced by `-`, e.g.
`Use of Computer Graphics ... in -Electricite de France- -E.D.F.-.pdf` for a title containing quotes and accents.
The mapping back to a title is lossy, so match PDFs to metadata via a normalized/fuzzy title comparison rather
than exact string equality — and prefer DOI-keyed renaming if a linking step is ever added.

### Counts don't line up

The IEEE CSV reports ~304 search hits but the downloaded `.bib` files total ~266 entries, and only ~96 PDFs were
retrieved. The corpus is deliberately incomplete; do not treat a count mismatch as a bug to fix in code.

## Notes

- `.env` holds MySQL connection settings plus `AIRFLOW_BASE_URL`; it's git-ignored (see `.env.example` for
  the expected keys).
- `README.md` has a full project overview (architecture, quick start, layout) in English.
