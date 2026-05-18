"""Shared monthly feature math for the GST and railway recipes.

POSOCO's recipe is daily (28-day rolling mean, 365-day YoY). Monthly sources
need their own, simpler primitives — kept here so both recipes share one
tested implementation and layout/PIT plumbing stays consistent:

  * YoY growth        : value / value 12 months ago - 1
  * MoM acceleration  : change in month-on-month growth (2nd difference of the
                        log-ish ratio) — captures inflection, not just level.

`compute._LOOKBACK` is 430 days, which covers the 12-month shift plus slack.
Everything here is pure pandas; no DB, no I/O — trivially unit-testable.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from adp.core.schemas import FeatureRow
from adp.core.universe import sector_to_tickers


def monthly_panel(
    silver: pd.DataFrame, metric: str
) -> tuple[pd.DataFrame, dict[tuple[str, pd.Timestamp], dt.date]]:
    """silver rows (from compute._load_silver, dims already normalized) ->
    (wide month-end x industry value matrix, published-date lookup).

    The silver `observation_date` is already the month it describes (set to
    month-end by the source parsers), so we only need to align to a clean
    month-end grid.
    """
    df = silver[silver["metric"] == metric].copy()
    if df.empty:
        return pd.DataFrame(), {}
    df["observation_date"] = pd.to_datetime(df["observation_date"])

    pub = (
        df.groupby(["industry", "observation_date"])["published_date"]
        .max()
        .to_dict()
    )
    wide = (
        df.pivot_table(
            index="observation_date",
            columns="industry",
            values="value",
            aggfunc="sum",
        )
        .sort_index()
        .resample("ME")
        .last()
    )
    return wide, pub


def yoy_and_accel(wide: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Wide (month-end x industry) values -> (YoY, MoM-acceleration) frames,
    same shape/index as `wide`."""
    if wide.empty:
        return wide, wide
    yoy = wide / wide.shift(12) - 1.0
    mom = wide / wide.shift(1) - 1.0
    accel = mom - mom.shift(1)
    return yoy, accel


def to_long(
    frame: pd.DataFrame,
    pub: dict[tuple[str, pd.Timestamp], dt.date],
    start: dt.date,
    end: dt.date,
) -> list[tuple[str, dt.date, float, dt.date]]:
    """(industry, feature_date, value, published_date) tuples for non-NaN
    cells whose feature_date is in [start, end] and that have a known
    publication date. Used by both recipes to emit FeatureRows."""
    if frame.empty:
        return []
    mask = (frame.index.date >= start) & (frame.index.date <= end)
    out: list[tuple[str, dt.date, float, dt.date]] = []
    for ts, row in frame.loc[mask].iterrows():
        for industry, val in row.items():
            if pd.isna(val):
                continue
            published = pub.get((industry, ts))
            if published is None:
                continue
            out.append((industry, ts.date(), float(val), published))
    return out


def _zscore(s: pd.Series) -> pd.Series:
    sd = s.std(ddof=0)
    return (s - s.mean()) / sd if sd and not np.isnan(sd) else s * 0.0


def build_feature_rows(
    silver: pd.DataFrame,
    start: dt.date,
    end: dt.date,
    *,
    source: str,
    value_metric: str,
    prefix: str,
) -> list[FeatureRow]:
    """End-to-end recipe body shared by GST and railway.

    Emits three PIT-correct feature families per ticker, attributing each
    industry's score to every ticker whose `sector` == that industry:

      * ``{prefix}_yoy``        — 12-month growth of the monthly value metric
      * ``{prefix}_mom_accel``  — change in month-on-month growth
      * ``{prefix}_composite``  — cross-sectional z(yoy) + z(accel), the
        directly-backtestable per-source signal (also FactorModel-ready).

    Honest granularity is the sector basket (documented ceiling, like POSOCO):
    every ticker in a sector shares its industry's value.
    """
    wide, pub = monthly_panel(silver, value_metric)
    if wide.empty:
        return []
    yoy, accel = yoy_and_accel(wide)

    s2t = sector_to_tickers()
    today = dt.date.today()
    rows: list[FeatureRow] = []

    def _emit(frame: pd.DataFrame, fname: str) -> None:
        for industry, fdate, val, published in to_long(frame, pub, start, end):
            for ticker in s2t.get(industry, []):
                rows.append(
                    FeatureRow(
                        ticker=ticker,
                        feature_date=fdate,
                        feature_name=fname,
                        value=val,
                        as_of_date=today,
                        published_date=published,
                        source=source,
                        source_version="v1",
                    )
                )

    _emit(yoy, f"{prefix}_yoy")
    _emit(accel, f"{prefix}_mom_accel")

    # Composite: standardize yoy & accel cross-sectionally per month, sum.
    # Emit wherever the underlying YoY is defined. A legitimately-zero
    # composite is a *neutral* cross-sectional reading (e.g. a thin month with
    # one sector, or a sector exactly at the mean), NOT missing data — skipping
    # zeros would silently empty the whole `*_composite` factor whenever the
    # cross-section is thin. "No signal" is YoY-is-NaN, nothing else.
    mask = (yoy.index.date >= start) & (yoy.index.date <= end)
    for ts in yoy.index[mask]:
        z = _zscore(yoy.loc[ts]).fillna(0.0) + _zscore(accel.loc[ts]).fillna(
            0.0
        )
        for industry, val in z.items():
            if pd.isna(yoy.loc[ts, industry]):
                continue  # no 12-month base yet -> genuinely no signal
            published = pub.get((industry, ts))
            if published is None:
                continue
            for ticker in s2t.get(industry, []):
                rows.append(
                    FeatureRow(
                        ticker=ticker,
                        feature_date=ts.date(),
                        feature_name=f"{prefix}_composite",
                        value=float(val),
                        as_of_date=today,
                        published_date=published,
                        source=source,
                        source_version="v1",
                    )
                )
    return rows
