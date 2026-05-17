"""Skeleton DataSource. See idea.md for the 5 remaining sources to build here
(satellite, GST e-way bill, railway freight, ports, Naukri jobs) and ROADMAP.md
for the per-source gotchas and recommended order."""

from __future__ import annotations

import datetime as dt

from adp.core.base import DataSource, DiscoveredArtifact
from adp.core.registry import register
from adp.core.schemas import BronzeRef, SilverRecord


@register
class TemplateSource(DataSource):
    name = "_template"  # rename; must be unique
    version = "v1"

    def discover(self, date: dt.date) -> DiscoveredArtifact | None:
        # Locate the artifact for `date`; set published_date = when the data
        # actually became public (drives point-in-time correctness).
        raise NotImplementedError

    def fetch(self, artifact: DiscoveredArtifact) -> bytes:
        # Download/read the raw payload. Framework persists it to Bronze.
        raise NotImplementedError

    def parse(self, ref: BronzeRef, raw: bytes) -> list[SilverRecord]:
        # Normalize raw -> SilverRecords (source-specific dims go in
        # `dimensions`). Keep ALL fragile parsing in this file.
        raise NotImplementedError
