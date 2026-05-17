"""Source-agnostic feature computation driver + recipe registry."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

import pandas as pd
from sqlalchemy import text

from adp.core.db import get_engine
from adp.core.logging import get_logger
from adp.core.pit import write_features
from adp.core.schemas import FeatureRow

log = get_logger(__name__)

# recipe signature: (silver_df, start, end) -> list[FeatureRow]
Recipe = Callable[[pd.DataFrame, dt.date, dt.date], list[FeatureRow]]
_RECIPES: dict[str, Recipe] = {}

# Trailing history each recipe needs. Sized for the heaviest current feature:
# YoY (365d) on a 28d rolling mean + slack -> ~14 months.
_LOOKBACK = dt.timedelta(days=430)


def feature_recipe(source: str) -> Callable[[Recipe], Recipe]:
    def deco(fn: Recipe) -> Recipe:
        _RECIPES[source] = fn
        return fn

    return deco


def _load_silver(source: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    q = text(
        """
        SELECT observation_date, published_date, dimensions, value, unit
        FROM silver_observations
        WHERE source = :source
          AND observation_date BETWEEN :start AND :end
        """
    )
    with get_engine().connect() as conn:
        df = pd.read_sql_query(
            q, conn, params={"source": source, "start": start, "end": end}
        )
    if not df.empty:
        dims = pd.json_normalize(df.pop("dimensions"))
        df = pd.concat([df.reset_index(drop=True), dims], axis=1)
    return df


def run(source: str, start: dt.date, end: dt.date) -> int:
    if source not in _RECIPES:
        raise KeyError(
            f"no feature recipe for '{source}'. have: {sorted(_RECIPES)}"
        )
    silver = _load_silver(source, start - _LOOKBACK, end)
    if silver.empty:
        log.warning("no_silver", source=source, start=str(start), end=str(end))
        return 0
    rows = _RECIPES[source](silver, start, end)
    n = write_features(rows)
    log.info("features_written", source=source, rows=n)
    return n
