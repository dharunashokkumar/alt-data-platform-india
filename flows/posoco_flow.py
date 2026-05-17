"""Prefect orchestration for POSOCO — the pattern every source reuses.

Idempotent + retry-safe + backfill-capable: re-running any date range is
safe (Bronze reuse + silver/feature upserts). A new source gets the same
guarantees by copying this flow and swapping the source name.

Run without a Prefect server:
    python -m flows.posoco_flow --start 2025-04-01 --end 2025-04-07
Deploy the daily schedule:
    python -m flows.posoco_flow --serve
"""

from __future__ import annotations

import argparse
import datetime as dt

from prefect import flow, task

from adp.core.logging import get_logger
from adp.core.registry import get_source
from adp.features import compute as features

log = get_logger("flows.posoco")


def _dates(start: dt.date, end: dt.date) -> list[dt.date]:
    return [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]


@task(retries=3, retry_delay_seconds=30)
def ingest_day(date: dt.date, force: bool) -> int:
    return get_source("posoco").run_ingest(date, force=force)


@task(retries=2, retry_delay_seconds=15)
def build_features(start: dt.date, end: dt.date) -> int:
    return features.run("posoco", start, end)


@flow(name="posoco-pipeline")
def posoco_pipeline(
    start: str, end: str | None = None, force: bool = False
) -> dict:
    sd = dt.date.fromisoformat(start)
    ed = dt.date.fromisoformat(end) if end else sd
    silver_rows = sum(ingest_day(d, force) for d in _dates(sd, ed))
    feat_rows = build_features(sd, ed)
    result = {"silver_rows": silver_rows, "feature_rows": feat_rows}
    log.info("posoco_pipeline_done", **result)
    return result


def _yesterday() -> str:
    return (dt.date.today() - dt.timedelta(days=1)).isoformat()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=_yesterday())
    ap.add_argument("--end", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument(
        "--serve", action="store_true", help="serve daily 06:30 IST schedule"
    )
    a = ap.parse_args()
    if a.serve:
        posoco_pipeline.serve(
            name="posoco-daily",
            cron="0 1 * * *",  # 01:00 UTC ~= 06:30 IST, after PSP publish
            parameters={"start": _yesterday()},
        )
    else:
        print(posoco_pipeline(start=a.start, end=a.end, force=a.force))
