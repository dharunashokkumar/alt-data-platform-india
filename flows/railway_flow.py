"""Prefect orchestration for Indian Railways freight — monthly.

Same idempotent + retry-safe + backfill-capable guarantees as the POSOCO flow.

    python -m flows.railway_flow --start 2024-01-01 --end 2025-04-01
    python -m flows.railway_flow --serve            # monthly schedule
"""

from __future__ import annotations

import argparse
import datetime as dt

from prefect import flow, task

from adp.core.logging import get_logger
from adp.core.registry import get_source
from adp.features import compute as features

log = get_logger("flows.railway")


def _dates(start: dt.date, end: dt.date) -> list[dt.date]:
    return [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]


@task(retries=3, retry_delay_seconds=60)
def ingest_day(date: dt.date, force: bool) -> int:
    return get_source("railway").run_ingest(date, force=force)


@task(retries=2, retry_delay_seconds=30)
def build_features(start: dt.date, end: dt.date) -> int:
    return features.run("railway", start, end)


@flow(name="railway-pipeline")
def railway_pipeline(
    start: str, end: str | None = None, force: bool = False
) -> dict:
    sd = dt.date.fromisoformat(start)
    ed = dt.date.fromisoformat(end) if end else sd
    silver_rows = sum(ingest_day(d, force) for d in _dates(sd, ed))
    feat_rows = build_features(sd, ed)
    result = {"silver_rows": silver_rows, "feature_rows": feat_rows}
    log.info("railway_pipeline_done", **result)
    return result


def _first_of_this_month() -> str:
    return dt.date.today().replace(day=1).isoformat()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=_first_of_this_month())
    ap.add_argument("--end", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument(
        "--serve", action="store_true", help="serve monthly schedule"
    )
    a = ap.parse_args()
    if a.serve:
        railway_pipeline.serve(
            name="railway-monthly",
            # 5th 02:00 UTC: Ministry of Railways month-M figures out (~3d lag).
            cron="0 2 5 * *",
            parameters={"start": _first_of_this_month()},
        )
    else:
        print(railway_pipeline(start=a.start, end=a.end, force=a.force))
