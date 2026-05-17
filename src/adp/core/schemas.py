"""Shared data contracts across the medallion layers.

These Pydantic models are the *interface* between layers. A new data source
only has to produce `SilverRecord`s; a new feature only has to produce
`FeatureRow`s. Everything downstream (signals, backtest, API) is source-agnostic.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class BronzeRef(BaseModel):
    """Pointer to an immutable raw payload in the lake."""

    source: str
    date: dt.date
    filename: str
    uri: str
    fetched_at: dt.datetime
    # When the underlying data was actually published by the provider. Drives
    # point-in-time correctness downstream.
    published_date: dt.date


class SilverRecord(BaseModel):
    """One normalized observation parsed out of a Bronze payload.

    Source-specific dimensions go in `dimensions` (e.g. {"state": "Maharashtra",
    "metric": "peak_demand_met_mw"}). This keeps the silver table generic so
    adding a source needs no schema migration.
    """

    source: str
    observation_date: dt.date
    published_date: dt.date
    dimensions: dict[str, str]
    value: float
    unit: str
    bronze_uri: str
    ingested_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC)
    )


class FeatureRow(BaseModel):
    """A point-in-time-correct feature value (Gold layer).

    The triplet (feature_date, as_of_date, published_date) is what makes
    backtests honest:
      - feature_date   : the date the feature describes
      - published_date : when the underlying data became publicly known
      - as_of_date     : when our pipeline computed/ingested it
    A backtest at time T may only read rows with published_date <= T.
    """

    ticker: str
    feature_date: dt.date
    feature_name: str
    value: float
    as_of_date: dt.date
    published_date: dt.date
    source: str
    source_version: str = "v1"


class SignalRow(BaseModel):
    """A combined trading signal for a ticker on a date."""

    ticker: str
    signal_date: dt.date
    signal_name: str
    score: float
    published_date: dt.date
    model_version: str = "v1"
