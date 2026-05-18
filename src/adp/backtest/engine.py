"""Long-short, monthly-rebalanced, PIT-correct backtest.

The non-negotiable rule (idea.md "Point-in-time correctness CRITICAL"): at
each rebalance date T the factor is read via `adp.core.pit.read_features(
as_of=T)`, which structurally cannot return anything published after T. There
is no code path that sees the future.

Cost model (idea.md): Indian round-trip ~0.1% (STT + brokerage + exchange) plus
slippage, charged on realized turnover.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd

from adp.core.logging import get_logger
from adp.core.marketdata import get_provider
from adp.core.pit import read_features
from adp.core.universe import tickers as universe_tickers

log = get_logger(__name__)

ROUND_TRIP_COST = 0.0010  # ~0.10% (one full in+out)
SLIPPAGE = 0.0005  # extra bps on traded notional
QUANTILE = 0.3  # long top 30%, short bottom 30%


@dataclass
class BacktestResult:
    factor: str
    returns: pd.Series  # net periodic returns indexed by rebalance date
    gross_returns: pd.Series
    ic: pd.DataFrame  # per-period IC (+ .attrs summary)
    n_rebalances: int

    def _ann(self, r: pd.Series) -> float:
        if r.empty:
            return float("nan")
        periods_per_year = 12.0
        return (1 + r).prod() ** (periods_per_year / len(r)) - 1

    def sharpe(self) -> float:
        r = self.returns
        if r.std(ddof=1) == 0 or r.empty:
            return float("nan")
        return float(r.mean() / r.std(ddof=1) * np.sqrt(12))

    def summary(self) -> str:
        ica = self.ic.attrs
        return (
            f"Backtest [{self.factor}]\n"
            f"  rebalances     : {self.n_rebalances}\n"
            f"  gross CAGR     : {self._ann(self.gross_returns):+.2%}\n"
            f"  net   CAGR     : {self._ann(self.returns):+.2%}\n"
            f"  net   Sharpe   : {self.sharpe():.2f}\n"
            f"  cum net return : {((1 + self.returns).prod() - 1):+.2%}\n"
            f"  mean IC        : {ica.get('mean_ic', float('nan')):.4f}\n"
            f"  IC t-stat      : {ica.get('t_stat', float('nan')):.2f}\n"
            f"  IC periods     : {ica.get('n_periods', 0)}"
        )


def _rebalance_dates(start: dt.date, end: dt.date) -> list[pd.Timestamp]:
    return list(pd.date_range(start, end, freq="MS"))


def _signal_on(as_of: dt.date, factor: str) -> pd.Series:
    """Latest-known factor value per ticker as of `as_of` (PIT-safe)."""
    df = read_features(as_of, feature_name=factor)
    if df.empty:
        return pd.Series(dtype=float)
    df = df.sort_values("feature_date")
    latest = df.groupby("ticker").tail(1)
    return latest.set_index("ticker")["value"]


def run_backtest(
    factor: str, start: dt.date, end: dt.date
) -> BacktestResult:
    tickers = universe_tickers()
    rebs = _rebalance_dates(start, end)
    if len(rebs) < 2:
        raise ValueError("need >= 2 monthly rebalance dates in range")

    # Honest empty-state: a factor with no rows known by `end` would otherwise
    # produce empty signals every rebalance and a misleading +0.00% / 0-period
    # scorecard. Fail loudly with an actionable message instead. (Skipping the
    # slow price fetch below when there is nothing to backtest is a bonus.)
    if read_features(end, feature_name=factor).empty:
        raise ValueError(
            f"no '{factor}' features have been ingested yet (nothing public "
            f"on or before {end.isoformat()}). Run the source pipeline first, "
            f"e.g. `adp ingest <source> --start … --end …` then "
            f"`adp features <source> --start … --end …`."
        )

    prov = get_provider()
    prices = prov.daily_prices(
        tickers, rebs[0].date(), (rebs[-1] + pd.Timedelta(days=5)).date()
    )
    if prices.empty:
        raise RuntimeError(
            "no prices from market data provider; check connectivity / "
            "ADP_MARKET_DATA_PROVIDER"
        )
    px = (
        prices.pivot_table(index="date", values="close", columns="ticker")
        .sort_index()
    )
    px.index = pd.to_datetime(px.index)
    # price on/just before each rebalance date
    px_reb = px.reindex(px.index.union(rebs)).ffill().reindex(rebs)

    gross, net, ic_rows = [], [], []
    prev_w = pd.Series(0.0, index=tickers)

    for i in range(len(rebs) - 1):
        t, t1 = rebs[i], rebs[i + 1]
        sig = _signal_on(t.date(), factor)
        sig = sig.reindex(tickers).dropna()
        if len(sig) < 5:
            gross.append(0.0)
            net.append(0.0)
            continue

        ranks = sig.rank(pct=True)
        longs = sig.index[ranks >= 1 - QUANTILE]
        shorts = sig.index[ranks <= QUANTILE]
        w = pd.Series(0.0, index=tickers)
        if len(longs):
            w[longs] = 0.5 / len(longs)
        if len(shorts):
            w[shorts] = -0.5 / len(shorts)

        fwd = (px_reb.loc[t1] / px_reb.loc[t] - 1.0).reindex(tickers)
        period_gross = float((w * fwd.fillna(0.0)).sum())

        turnover = (w - prev_w).abs().sum()
        cost = turnover * (ROUND_TRIP_COST / 2 + SLIPPAGE)
        prev_w = w

        gross.append(period_gross)
        net.append(period_gross - cost)

        valid = fwd.dropna()
        common = sig.index.intersection(valid.index)
        for tk in common:
            ic_rows.append(
                {
                    "feature_date": t.date(),
                    "ticker": tk,
                    "value": sig[tk],
                    "fwd_ret": valid[tk],
                }
            )

    idx = rebs[:-1]
    gross_s = pd.Series(gross, index=idx, name="gross")
    net_s = pd.Series(net, index=idx, name="net")

    from adp.signals.model import information_coefficient

    icdf = pd.DataFrame(ic_rows)
    if not icdf.empty:
        ic = information_coefficient(
            icdf[["feature_date", "ticker", "value"]],
            icdf[["feature_date", "ticker", "fwd_ret"]],
        )
    else:
        ic = pd.DataFrame(columns=["feature_date", "ic"])

    res = BacktestResult(factor, net_s, gross_s, ic, len(idx))
    log.info("backtest_done", factor=factor, sharpe=res.sharpe())
    return res
