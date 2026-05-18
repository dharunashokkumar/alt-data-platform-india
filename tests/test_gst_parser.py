import datetime as dt
import pathlib

from adp.core.schemas import BronzeRef
from adp.sources.gst.parser import EWAY_COUNT, EWAY_VALUE_CR, parse

FIX = pathlib.Path(__file__).parent / "fixtures" / "gst_2025-03.csv"


def _ref(obs: dt.date, pub: dt.date) -> BronzeRef:
    return BronzeRef(
        source="gst",
        date=obs,
        filename="gst_2025-03.csv",
        uri="s3://bronze/gst/gst_2025-03.csv",
        fetched_at=dt.datetime.now(dt.UTC),
        published_date=pub,
    )


def test_gst_csv_maps_hsn_to_sector_and_aggregates():
    raw = FIX.read_bytes()
    # ingest trigger = month-start; data describes that whole month
    recs = parse(_ref(dt.date(2025, 3, 1), dt.date(2025, 4, 12)), raw)

    industries = {r.dimensions["industry"] for r in recs}
    # Iron+Steel and Articles-of-iron both -> Metals; Cotton -> dropped
    assert industries == {
        "Metals",
        "Cement",
        "Auto",
        "Energy",
        "Fertilizers",
        "Chemicals",
    }
    metrics = {r.dimensions["metric"] for r in recs}
    assert metrics == {EWAY_COUNT, EWAY_VALUE_CR}

    # observation_date is the month-end the figure describes
    assert all(r.observation_date == dt.date(2025, 3, 31) for r in recs)
    assert all(r.published_date == dt.date(2025, 4, 12) for r in recs)

    # Metals value = 142500.50 + 38200.10 (two HSN rows aggregated)
    metals_val = next(
        r.value
        for r in recs
        if r.dimensions == {"industry": "Metals", "metric": EWAY_VALUE_CR}
    )
    assert round(metals_val, 2) == 180700.60


def test_gst_unknown_label_dropped():
    raw = b"commodity,eway_count,eway_value_cr\nUnobtanium widgets,5,9\n"
    recs = parse(_ref(dt.date(2025, 3, 1), dt.date(2025, 4, 12)), raw)
    assert recs == []
