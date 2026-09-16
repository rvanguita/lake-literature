"""Create the single medallion database (`medalhao`) on the MySQL server if
it doesn't exist yet, then create every layer's tables in it.

Usage:
    uv run python -m lake_literature.db.bootstrap
"""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from lake_literature.config import get_settings
from lake_literature.db import bronze_models, gold_models, raw_models, silver_models
from lake_literature.db.engines import get_engine

_MODELS = {
    "raw": raw_models,
    "bronze": bronze_models,
    "silver": silver_models,
    "gold": gold_models,
}

_ARTICLES_TABLE = {
    "bronze": "lit_articles_bronze",
    "silver": "lit_articles_silver",
    "gold": "lit_articles_gold",
}


def create_databases() -> None:
    settings = get_settings()
    server_engine = create_engine(settings.server_url(), future=True)
    with server_engine.connect() as conn:
        conn.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS `{settings.database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )
        conn.commit()
    server_engine.dispose()


def create_tables() -> None:
    for layer, module in _MODELS.items():
        engine = get_engine(layer)
        module.Base.metadata.create_all(engine)
        if layer in ("bronze", "silver", "gold"):
            table = _ARTICLES_TABLE[layer]
            inspector = inspect(engine)
            if inspector.has_table(table):
                cols = {c["name"] for c in inspector.get_columns(table)}
                if "reference_count" not in cols:
                    with engine.connect() as conn:
                        conn.execute(
                            text(f"ALTER TABLE `{table}` ADD COLUMN `reference_count` INT NULL")
                        )
                        conn.commit()
                if layer == "gold" and "sources" not in cols:
                    with engine.connect() as conn:
                        conn.execute(text(f"ALTER TABLE `{table}` ADD COLUMN `sources` JSON NULL"))
                        conn.commit()


def bootstrap() -> None:
    create_databases()
    create_tables()


def main() -> None:
    bootstrap()
    settings = get_settings()
    print(f"Bootstrapped database: {settings.database}")


if __name__ == "__main__":
    main()
