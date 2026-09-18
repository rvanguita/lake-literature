"""CLI orchestrator for the medallion pipeline.

Usage:
    uv run lake-literature --stage raw
    uv run lake-literature --stage bronze
    uv run lake-literature --stage silver
    uv run lake-literature --stage gold
    uv run lake-literature --stage embed
    uv run lake-literature --stage semantic
    uv run lake-literature --stage all       # default
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime

from lake_literature.db.bootstrap import bootstrap
from lake_literature.db.engines import get_session
from lake_literature.ingest.raw_bib import load_bib_entries
from lake_literature.ingest.raw_config import load_configs
from lake_literature.ingest.raw_csv import load_ieee_csv
from lake_literature.ingest.raw_pdfs import load_pdf_inventory
from lake_literature.transform.bronze_articles import build_bronze_articles
from lake_literature.transform.embeddings import build_embeddings
from lake_literature.transform.gold_articles import build_gold_articles
from lake_literature.transform.semantics import build_semantics
from lake_literature.transform.silver_articles import build_silver_articles

STAGES = ("raw", "bronze", "silver", "gold", "embed", "semantic", "all")

logger = logging.getLogger(__name__)


def _record_run(stage: str, started: datetime, stats: dict | None, error: str | None) -> None:
    """Persist a pipeline run record to `gold.lit_pipeline_runs`."""
    try:
        from lake_literature.db.gold_models import PipelineRun

        finished = datetime.now(UTC)
        run = PipelineRun(
            stage=stage,
            started_at=started,
            finished_at=finished,
            duration_seconds=(finished - started).total_seconds(),
            stats=stats,
            status="error" if error else "success",
            error_message=error,
        )
        session = get_session("gold")
        try:
            session.add(run)
            session.commit()
        finally:
            session.close()
    except Exception:
        logger.debug("_record_run: could not persist run record", exc_info=True)


def run_raw() -> dict:
    started = datetime.now(UTC)
    session = get_session("raw")
    try:
        n_config = load_configs(session)
        n_csv = load_ieee_csv(session)
        n_bib = load_bib_entries(session)
        n_pdf = load_pdf_inventory(session)
        stats = {
            "config": n_config,
            "ieee_csv_rows": n_csv,
            "bib_entries": n_bib,
            "pdf_files": n_pdf,
        }
        print(f"[raw] {stats}")
        _record_run("raw", started, stats, None)
        return stats
    except Exception as exc:
        _record_run("raw", started, None, str(exc))
        raise
    finally:
        session.close()


def run_bronze() -> dict:
    started = datetime.now(UTC)
    raw_session = get_session("raw")
    bronze_session = get_session("bronze")
    try:
        stats = build_bronze_articles(raw_session, bronze_session)
        stats = {"articles": stats["written"], "enriched": stats["enriched"]}
        print(f"[bronze] {stats}")
        _record_run("bronze", started, stats, None)
        return stats
    except Exception as exc:
        _record_run("bronze", started, None, str(exc))
        raise
    finally:
        raw_session.close()
        bronze_session.close()


def run_silver() -> dict:
    started = datetime.now(UTC)
    bronze_session = get_session("bronze")
    silver_session = get_session("silver")
    raw_session = get_session("raw")
    try:
        stats = build_silver_articles(bronze_session, silver_session, raw_session)
        print(f"[silver] {stats}")
        _record_run("silver", started, stats, None)
        return stats
    except Exception as exc:
        _record_run("silver", started, None, str(exc))
        raise
    finally:
        bronze_session.close()
        silver_session.close()
        raw_session.close()


def run_gold() -> dict:
    started = datetime.now(UTC)
    silver_session = get_session("silver")
    gold_session = get_session("gold")
    try:
        stats = build_gold_articles(silver_session, gold_session)
        print(f"[gold] {stats}")
        _record_run("gold", started, stats, None)
        return stats
    except Exception as exc:
        _record_run("gold", started, None, str(exc))
        raise
    finally:
        silver_session.close()
        gold_session.close()


def run_embed() -> dict:
    started = datetime.now(UTC)
    gold_session = get_session("gold")
    try:
        stats = build_embeddings(gold_session)
        print(f"[embed] {stats}")
        _record_run("embed", started, stats, None)
        return stats
    except Exception as exc:
        _record_run("embed", started, None, str(exc))
        raise
    finally:
        gold_session.close()


def run_semantic() -> dict:
    started = datetime.now(UTC)
    gold_session = get_session("gold")
    try:
        stats = build_semantics(gold_session)
        print(f"[semantic] {stats}")
        _record_run("semantic", started, stats, None)
        return stats
    except Exception as exc:
        _record_run("semantic", started, None, str(exc))
        raise
    finally:
        gold_session.close()


def run_all() -> dict:
    bootstrap()
    return {
        "raw": run_raw(),
        "bronze": run_bronze(),
        "silver": run_silver(),
        "gold": run_gold(),
        "embed": run_embed(),
        "semantic": run_semantic(),
    }


def run(stage: str) -> None:
    bootstrap()
    if stage in ("raw", "all"):
        run_raw()
    if stage in ("bronze", "all"):
        run_bronze()
    if stage in ("silver", "all"):
        run_silver()
    if stage in ("gold", "all"):
        run_gold()
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
