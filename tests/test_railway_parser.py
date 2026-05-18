import datetime as dt
import pathlib

from adp.core.schemas import BronzeRef
from adp.sources.railway.parser import FREIGHT_MT, FREIGHT_REVENUE_CR, parse

FIX = pathlib.Path(__file__).parent / "fixtures" / "railway_2025-03.csv"


def _ref(obs: dt.date, pub: dt.date) -> BronzeRef:
    return BronzeRef(
        source="railway",
        date=obs,
        filename="railway_2025-03.csv",
        uri="s3://bronze/railway/railway_2025-03.csv",
        fetched_at=dt.datetime.now(dt.UTC),
        published_date=pub,
    )


def test_railway_csv_fans_commodities_to_consuming_industries():
    raw = FIX.read_bytes()
    recs = parse(_ref(dt.date(2025, 3, 1), dt.date(2025, 4, 3)), raw)

    industries = {r.dimensions["industry"] for r in recs}
    # Coal -> Power; coking coal/coke/iron ore/steel -> Metals; cement;
    # fertiliser; POL -> Energy; containers + foodgrains -> Logistics;
    # "Balance Other Goods" -> dropped
    assert industries == {
        "Power",
        "Metals",
        "Cement",
        "Fertilizers",
        "Energy",
        "Logistics",
    }
    metrics = {r.dimensions["metric"] for r in recs}
    assert metrics == {FREIGHT_MT, FREIGHT_REVENUE_CR}
    assert all(r.observation_date == dt.date(2025, 3, 31) for r in recs)
    assert all(r.published_date == dt.date(2025, 4, 3) for r in recs)

    metals_mt = next(
        r.value
        for r in recs
        if r.dimensions == {"industry": "Metals", "metric": FREIGHT_MT}
    )
    # 7.20 (coking) + 1.10 (coke) + 16.40 (iron ore) + 5.60 (steel)
    assert round(metals_mt, 2) == 30.30

    logistics_mt = next(
        r.value
        for r in recs
        if r.dimensions == {"industry": "Logistics", "metric": FREIGHT_MT}
    )
    assert round(logistics_mt, 2) == 12.40  # containers 7.90 + foodgrains 4.50


def test_plain_coal_is_power_not_metals():
    raw = b"commodity,freight_mt,freight_revenue_cr\nCoal,50,9000\n"
    recs = parse(_ref(dt.date(2025, 3, 1), dt.date(2025, 4, 3)), raw)
    assert {r.dimensions["industry"] for r in recs} == {"Power"}
