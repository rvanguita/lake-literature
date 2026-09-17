"""Create the four medallion databases (`raw`/`bronze`/`silver`/`gold`) on
the MySQL server if they don't exist yet, then create every layer's tables.

Note: `raw`/`bronze`/`silver` are typically already present on the server
(shared with unrelated tables from other projects) -- `CREATE DATABASE IF
NOT EXISTS` is a no-op for them. `gold` is created fresh.

Usage:
    uv run python -m lake_literature.db.bootstrap
"""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from lake_literature.config import LAYERS, get_settings
from lake_literature.db import bronze_models, gold_models, raw_models, silver_models
from lake_literature.db.engines import get_engine

_MODELS = {
    "raw": raw_models,
    "bronze": bronze_models,
    "silver": silver_models,
    "gold": gold_models,
}


def create_databases() -> None:
    settings = get_settings()
    server_engine = create_engine(settings.server_url(), future=True)
    with server_engine.connect() as conn:
        for layer in LAYERS:
            db_name = settings.database_name(layer)
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
        conn.commit()
    server_engine.dispose()


# Additive migrations for `lit_articles`, applied where the column is missing.
# `create_all` only ever creates absent *tables*, so a column added to a model
# after a table already exists needs this. Every entry must be nullable and
# purely additive -- this runs unattended on every pipeline start, so it must
# never be able to drop or rewrite existing data.
_ARTICLE_COLUMNS: dict[str, tuple[str, tuple[str, ...]]] = {
    "reference_count": ("INT NULL", ("bronze", "silver", "gold")),
    "sources": ("JSON NULL", ("gold",)),
    # IEEE-only enrichment, see transform/bronze_articles.py.
    "countries": ("JSON NULL", ("bronze", "silver", "gold")),
    "online_date": ("DATE NULL", ("bronze", "silver", "gold")),
    "document_type": ("VARCHAR(128) NULL", ("bronze", "silver", "gold")),
    "license": ("VARCHAR(64) NULL", ("bronze", "silver", "gold")),
}


def create_tables() -> None:
    for layer, module in _MODELS.items():
        engine = get_engine(layer)
        module.Base.metadata.create_all(engine)

        inspector = inspect(engine)
        if not inspector.has_table("lit_articles"):
            continue
        existing = {c["name"] for c in inspector.get_columns("lit_articles")}
        missing = [
            (name, ddl)
            for name, (ddl, layers) in _ARTICLE_COLUMNS.items()
            if layer in layers and name not in existing
        ]
        if not missing:
            continue
        with engine.connect() as conn:
            for name, ddl in missing:
                conn.execute(text(f"ALTER TABLE `lit_articles` ADD COLUMN `{name}` {ddl}"))
            conn.commit()


def bootstrap() -> None:
    create_databases()
    create_tables()


def main() -> None:
    bootstrap()
    settings = get_settings()
    print("Bootstrapped databases:")
    for layer in LAYERS:
        print(f"  {settings.database_name(layer)}")


if __name__ == "__main__":
    main()
