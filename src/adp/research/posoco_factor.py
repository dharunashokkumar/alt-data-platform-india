"""POSOCO factor research entry point.

Runs the PIT backtest and, if alphalens-reloaded is installed, prints a factor
tearsheet. Designed to be `%run` from a Jupyter notebook or run as a script:

    python -m adp.research.posoco_factor --start 2024-01-01 --end 2025-05-01
"""

from __future__ import annotations

import argparse
import datetime as dt

from adp.backtest.engine import run_backtest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--factor", default="posoco_industrial_yoy")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    a = ap.parse_args()

    res = run_backtest(
        a.factor,
        dt.date.fromisoformat(a.start),
        dt.date.fromisoformat(a.end),
    )
    print(res.summary())

    try:
        import alphalens  # noqa: F401

        print(
            "\n[alphalens installed] build a full tearsheet from "
            "adp.core.pit.read_features + price data in a notebook."
        )
    except ImportError:
        print(
            "\n[hint] pip install '.[research]' for alphalens factor tearsheets."
        )


if __name__ == "__main__":
    main()
