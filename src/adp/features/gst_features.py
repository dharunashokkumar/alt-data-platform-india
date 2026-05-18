"""GST e-way bill feature recipe (ROADMAP source #2).

Signal: monthly e-way-bill *value* per HSN-commodity is a goods-movement /
industrial-throughput proxy. We use value (₹cr) as the primary metric (less
noisy than raw count). Features: YoY growth, MoM acceleration, and a composite
z-blend — attributed to the consuming sector's tickers (basket granularity is
the honest ceiling, exactly as documented for POSOCO).
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from adp.core.schemas import FeatureRow
from adp.features._monthly import build_feature_rows
from adp.features.compute import feature_recipe
from adp.sources.gst.parser import EWAY_VALUE_CR


@feature_recipe("gst")
def build(
    silver: pd.DataFrame, start: dt.date, end: dt.date
) -> list[FeatureRow]:
    return build_feature_rows(
        silver,
        start,
        end,
        source="gst",
        value_metric=EWAY_VALUE_CR,
        prefix="gst_eway",
    )
