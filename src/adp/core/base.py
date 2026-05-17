"""The DataSource plugin contract.

THIS IS THE PRIMARY EXTENSIBILITY SEAM. Adding any of the remaining data
sources from idea.md (satellite, GST, railway, ports, jobs) means writing one
class that implements this ABC and registering it. Nothing downstream changes.

Lifecycle for a single date:

    discover(date)  -> DiscoveredArtifact  (where the raw data lives, when it
                                             was published)
    fetch(artifact) -> bytes               (download raw payload)
    [framework stores bytes -> Bronze]
    parse(BronzeRef, bytes) -> list[SilverRecord]   (raw -> normalized)

`run_ingest` wires these together with idempotency + Bronze persistence so
every source gets retry-safe, backfill-capable ingestion for free.
"""

from __future__ import annotations

import abc
import datetime as dt

from pydantic import BaseModel

from adp.core import storage
from adp.core.db import session_scope
from adp.core.logging import get_logger
from adp.core.schemas import BronzeRef, SilverRecord
from adp.core.sql import upsert_silver

log = get_logger(__name__)


class DiscoveredArtifact(BaseModel):
    """What/where the raw data for a date is, and when it was published."""

    filename: str
    published_date: dt.date
    # Opaque locator the concrete source understands (URL, S3 path, API id...).
    locator: str


class DataSource(abc.ABC):
    """Base class every source plugin implements."""

    #: stable short id, e.g. "posoco". Used as Bronze prefix + registry key.
    name: str
    #: bumped when parsing logic changes so features can be recomputed cleanly.
    version: str = "v1"

    @abc.abstractmethod
    def discover(self, date: dt.date) -> DiscoveredArtifact | None:
        """Locate the artifact for `date`. Return None if none exists yet."""

    @abc.abstractmethod
    def fetch(self, artifact: DiscoveredArtifact) -> bytes:
        """Download the raw payload for a discovered artifact."""

    @abc.abstractmethod
    def parse(self, ref: BronzeRef, raw: bytes) -> list[SilverRecord]:
        """Turn a raw Bronze payload into normalized SilverRecords."""

    # --- framework-provided orchestration (sources should not override) ---

    def run_ingest(self, date: dt.date, *, force: bool = False) -> int:
        """Idempotent ingest for one date. Returns silver rows written.

        Safe to re-run (backfill): existing Bronze is reused unless `force`,
        and silver writes are upserts.
        """
        artifact = self.discover(date)
        if artifact is None:
            log.info("no_artifact", source=self.name, date=str(date))
            return 0

        fetched_at = dt.datetime.now(dt.UTC)
        if force or not storage.bronze_exists(
            self.name, date, artifact.filename
        ):
            raw = self.fetch(artifact)
            uri = storage.put_bronze(self.name, date, artifact.filename, raw)
        else:
            raw = storage.get_bronze(self.name, date, artifact.filename)
            uri = (
                f"s3://{storage.get_settings().bronze_bucket}/"
                f"{storage.bronze_key(self.name, date, artifact.filename)}"
            )

        ref = BronzeRef(
            source=self.name,
            date=date,
            filename=artifact.filename,
            uri=uri,
            fetched_at=fetched_at,
            published_date=artifact.published_date,
        )
        records = self.parse(ref, raw)
        with session_scope() as s:
            upsert_silver(s, records)
        log.info(
            "ingest_done", source=self.name, date=str(date), rows=len(records)
        )
        return len(records)
