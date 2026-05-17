"""Programmatic access to the platform.

Every read goes through the point-in-time layer, so even the API cannot serve
look-ahead data: callers pass `as_of` and get only what was public then.

The same FastAPI app also serves the human-facing dashboard (a static page at
``/``); the API paths below are unchanged and remain the documented contract.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Annotated

import pandas as pd
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from adp import __version__
from adp.core.db import get_engine
from adp.core.pit import read_features
from adp.core.registry import list_sources
from adp.core.universe import load_universe

app = FastAPI(title="Alternative Data Platform — Indian Equities", version=__version__)

_STATIC_DIR = Path(__file__).parent / "static"


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


@app.get("/universe")
def universe() -> dict:
    """The tradable universe with sector/state mapping (master data)."""
    try:
        df = load_universe()
    except Exception as e:  # DB not up / not seeded
        return {"count": 0, "rows": [], "error": str(e)}
    return {"count": len(df), "rows": df.to_dict(orient="records")}


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


@app.get("/backtest")
def backtest(
    factor: str = "posoco_industrial_yoy",
    start: dt.date = dt.date(2024, 8, 1),
    end: dt.date = dt.date(2025, 5, 1),
) -> dict:
    """Run the PIT-correct long/short backtest on demand and return its
    headline metrics, the cumulative equity curve, and per-period IC.

    Computes live (needs a populated `features` table and market-data
    connectivity for prices). On any failure it returns ``{"error": ...}``
    with HTTP 200 so the dashboard can show a clear message instead of a
    stack trace.
    """
    from adp.backtest.engine import run_backtest

    try:
        res = run_backtest(factor, start, end)
    except Exception as e:
        return {
            "factor": factor,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "error": str(e),
        }

    net_cum = (1 + res.returns).cumprod() - 1
    gross_cum = (1 + res.gross_returns).cumprod() - 1
    equity_curve = [
        {
            "date": pd.Timestamp(idx).date().isoformat(),
            "net_cum": float(net_cum.loc[idx]),
            "gross_cum": float(gross_cum.loc[idx]),
        }
        for idx in res.returns.index
    ]

    ica = res.ic.attrs
    ic_series = []
    if not res.ic.empty and "ic" in res.ic.columns:
        for _, r in res.ic.iterrows():
            ic_series.append(
                {
                    "feature_date": pd.Timestamp(r["feature_date"])
                    .date()
                    .isoformat(),
                    "ic": float(r["ic"]),
                }
            )

    def _f(x: float) -> float | None:
        return None if x != x else float(x)  # NaN -> null

    return {
        "factor": factor,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "metrics": {
            "gross_cagr": _f(res._ann(res.gross_returns)),
            "net_cagr": _f(res._ann(res.returns)),
            "sharpe": _f(res.sharpe()),
            "cum_net": _f(float((1 + res.returns).prod() - 1)),
            "mean_ic": _f(ica.get("mean_ic", float("nan"))),
            "ic_tstat": _f(ica.get("t_stat", float("nan"))),
            "ic_periods": int(ica.get("n_periods", 0)),
            "n_rebalances": res.n_rebalances,
        },
        "equity_curve": equity_curve,
        "ic_series": ic_series,
    }


# --- Human-facing dashboard (static, same-origin, no build step) ------------
# API routes are declared above so they always take precedence; the mount and
# index route below only serve the UI shell and its assets.

if _STATIC_DIR.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=str(_STATIC_DIR)),
        name="assets",
    )


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")
