"""Indian Railways freight feature recipe (ROADMAP source #3).

Signal: monthly commodity *loading* (million tonnes) leads the earnings of the
consuming industry by 1-2 quarters (coal->power, iron ore/steel->metals,
cement->cement, POL->energy). Features: YoY growth, MoM acceleration, composite
z-blend — attributed to each consuming sector's tickers.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from adp.core.schemas import FeatureRow
from adp.features._monthly import build_feature_rows
from adp.features.compute import feature_recipe
from adp.sources.railway.parser import FREIGHT_MT


@feature_recipe("railway")
def build(
    silver: pd.DataFrame, start: dt.date, end: dt.date
) -> list[FeatureRow]:
    return build_feature_rows(
        silver,
        start,
        end,
        source="railway",
        value_metric=FREIGHT_MT,
        prefix="railway_freight",
    )
