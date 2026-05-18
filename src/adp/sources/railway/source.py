"""Indian Railways freight source — monthly commodity-wise loading + revenue.

Signal thesis (ROADMAP source #3): rail is the backbone for bulk movement in
India. Monthly commodity loadings — coal -> thermal power, iron ore -> steel,
cement -> cement cos, POL -> OMC — lead reported earnings by 1-2 quarters and
are genuinely underexploited (US funds watch AAR weekly; no India equivalent).
Honest granularity is the consuming industry/sector (commodity -> industry ->
sector), the same documented basket ceiling as POSOCO.

Cadence: monthly. The Ministry of Railways releases month M's figures within
~3 days of month end, so ``published_date = month_end +
ADP_RAILWAY_PUBLICATION_LAG_DAYS`` keeps the PIT layer honest.
"""

from __future__ import annotations

import datetime as dt
import pathlib

import requests

from adp.core.base import DataSource, DiscoveredArtifact
from adp.core.config import get_settings
from adp.core.logging import get_logger
from adp.core.registry import register
from adp.core.schemas import BronzeRef, SilverRecord
from adp.sources._periodic import fmt_month, is_month_start, published_date
from adp.sources.railway.parser import parse as parse_railway

log = get_logger(__name__)


@register
class RailwaySource(DataSource):
    name = "railway"
    version = "v1"

    def discover(self, date: dt.date) -> DiscoveredArtifact | None:
        if not is_month_start(date):
            return None

        s = get_settings()
        published = published_date(date, s.railway_publication_lag_days)
        stem = f"railway_{date.year:04d}-{date.month:02d}"

        if s.railway_local_dir:
            base = pathlib.Path(s.railway_local_dir)
            for ext in ("pdf", "xlsx", "csv"):
                p = base / f"{stem}.{ext}"
                if p.exists():
                    return DiscoveredArtifact(
                        filename=p.name,
                        published_date=published,
                        locator=str(p),
                    )
            log.info("railway_local_missing", month=stem, dir=str(base))
            return None

        url = fmt_month(s.railway_report_url_template, date)
        ext = url.rsplit(".", 1)[-1].lower()
        ext = ext if ext in ("pdf", "xlsx", "csv") else "pdf"
        return DiscoveredArtifact(
            filename=f"{stem}.{ext}",
            published_date=published,
            locator=url,
        )

    def fetch(self, artifact: DiscoveredArtifact) -> bytes:
        loc = artifact.locator
        if loc.startswith(("http://", "https://")):
            resp = requests.get(loc, timeout=90)
            resp.raise_for_status()
            return resp.content
        return pathlib.Path(loc).read_bytes()

    def parse(self, ref: BronzeRef, raw: bytes) -> list[SilverRecord]:
        return parse_railway(ref, raw)
