"""CLI orchestrator for the medallion pipeline.

Usage:
    uv run lake-literature --stage raw
    uv run lake-literature --stage bronze
    uv run lake-literature --stage silver
    uv run lake-literature --stage gold
    uv run lake-literature --stage embed
    uv run lake-literature --stage all       # default
"""

from __future__ import annotations

import argparse
import sys

from lake_literature.db.bootstrap import bootstrap
from lake_literature.db.engines import get_session
from lake_literature.ingest.raw_bib import load_bib_entries
from lake_literature.ingest.raw_config import load_configs
from lake_literature.ingest.raw_csv import load_ieee_csv
from lake_literature.ingest.raw_pdfs import load_pdf_inventory
from lake_literature.transform.bronze_articles import build_bronze_articles
from lake_literature.transform.embeddings import build_embeddings
from lake_literature.transform.gold_articles import build_gold_articles
from lake_literature.transform.silver_articles import build_silver_articles

STAGES = ("raw", "bronze", "silver", "gold", "embed", "all")


def run_raw() -> dict:
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
        return stats
    finally:
        session.close()


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


def run_gold() -> dict:
    silver_session = get_session("silver")
    gold_session = get_session("gold")
    try:
        stats = build_gold_articles(silver_session, gold_session)
        print(f"[gold] {stats}")
        return stats
    finally:
        silver_session.close()
        gold_session.close()


def run_embed() -> dict:
    gold_session = get_session("gold")
    try:
        stats = build_embeddings(gold_session)
        print(f"[embed] {stats}")
        return stats
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="lake-literature medallion pipeline")
    parser.add_argument("--stage", choices=STAGES, default="all", help="pipeline stage to run")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    run(args.stage)


if __name__ == "__main__":
    main()
