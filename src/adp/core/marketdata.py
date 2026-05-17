"""Market data provider contract + a free default implementation.

The backtest needs prices but prices are NOT the platform's edge, so this is a
swap-in seam: today a free yfinance provider, tomorrow a paid vendor — without
touching the backtester. (idea.md: realistic costs/slippage matter more than
the price feed itself.)
"""

from __future__ import annotations

import abc
import datetime as dt
from functools import lru_cache

import pandas as pd

from adp.core.config import get_settings
from adp.core.logging import get_logger

log = get_logger(__name__)


class MarketDataProvider(abc.ABC):
    @abc.abstractmethod
    def daily_prices(
        self, tickers: list[str], start: dt.date, end: dt.date
    ) -> pd.DataFrame:
        """Return tidy frame: columns [date, ticker, close] (adjusted close)."""


class YFinanceProvider(MarketDataProvider):
    """NSE tickers map to the `<TICKER>.NS` Yahoo symbol."""

    def daily_prices(
        self, tickers: list[str], start: dt.date, end: dt.date
    ) -> pd.DataFrame:
        import yfinance as yf

        symbols = [f"{t}.NS" for t in tickers]
        raw = yf.download(
            symbols,
            start=start.isoformat(),
            end=(end + dt.timedelta(days=1)).isoformat(),
            auto_adjust=True,
            progress=False,
            group_by="ticker",
        )
        frames = []
        for t, sym in zip(tickers, symbols, strict=True):
            try:
                col = raw[sym]["Close"] if len(symbols) > 1 else raw["Close"]
            except (KeyError, TypeError):
                continue
            f = col.rename("close").reset_index()
            f.columns = ["date", "close"]
            f["ticker"] = t
            frames.append(f)
        if not frames:
            return pd.DataFrame(columns=["date", "ticker", "close"])
        out = pd.concat(frames, ignore_index=True)
        out["date"] = pd.to_datetime(out["date"]).dt.date
        return out.dropna(subset=["close"])


_PROVIDERS: dict[str, type[MarketDataProvider]] = {
    "yfinance": YFinanceProvider,
}


@lru_cache
def get_provider() -> MarketDataProvider:
    name = get_settings().market_data_provider
    if name not in _PROVIDERS:
        raise KeyError(f"unknown market data provider '{name}'")
    return _PROVIDERS[name]()
