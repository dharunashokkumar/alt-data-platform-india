"""GST e-way bill source — monthly state/commodity volume + value.

Signal thesis (ROADMAP source #2): e-way bills are generated for every
consignment moved; monthly HSN-commodity bill *count* and *value* are a
near-real-time proxy for goods movement / industrial throughput. Honest
granularity is industry/sector (HSN -> industry -> sector), never single-stock,
so this is a sector-basket factor — the same documented ceiling as POSOCO.

Cadence: monthly. GSTN releases month M's statistics ~12 days into M+1, so
``published_date = month_end + ADP_GST_PUBLICATION_LAG_DAYS`` — the PIT layer
can then never leak a month before it was public.

Shape is a copy of the POSOCO reference plugin: discover/fetch/parse, register.
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
from adp.sources.gst.parser import parse as parse_gst

log = get_logger(__name__)


@register
class GstSource(DataSource):
    name = "gst"
    version = "v1"

    def discover(self, date: dt.date) -> DiscoveredArtifact | None:
        # Monthly: only the 1st of a month yields an artifact. Daily iteration
        # over a range therefore ingests each month exactly once; every other
        # day is a no-op, identical to POSOCO returning None when nothing.
        if not is_month_start(date):
            return None

        s = get_settings()
        published = published_date(date, s.gst_publication_lag_days)
        stem = f"gst_{date.year:04d}-{date.month:02d}"

        if s.gst_local_dir:
            base = pathlib.Path(s.gst_local_dir)
            for ext in ("xlsx", "pdf", "csv"):
                p = base / f"{stem}.{ext}"
                if p.exists():
                    return DiscoveredArtifact(
                        filename=p.name,
                        published_date=published,
                        locator=str(p),
                    )
            log.info("gst_local_missing", month=stem, dir=str(base))
            return None

        url = fmt_month(s.gst_report_url_template, date)
        ext = url.rsplit(".", 1)[-1].lower()
        ext = ext if ext in ("xlsx", "pdf", "csv") else "xlsx"
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
        return parse_gst(ref, raw)
