"""Point-in-time feature access — the anti-lookahead guard.

idea.md flags this as the #1 amateur mistake: backtesting with data that
wasn't published yet. Every read here is filtered by `published_date <= as_of`
and, when multiple vintages of the same (ticker, feature_date, feature_name)
exist, returns the latest one *that was known at as_of*. There is no API to
read the future.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
from sqlalchemy import text

from adp.core.db import get_engine, session_scope
from adp.core.schemas import FeatureRow
from adp.core.sql import upsert_features


def write_features(rows: list[FeatureRow]) -> int:
    if not rows:
        return 0
    with session_scope() as s:
        upsert_features(s, rows)
    return len(rows)


_PIT_QUERY = text(
    """
    SELECT DISTINCT ON (ticker, feature_date, feature_name)
        ticker, feature_date, feature_name, value,
        as_of_date, published_date, source, source_version
    FROM features
    WHERE published_date <= :as_of
      AND (:feature_name IS NULL OR feature_name = :feature_name)
      AND (:start IS NULL OR feature_date >= :start)
      AND (:end   IS NULL OR feature_date <= :end)
    ORDER BY ticker, feature_date, feature_name, published_date DESC
    """
)


def read_features(
    as_of: dt.date,
    *,
    feature_name: str | None = None,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> pd.DataFrame:
    """Return only features publicly known on or before `as_of`.

    For each (ticker, feature_date, feature_name) the most recently *published*
    vintage with published_date <= as_of wins (DISTINCT ON ... ORDER BY
    published_date DESC).
    """
    with get_engine().connect() as conn:
        df = pd.read_sql_query(
            _PIT_QUERY,
            conn,
            params={
                "as_of": as_of,
                "feature_name": feature_name,
                "start": start,
                "end": end,
            },
        )
    return df
