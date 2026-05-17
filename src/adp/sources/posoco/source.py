"""POSOCO / Grid-India daily power-supply source — the REFERENCE plugin.

Every future source (satellite, GST, railway, ports, jobs) is a copy of this
shape: implement discover/fetch/parse, decorate with @register, done.

Publication lag: the PSP report describing day D is published the morning of
D+1. We therefore set ``published_date = observation_date + 1 day`` so the
point-in-time layer can never leak same-day data into a backtest.
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
from adp.sources.posoco.parser import parse as parse_psp

log = get_logger(__name__)

PUBLICATION_LAG = dt.timedelta(days=1)


def _fmt(template: str, d: dt.date) -> str:
    return template.format(
        yyyy=f"{d.year:04d}",
        mm=f"{d.month:02d}",
        dd=f"{d.day:02d}",
        ddmmyyyy=d.strftime("%d-%m-%Y"),
        ddmmyy=d.strftime("%d%m%y"),
    )


@register
class PosocoSource(DataSource):
    name = "posoco"
    version = "v1"

    def discover(self, date: dt.date) -> DiscoveredArtifact | None:
        s = get_settings()
        published = date + PUBLICATION_LAG

        # Offline / archive path takes precedence so dev + CI are deterministic.
        if s.posoco_local_dir:
            base = pathlib.Path(s.posoco_local_dir)
            for ext in ("csv", "pdf"):
                p = base / f"posoco_{date.isoformat()}.{ext}"
                if p.exists():
                    return DiscoveredArtifact(
                        filename=p.name,
                        published_date=published,
                        locator=str(p),
                    )
            log.info("posoco_local_missing", date=str(date), dir=str(base))
            return None

        url = _fmt(s.posoco_report_url_template, date)
        return DiscoveredArtifact(
            filename=f"posoco_{date.isoformat()}.pdf",
            published_date=published,
            locator=url,
        )

    def fetch(self, artifact: DiscoveredArtifact) -> bytes:
        loc = artifact.locator
        if loc.startswith(("http://", "https://")):
            resp = requests.get(loc, timeout=60)
            resp.raise_for_status()
            return resp.content
        return pathlib.Path(loc).read_bytes()

    def parse(self, ref: BronzeRef, raw: bytes) -> list[SilverRecord]:
        return parse_psp(ref, raw)
