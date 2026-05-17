"""Bronze raw-data lake client (MinIO / S3 compatible).

Layout convention (immutable, date-partitioned):

    s3://<bronze_bucket>/<source>/dt=YYYY-MM-DD/<filename>

Raw payloads are never mutated. Re-ingesting the same date overwrites the same
key, keeping the lake idempotent and backfill-safe.
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from adp.core.config import get_settings
from adp.core.logging import get_logger

log = get_logger(__name__)


@lru_cache
def _client() -> BaseClient:
    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint_url,
        aws_access_key_id=s.s3_access_key,
        aws_secret_access_key=s.s3_secret_key,
        region_name=s.s3_region,
    )


def ensure_bucket() -> None:
    s = get_settings()
    c = _client()
    try:
        c.head_bucket(Bucket=s.bronze_bucket)
    except ClientError:
        c.create_bucket(Bucket=s.bronze_bucket)
        log.info("bronze_bucket_created", bucket=s.bronze_bucket)


def bronze_key(source: str, date: dt.date, filename: str) -> str:
    return f"{source}/dt={date.isoformat()}/{filename}"


def put_bronze(source: str, date: dt.date, filename: str, data: bytes) -> str:
    """Store a raw payload, return its s3 URI."""
    ensure_bucket()
    s = get_settings()
    key = bronze_key(source, date, filename)
    _client().put_object(Bucket=s.bronze_bucket, Key=key, Body=data)
    uri = f"s3://{s.bronze_bucket}/{key}"
    log.info("bronze_put", uri=uri, bytes=len(data))
    return uri


def get_bronze(source: str, date: dt.date, filename: str) -> bytes:
    s = get_settings()
    key = bronze_key(source, date, filename)
    obj = _client().get_object(Bucket=s.bronze_bucket, Key=key)
    return obj["Body"].read()


def bronze_exists(source: str, date: dt.date, filename: str) -> bool:
    s = get_settings()
    try:
        _client().head_object(
            Bucket=s.bronze_bucket, Key=bronze_key(source, date, filename)
        )
        return True
    except ClientError:
        return False
