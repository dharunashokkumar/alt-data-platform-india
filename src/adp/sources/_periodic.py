"""Shared date plumbing for *monthly* sources (GST e-way bill, railway freight).

POSOCO is daily; these are monthly. The framework's `run_ingest(date)` is still
called per-day by the CLI/Prefect drivers, so a monthly source simply returns an
artifact only on the first day of a month and `None` on every other day — the
exact same "return None when there is nothing for this date" contract POSOCO
uses. One ingest per month, no core changes.

Keep this to date math only; all fragile *parsing* stays in each source's
`parser.py` (the layout-drift firewall).
"""

from __future__ import annotations

import calendar
import datetime as dt


def is_month_start(date: dt.date) -> bool:
    """The trigger day. Daily iteration over a range hits this once per month."""
    return date.day == 1


def month_end(date: dt.date) -> dt.date:
    """Last calendar day of `date`'s month — the observation_date a monthly
    figure describes (the data is for the whole month)."""
    last = calendar.monthrange(date.year, date.month)[1]
    return dt.date(date.year, date.month, last)


def published_date(date: dt.date, lag_days: int) -> dt.date:
    """When the month's figure actually became public: provider releases it
    `lag_days` after month end. Drives point-in-time correctness."""
    return month_end(date) + dt.timedelta(days=lag_days)


def fmt_month(template: str, date: dt.date) -> str:
    """Fill {yyyy} {mm} {yyyymm} placeholders in a discovery URL template."""
    return template.format(
        yyyy=f"{date.year:04d}",
        mm=f"{date.month:02d}",
        yyyymm=f"{date.year:04d}{date.month:02d}",
    )
