"""Programmatic access to the platform.

Every read goes through the point-in-time layer, so even the API cannot serve
look-ahead data: callers pass `as_of` and get only what was public then.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import FastAPI, Query
from sqlalchemy import text

from adp import __version__
from adp.core.db import get_engine
from adp.core.pit import read_features
from adp.core.registry import list_sources

app = FastAPI(title="Alternative Data Platform — Indian Equities", version=__version__)


@app.get("/health")
def health() -> dict:
    try:
        with get_engine().connect() as c:
            c.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db": db_ok, "version": __version__}


@app.get("/sources")
def sources() -> dict:
    return {"sources": list_sources()}


@app.get("/features")
def features(
    as_of: Annotated[
        dt.date, Query(description="point-in-time cutoff (YYYY-MM-DD)")
    ],
    feature_name: str | None = None,
    ticker: str | None = None,
    limit: Annotated[int, Query(le=5000)] = 500,
) -> dict:
    df = read_features(as_of, feature_name=feature_name)
    if ticker:
        df = df[df["ticker"] == ticker]
    df = df.sort_values("feature_date").tail(limit)
    return {
        "as_of": as_of.isoformat(),
        "count": len(df),
        "rows": df.to_dict(orient="records"),
    }


@app.get("/signals")
def signals(
    factor: str = "posoco_industrial_yoy",
    as_of: dt.date | None = None,
) -> dict:
    """Latest factor value per ticker, point-in-time as of `as_of`
    (defaults to today)."""
    cutoff = as_of or dt.date.today()
    df = read_features(cutoff, feature_name=factor)
    if df.empty:
        return {"factor": factor, "as_of": cutoff.isoformat(), "signals": []}
    latest = df.sort_values("feature_date").groupby("ticker").tail(1)
    latest = latest.sort_values("value", ascending=False)
    return {
        "factor": factor,
        "as_of": cutoff.isoformat(),
        "signals": latest[["ticker", "feature_date", "value"]].to_dict(
            orient="records"
        ),
    }
