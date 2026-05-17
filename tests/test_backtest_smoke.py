import datetime as dt

import pandas as pd
from sqlalchemy import text

from adp.core.db import session_scope
from adp.core.marketdata import MarketDataProvider
from adp.core.pit import write_features
from adp.core.schemas import FeatureRow
from tests.conftest import requires_db


class _FakeProvider(MarketDataProvider):
    def daily_prices(self, tickers, start, end):
        dates = pd.date_range(start, end, freq="D")
        rows = []
        for i, t in enumerate(tickers):
            for j, d in enumerate(dates):
                rows.append(
                    {"date": d.date(), "ticker": t, "close": 100 + i * 5 + j}
                )
        return pd.DataFrame(rows)


@requires_db
def test_backtest_runs_pit_correct(clean_db, monkeypatch):
    with session_scope() as s:
        s.execute(text("TRUNCATE universe"))
        s.execute(
            text(
                "INSERT INTO universe(ticker,name,sector,state) VALUES "
                "('AAA','A','Cement','Gujarat'),"
                "('BBB','B','Cement','Maharashtra'),"
                "('CCC','C','Metals','Karnataka'),"
                "('DDD','D','Metals','Rajasthan'),"
                "('EEE','E','Auto','Haryana'),"
                "('FFF','F','Auto','Tamil Nadu')"
            )
        )

    rows = []
    for m in range(1, 7):
        fd = dt.date(2025, m, 1)
        pub = fd + dt.timedelta(days=1)  # realistic publish lag
        for k, tk in enumerate(["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]):
            rows.append(
                FeatureRow(
                    ticker=tk,
                    feature_date=fd,
                    feature_name="posoco_industrial_yoy",
                    value=(k - 2.5) * 0.01 + m * 0.001,
                    as_of_date=pub,
                    published_date=pub,
                    source="posoco",
                )
            )
    write_features(rows)

    import adp.backtest.engine as eng

    monkeypatch.setattr(eng, "get_provider", lambda: _FakeProvider())

    res = eng.run_backtest(
        "posoco_industrial_yoy", dt.date(2025, 1, 1), dt.date(2025, 6, 1)
    )
    assert res.n_rebalances >= 3
    assert not res.returns.empty
    # summary must render without error
    assert "Backtest [posoco_industrial_yoy]" in res.summary()
