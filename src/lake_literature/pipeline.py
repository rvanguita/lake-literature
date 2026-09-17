"""CLI orchestrator for the medallion pipeline.

Usage:
    uv run lake-literature --stage raw
    uv run lake-literature --stage enrich
    uv run lake-literature --stage bronze
    uv run lake-literature --stage silver
    uv run lake-literature --stage gold
    uv run lake-literature --stage embed
    uv run lake-literature --stage semantic
    uv run lake-literature --stage all       # default
"""

from __future__ import annotations

import argparse
import functools
import sys
from collections.abc import Callable

from lake_literature.db import utcnow
from lake_literature.db.bootstrap import bootstrap
from lake_literature.db.engines import get_session
from lake_literature.db.raw_models import PipelineRun
from lake_literature.ingest.enrichment_api import build_enrichment
from lake_literature.ingest.raw_bib import load_bib_entries
from lake_literature.ingest.raw_config import load_configs
from lake_literature.ingest.raw_csv import load_ieee_csv
from lake_literature.ingest.raw_pdfs import load_pdf_inventory
from lake_literature.transform.bronze_articles import build_bronze_articles
from lake_literature.transform.embeddings import build_embeddings
from lake_literature.transform.gold_articles import build_gold_articles
from lake_literature.transform.semantics import build_semantics
from lake_literature.transform.silver_articles import build_silver_articles

STAGES = ("raw", "enrich", "bronze", "silver", "gold", "embed", "semantic", "all")


def _recorded(stage: str) -> Callable:
    """Persist one `lit_pipeline_runs` row per execution of the wrapped stage.

    Applied to the `run_*` wrappers rather than to the `build_*` transforms, so
    a stage started from the CLI, from `run_all()` or by an Airflow task (which
    shells out to this same CLI) is recorded once, in one place -- while the
    transforms stay pure functions that take sessions and return stats.

    A failure is recorded before the exception is re-raised: a crashed run is
    exactly the one worth having a row for.
    """

    def decorator(fn: Callable[..., dict]) -> Callable[..., dict]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> dict:
            session = get_session("raw")
            run = PipelineRun(
                stage=stage,
                started_at=utcnow(),
                status="running",
            )
            session.add(run)
            session.commit()
            try:
                stats = fn(*args, **kwargs)
            except Exception as exc:
                run.status = "error"
                run.error = f"{type(exc).__name__}: {exc}"
                run.finished_at = utcnow()
                session.commit()
                raise
            else:
                run.status = "success"
                run.stats = stats
                run.finished_at = utcnow()
                session.commit()
                return stats
            finally:
                session.close()

        return wrapper

    return decorator


@_recorded("raw")
def run_raw() -> dict:
    session = get_session("raw")
    try:
        n_config = load_configs(session)
        csv_stats = load_ieee_csv(session)
        bib_stats = load_bib_entries(session)
        n_pdf = load_pdf_inventory(session)
        stats = {
            "config": n_config,
            "ieee_csv_rows": csv_stats["rows"],
            "bib_entries": bib_stats["entries"],
            "pdf_files": n_pdf,
            # Named, not just counted: a file that failed to parse is skipped
            # and retried next run, so the operator needs to know which one.
            "failed_files": csv_stats["failed_files"] + bib_stats["failed_files"],
            # Entries a readable .bib still lost: bibtexparser skips a corrupt
            # block instead of raising, so this would otherwise be invisible.
            "failed_bib_blocks": bib_stats["failed_blocks"],
        }
        print(f"[raw] {stats}")
        return stats
    finally:
        session.close()


@_recorded("enrich")
def run_enrich() -> dict:
    """Fetch citation/reference counts for DOIs the exports don't carry them for.

    Between `raw` (which supplies the DOIs) and `bronze` (which consumes the
    counts). Network-bound and best-effort: it never fails the pipeline, it just
    reports how much it managed to fill.
    """
    session = get_session("raw")
    try:
        stats = build_enrichment(session)
        print(f"[enrich] {stats}")
        return stats
    finally:
        session.close()


@_recorded("bronze")
def run_bronze() -> dict:
    raw_session = get_session("raw")
    bronze_session = get_session("bronze")
    try:
        stats = build_bronze_articles(raw_session, bronze_session)
        stats = {"articles": stats["written"], "enriched": stats["enriched"]}
        print(f"[bronze] {stats}")
        return stats
    finally:
        raw_session.close()
        bronze_session.close()


@_recorded("silver")
def run_silver() -> dict:
    bronze_session = get_session("bronze")
    silver_session = get_session("silver")
    raw_session = get_session("raw")
    try:
        stats = build_silver_articles(bronze_session, silver_session, raw_session)
        print(f"[silver] {stats}")
        return stats
    finally:
        bronze_session.close()
        silver_session.close()
        raw_session.close()


@_recorded("gold")
def run_gold(warn_pending: bool = True) -> dict:
    """Rebuild the gold layer.

    `warn_pending` is False when the caller goes on to run `embed` itself (the
    `all` flow), so the reminder only appears when the chunks would actually be
    left without vectors.
    """
    silver_session = get_session("silver")
    gold_session = get_session("gold")
    try:
        stats = build_gold_articles(silver_session, gold_session)
        print(f"[gold] {stats}")
        pending = stats.get("chunks_missing_embedding", 0)
        if warn_pending and pending:
            print(
                f"[gold] WARNING: {pending} chunk(s) have no embedding -- run "
                "`--stage embed` and then `--stage semantic`, or the semantic "
                "signals will keep describing an older state of the corpus"
            )
        return stats
    finally:
        silver_session.close()
        gold_session.close()


@_recorded("embed")
def run_embed() -> dict:
    gold_session = get_session("gold")
    try:
        stats = build_embeddings(gold_session)
        print(f"[embed] {stats}")
        return stats
    finally:
        gold_session.close()


@_recorded("semantic")
def run_semantic() -> dict:
    gold_session = get_session("gold")
    try:
        stats = build_semantics(gold_session)
        print(f"[semantic] {stats}")
        return stats
    finally:
        gold_session.close()


def run_all() -> dict:
    bootstrap()
    return {
        "raw": run_raw(),
        "enrich": run_enrich(),
        "bronze": run_bronze(),
        "silver": run_silver(),
        "gold": run_gold(warn_pending=False),
        "embed": run_embed(),
        "semantic": run_semantic(),
    }


def run(stage: str) -> None:
    bootstrap()
    if stage in ("raw", "all"):
        run_raw()
    if stage in ("enrich", "all"):
        run_enrich()
    if stage in ("bronze", "all"):
        run_bronze()
    if stage in ("silver", "all"):
        run_silver()
    if stage in ("gold", "all"):
        run_gold(warn_pending=stage != "all")
    if stage in ("embed", "all"):
        run_embed()
    if stage in ("semantic", "all"):
        run_semantic()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="lake-literature medallion pipeline")
    parser.add_argument("--stage", choices=STAGES, default="all", help="pipeline stage to run")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    run(args.stage)


if __name__ == "__main__":
    main()
