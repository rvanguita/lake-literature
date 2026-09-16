"""SQLAlchemy engine/session factories.

All four medallion layers share one MySQL database (`medalhao`); `layer` is
kept as a parameter purely for call-site readability and typo-safety (see
`LAYERS`), not because it selects a different engine.
"""

from __future__ import annotations

from functools import cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from lake_literature.config import LAYERS, get_settings


@cache
def _shared_engine() -> Engine:
    settings = get_settings()
    return create_engine(settings.database_url(), pool_pre_ping=True, future=True)


def get_engine(layer: str) -> Engine:
    if layer not in LAYERS:
        raise ValueError(f"unknown layer {layer!r}, expected one of {LAYERS}")
    return _shared_engine()


def get_session(layer: str) -> Session:
    Session_ = sessionmaker(bind=get_engine(layer), future=True)
    return Session_()
