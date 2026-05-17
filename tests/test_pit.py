"""The most important test: backtests must never see unpublished data."""

import datetime as dt

from adp.core.pit import read_features, write_features
from adp.core.schemas import FeatureRow
from tests.conftest import requires_db


@requires_db
def test_read_features_hides_unpublished_and_picks_latest_vintage(clean_db):
    fd = dt.date(2025, 3, 31)

    # March data describing fd, published 2025-04-15.
    v1 = FeatureRow(
        ticker="ULTRACEMCO",
        feature_date=fd,
        feature_name="posoco_industrial_yoy",
        value=0.10,
        as_of_date=dt.date(2025, 4, 15),
        published_date=dt.date(2025, 4, 15),
        source="posoco",
    )
    # A revised vintage for the SAME feature_date, published later.
    v2 = v1.model_copy(
        update={"value": 0.12, "published_date": dt.date(2025, 4, 20)}
    )
    write_features([v1, v2])

    # As of 2025-04-01 nothing is public yet -> empty (NO look-ahead).
    assert read_features(dt.date(2025, 4, 1)).empty

    # As of 2025-04-16 only the first vintage is known.
    df = read_features(dt.date(2025, 4, 16))
    assert len(df) == 1
    assert float(df.iloc[0]["value"]) == 0.10

    # As of 2025-04-21 the revised vintage supersedes it.
    df2 = read_features(dt.date(2025, 4, 21))
    assert len(df2) == 1
    assert float(df2.iloc[0]["value"]) == 0.12
