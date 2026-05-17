"""The tradable universe + entity mappings.

Universe and state/sector mappings live in the `universe` table (seeded from
infra/db/seed). Everything is config/data driven — no ticker is hardcoded in
logic, so expanding coverage is a seed change, not a code change.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from adp.core.db import get_engine


def load_universe() -> pd.DataFrame:
    """Columns: ticker, name, sector, state."""
    with get_engine().connect() as conn:
        return pd.read_sql_query(
            text("SELECT ticker, name, sector, state FROM universe"), conn
        )


def tickers() -> list[str]:
    return load_universe()["ticker"].tolist()


def tickers_for_state(state: str) -> list[str]:
    u = load_universe()
    return u.loc[u["state"] == state, "ticker"].tolist()


def state_to_tickers() -> dict[str, list[str]]:
    u = load_universe()
    return {
        st: g["ticker"].tolist() for st, g in u.groupby("state") if st
    }
