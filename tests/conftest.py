"""Shared fixtures: one in-memory SQLite session per medallion layer.

In the real system all four layers share one MySQL database (`medalhao`,
see `src/lake_literature/db/engines.py`), but each layer still has its own
SQLAlchemy `Base` (`src/lake_literature/db/*_models.py`) with its own table
names, so a separate in-memory SQLite engine per layer remains a faithful,
dependency-free stand-in -- nothing in the transform code is MySQL-specific,
and sessions are already passed around independently per layer in
`pipeline.py`.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lake_literature.db import bronze_models, gold_models, raw_models, silver_models


def _sqlite_session(base):
    engine = create_engine("sqlite:///:memory:", future=True)
    base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


@pytest.fixture
def raw_session():
    session = _sqlite_session(raw_models.Base)
    yield session
    session.close()


@pytest.fixture
def bronze_session():
    session = _sqlite_session(bronze_models.Base)
    yield session
    session.close()


@pytest.fixture
def silver_session():
    session = _sqlite_session(silver_models.Base)
    yield session
    session.close()


@pytest.fixture
def gold_session():
    session = _sqlite_session(gold_models.Base)
    yield session
    session.close()
