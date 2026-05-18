"""Cross-source multi-factor research (ROADMAP Phase 3 seed).

Blends the three per-source composites — POSOCO industrial demand, GST e-way
bill, railway freight — into one score with the existing linear `FactorModel`
and reports the combined Information Coefficient against forward monthly
returns. PIT-correct: every feature read goes through `read_features(as_of=T)`.

No backtest-engine change is needed: each composite is independently
backtestable today via `adp backtest --factor <name>`; this module just shows
the *combined* signal is additive.

    python -m adp.research.multifactor --start 2024-01-01 --end 2025-04-01
"""

from __future__ import annotations

import argparse
import datetime as dt

import pandas as pd

from adp.core.marketdata import get_provider
from adp.core.pit import read_features
from adp.core.universe import tickers as universe_tickers
from adp.signals.model import FactorModel, information_coefficient

COMPOSITES = {
    "posoco_industrial_yoy": 1.0,
    "gst_eway_composite": 1.0,
    "railway_freight_composite": 1.0,
}


def _panel(as_of: dt.date) -> pd.DataFrame:
    frames = []
    for name in COMPOSITES:
        df = read_features(as_of, feature_name=name)
        if not df.empty:
            frames.append(df[["feature_date", "ticker", "feature_name", "value"]])
    if not frames:
        return pd.DataFrame(
            columns=["feature_date", "ticker", "feature_name", "value"]
        )
    out = pd.concat(frames, ignore_index=True)
    out["feature_date"] = pd.to_datetime(out["feature_date"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    a = ap.parse_args()
    start = dt.date.fromisoformat(a.start)
    end = dt.date.fromisoformat(a.end)

    panel = _panel(end)
    if panel.empty:
        print("no composite features found — build features for all 3 sources first")
        return

    scores = FactorModel(COMPOSITES).score(panel)  # [feature_date, ticker, score]
    scores = scores[
        (scores["feature_date"].dt.date >= start)
        & (scores["feature_date"].dt.date <= end)
    ]
    if scores.empty:
        print("no scored rows in range")
        return

    prov = get_provider()
    tks = universe_tickers()
    px = prov.daily_prices(tks, start, end + dt.timedelta(days=40))
    if px.empty:
        print("no market data — check ADP_MARKET_DATA_PROVIDER / connectivity")
        return
    wide = (
        px.pivot_table(index="date", values="close", columns="ticker")
        .sort_index()
    )
    wide.index = pd.to_datetime(wide.index)

    # forward 1-month return from each feature_date
    rebs = sorted(scores["feature_date"].unique())
    px_m = wide.reindex(wide.index.union(rebs)).ffill().reindex(rebs)
    fwd = (px_m.shift(-1) / px_m - 1.0).stack().rename("fwd_ret").reset_index()
    fwd.columns = ["feature_date", "ticker", "fwd_ret"]

    feats = scores.rename(columns={"score": "value"})[
        ["feature_date", "ticker", "value"]
    ]
    ic = information_coefficient(feats, fwd)
    at = ic.attrs
    print("Combined multi-factor (equal-weight z-blend of 3 composites)")
    print(f"  periods   : {at.get('n_periods', 0)}")
    print(f"  mean IC   : {at.get('mean_ic', float('nan')):.4f}")
    print(f"  IC IR     : {at.get('ic_ir', float('nan')):.3f}")
    print(f"  IC t-stat : {at.get('t_stat', float('nan')):.2f}")


if __name__ == "__main__":
    main()
