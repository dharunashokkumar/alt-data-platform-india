import datetime as dt

from adp.core.schemas import BronzeRef
from adp.sources.posoco.parser import ENERGY_MET_MU, PEAK_DEMAND_MW, parse


def _ref(obs: dt.date, pub: dt.date) -> BronzeRef:
    return BronzeRef(
        source="posoco",
        date=obs,
        filename="x.csv",
        uri="s3://bronze/posoco/x.csv",
        fetched_at=dt.datetime.now(dt.UTC),
        published_date=pub,
    )


def test_csv_parse_emits_records_with_canonical_states():
    csv = (
        "date,state,energy_met_mu,peak_demand_met_mw\n"
        "2025-04-01,Maharashtra,300.5,18000\n"
        "2025-04-01,Chattisgarh,120.0,6000\n"  # misspelling -> Chhattisgarh
        "2025-04-01,Atlantis,1.0,1.0\n"  # unknown -> dropped
    )
    recs = parse(_ref(dt.date(2025, 4, 1), dt.date(2025, 4, 2)), csv.encode())

    states = {r.dimensions["state"] for r in recs}
    assert states == {"Maharashtra", "Chhattisgarh"}
    metrics = {r.dimensions["metric"] for r in recs}
    assert metrics == {ENERGY_MET_MU, PEAK_DEMAND_MW}
    assert all(r.published_date == dt.date(2025, 4, 2) for r in recs)
