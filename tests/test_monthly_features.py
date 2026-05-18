"""Monthly feature math (pure pandas) + a DB-guarded end-to-end recipe check."""

import datetime as dt

import pandas as pd

from adp.features._monthly import (
    build_feature_rows,
    monthly_panel,
    to_long,
    yoy_and_accel,
)
from tests.conftest import requires_db


def _silver(rows):
    """Build a frame shaped like compute._load_silver output (dims already
    normalized into `industry`/`metric` columns)."""
    return pd.DataFrame(
        rows,
        columns=[
            "observation_date",
            "published_date",
            "industry",
            "metric",
            "value",
            "unit",
        ],
    )


def test_yoy_and_accel_math():
    idx = pd.date_range("2023-01-31", periods=15, freq="ME")
    # Metals grows 1% MoM from 100; level lets us check YoY ~ (1.01^12 - 1)
    vals = [100 * (1.01**i) for i in range(15)]
    wide = pd.DataFrame({"Metals": vals}, index=idx)

    yoy, accel = yoy_and_accel(wide)
    # first 12 YoY are NaN (no value 12 months prior)
    assert yoy["Metals"].iloc[:12].isna().all()
    assert round(yoy["Metals"].iloc[12], 6) == round(1.01**12 - 1, 6)
    # constant 1% MoM growth -> acceleration ~ 0 once defined
    assert abs(accel["Metals"].iloc[3]) < 1e-9


def test_monthly_panel_and_to_long_pit_filter():
    rows = []
    for i in range(14):
        m = (pd.Timestamp("2023-01-31") + pd.offsets.MonthEnd(i)).date()
        pub = m + dt.timedelta(days=3)
        rows.append((m, pub, "Metals", "freight_mt", 100 + i, "MT"))
        rows.append((m, pub, "Cement", "freight_mt", 50 + i, "MT"))
    wide, pub = monthly_panel(_silver(rows), "freight_mt")

    assert list(wide.columns) == ["Cement", "Metals"]
    assert len(wide) == 14
    yoy, _ = yoy_and_accel(wide)

    long = to_long(yoy, pub, dt.date(2024, 1, 1), dt.date(2024, 3, 31))
    # only feature_dates in-range, only non-NaN (>=12 months of history)
    assert long
    for _industry, fdate, _val, published in long:
        assert dt.date(2024, 1, 1) <= fdate <= dt.date(2024, 3, 31)
        assert published == fdate + dt.timedelta(days=3)  # PIT lag preserved


@requires_db
def test_build_feature_rows_end_to_end(clean_db):
    from sqlalchemy import text

    from adp.core.db import session_scope

    with session_scope() as s:
        s.execute(
            text(
                "INSERT INTO universe (ticker, name, sector, state) VALUES "
                "('TATASTEEL','Tata Steel','Metals','Jharkhand'),"
                "('JSWSTEEL','JSW Steel','Metals','Karnataka')"
            )
        )

    rows = []
    for i in range(14):
        m = (pd.Timestamp("2023-01-31") + pd.offsets.MonthEnd(i)).date()
        pub = m + dt.timedelta(days=3)
        rows.append((m, pub, "Metals", "freight_mt", 100 * (1.02**i), "MT"))
    silver = _silver(rows)

    out = build_feature_rows(
        silver,
        dt.date(2024, 1, 1),
        dt.date(2024, 3, 31),
        source="railway",
        value_metric="freight_mt",
        prefix="railway_freight",
    )
    names = {r.feature_name for r in out}
    assert names == {
        "railway_freight_yoy",
        "railway_freight_mom_accel",
        "railway_freight_composite",
    }
    tickers = {r.ticker for r in out}
    assert tickers == {"TATASTEEL", "JSWSTEEL"}  # both Metals tickers
    assert all(r.published_date <= r.feature_date + dt.timedelta(days=3) for r in out)
    assert all(r.source == "railway" for r in out)
