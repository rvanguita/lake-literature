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


def create_tables() -> None:
    for layer, module in _MODELS.items():
        engine = get_engine(layer)
        module.Base.metadata.create_all(engine)
        if layer in ("bronze", "silver", "gold"):
            inspector = inspect(engine)
            if inspector.has_table("lit_articles"):
                cols = {c["name"] for c in inspector.get_columns("lit_articles")}
                if "reference_count" not in cols:
                    with engine.connect() as conn:
                        conn.execute(
                            text("ALTER TABLE `lit_articles` ADD COLUMN `reference_count` INT NULL")
                        )
                        conn.commit()
                if layer == "gold" and "sources" not in cols:
                    with engine.connect() as conn:
                        conn.execute(
                            text("ALTER TABLE `lit_articles` ADD COLUMN `sources` JSON NULL")
                        )
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
