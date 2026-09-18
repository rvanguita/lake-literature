"""Shared fixtures: one in-memory SQLite session per medallion layer.

Each layer is already an independent SQLAlchemy `Base`/database in the real
system (see `src/lake_research_map/db/*_models.py`), and nothing in the
transform code is MySQL-specific, so a separate in-memory SQLite engine per
layer is a faithful, dependency-free stand-in for the real MySQL databases.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lake_research_map.db import bronze_models, gold_models, raw_models, silver_models


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
