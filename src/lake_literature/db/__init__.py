"""Database layer: one SQLAlchemy `Base`/model module per medallion layer."""

from __future__ import annotations

import datetime as dt


def utcnow() -> dt.datetime:
    """Naive UTC timestamp, for `DateTime` column defaults.

    `datetime.utcnow()` is deprecated since Python 3.12. Its replacement,
    `datetime.now(dt.UTC)`, returns an *aware* datetime, which these columns
    (plain `DateTime`, MySQL `DATETIME`) don't carry -- so it's stripped back to
    naive UTC, keeping every stored value's meaning exactly as before.
    """
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)
