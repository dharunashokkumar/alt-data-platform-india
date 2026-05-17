"""POSOCO feature recipe.

Signal thesis (idea.md §4): state industrial power demand is a near-real-time
proxy for industrial activity. Feature = YoY growth of the trailing 28-day mean
"energy met" for a state, attributed to companies whose primary
manufacturing/HQ state is that state.

Granularity caveat (idea.md): POSOCO is honest only at state level, so this is
a state/sector-basket factor, not a single-stock alpha. That limitation is
intentional and documented, not hidden.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from adp.core.schemas import FeatureRow
from adp.core.universe import state_to_tickers
from adp.features.compute import feature_recipe
from adp.sources.posoco.parser import ENERGY_MET_MU

FEATURE_NAME = "posoco_industrial_yoy"
_ROLL = 28
_YOY_LAG = 365


@feature_recipe("posoco")
def build(
    silver: pd.DataFrame, start: dt.date, end: dt.date
) -> list[FeatureRow]:
    df = silver[silver["metric"] == ENERGY_MET_MU].copy()
    if df.empty:
        return []
    df["observation_date"] = pd.to_datetime(df["observation_date"])

    # published_date per (state, date): the data became public next morning.
    pub = (
        df.groupby(["state", "observation_date"])["published_date"]
        .max()
        .to_dict()
    )

    wide = (
        df.pivot_table(
            index="observation_date",
            columns="state",
            values="value",
            aggfunc="mean",
        )
        .sort_index()
        .asfreq("D")
    )
    roll = wide.rolling(_ROLL, min_periods=max(7, _ROLL // 2)).mean()
    yoy = roll / roll.shift(_YOY_LAG) - 1.0

    s2t = state_to_tickers()
    today = dt.date.today()
    rows: list[FeatureRow] = []
    mask = (yoy.index.date >= start) & (yoy.index.date <= end)
    for ts, srow in yoy.loc[mask].iterrows():
        fdate = ts.date()
        for state, val in srow.items():
            if pd.isna(val) or state not in s2t:
                continue
            published = pub.get((state, ts))
            if published is None:
                continue
            for ticker in s2t[state]:
                rows.append(
                    FeatureRow(
                        ticker=ticker,
                        feature_date=fdate,
                        feature_name=FEATURE_NAME,
                        value=float(val),
                        as_of_date=today,
                        published_date=published,
                        source="posoco",
                        source_version="v1",
                    )
                )
    return rows
