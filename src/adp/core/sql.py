"""Low-level table operations (idempotent upserts).

Tables are owned by Alembic migrations (infra/db). We deliberately use
SQLAlchemy Core text() + Postgres ON CONFLICT rather than ORM models so the
schema stays generic and adding a source needs no Python model changes.
"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from adp.core.schemas import FeatureRow, SignalRow, SilverRecord


def _obs_key(r: SilverRecord) -> str:
    dims = json.dumps(r.dimensions, sort_keys=True, separators=(",", ":"))
    raw = f"{r.source}|{r.observation_date.isoformat()}|{dims}"
    return hashlib.md5(raw.encode()).hexdigest()


_SILVER_UPSERT = text(
    """
    INSERT INTO silver_observations
        (obs_key, source, observation_date, published_date,
         dimensions, value, unit, bronze_uri, ingested_at)
    VALUES
        (:obs_key, :source, :observation_date, :published_date,
         CAST(:dimensions AS jsonb), :value, :unit, :bronze_uri, :ingested_at)
    ON CONFLICT (obs_key) DO UPDATE SET
        value        = EXCLUDED.value,
        published_date = EXCLUDED.published_date,
        bronze_uri   = EXCLUDED.bronze_uri,
        ingested_at  = EXCLUDED.ingested_at
    """
)


def upsert_silver(session: Session, records: list[SilverRecord]) -> None:
    for r in records:
        session.execute(
            _SILVER_UPSERT,
            {
                "obs_key": _obs_key(r),
                "source": r.source,
                "observation_date": r.observation_date,
                "published_date": r.published_date,
                "dimensions": json.dumps(r.dimensions, sort_keys=True),
                "value": r.value,
                "unit": r.unit,
                "bronze_uri": r.bronze_uri,
                "ingested_at": r.ingested_at,
            },
        )


_FEATURE_UPSERT = text(
    """
    INSERT INTO features
        (ticker, feature_date, feature_name, value,
         as_of_date, published_date, source, source_version, ingested_at)
    VALUES
        (:ticker, :feature_date, :feature_name, :value,
         :as_of_date, :published_date, :source, :source_version, now())
    ON CONFLICT (ticker, feature_date, feature_name, published_date)
    DO UPDATE SET
        value       = EXCLUDED.value,
        as_of_date  = EXCLUDED.as_of_date,
        ingested_at = now()
    """
)


def upsert_features(session: Session, rows: list[FeatureRow]) -> None:
    for f in rows:
        session.execute(_FEATURE_UPSERT, f.model_dump())


_SIGNAL_UPSERT = text(
    """
    INSERT INTO signals
        (ticker, signal_date, signal_name, score,
         published_date, model_version, created_at)
    VALUES
        (:ticker, :signal_date, :signal_name, :score,
         :published_date, :model_version, now())
    ON CONFLICT (ticker, signal_date, signal_name, published_date)
    DO UPDATE SET score = EXCLUDED.score, created_at = now()
    """
)


def upsert_signals(session: Session, rows: list[SignalRow]) -> None:
    for sig in rows:
        session.execute(_SIGNAL_UPSERT, sig.model_dump())
