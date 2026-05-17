"""Test isolation.

DB tests run against a DEDICATED `<db>_test` database that is created and
migrated on demand. Running pytest therefore never truncates or otherwise
touches the working/dev database. This is enforced before any `adp.*` import
so the cached Settings/engine pick up the test DSN.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

# --- redirect every DB connection to an isolated test database --------------
_BASE_DB = os.environ.get("ADP_PG_DB", "adp")
_TEST_DB = _BASE_DB if _BASE_DB.endswith("_test") else f"{_BASE_DB}_test"
os.environ["ADP_PG_DB"] = _TEST_DB


def _server_url(dbname: str) -> str:
    import sqlalchemy as sa

    from adp.core.config import get_settings

    s = get_settings()
    return sa.engine.URL.create(
        "postgresql+psycopg2",
        username=s.pg_user,
        password=s.pg_password,
        host=s.pg_host,
        port=s.pg_port,
        database=dbname,
    ).render_as_string(hide_password=False)


def _db_reachable() -> bool:
    try:
        import sqlalchemy as sa

        eng = sa.create_engine(_server_url("postgres"))
        with eng.connect() as c:
            c.execute(sa.text("SELECT 1"))
        return True
    except Exception:
        return False


def _ensure_test_db_migrated() -> bool:
    """Create <db>_test if absent and run migrations. Returns success."""
    try:
        import sqlalchemy as sa

        admin = sa.create_engine(
            _server_url("postgres"), isolation_level="AUTOCOMMIT"
        )
        with admin.connect() as c:
            exists = c.execute(
                sa.text("SELECT 1 FROM pg_database WHERE datname = :n"),
                {"n": _TEST_DB},
            ).scalar()
            if not exists:
                c.execute(sa.text(f'CREATE DATABASE "{_TEST_DB}"'))
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            check=True,
            capture_output=True,
        )
        return True
    except Exception as e:  # pragma: no cover - infra dependent
        print(f"[conftest] test DB setup skipped: {e}")
        return False


_DB_OK = _db_reachable() and _ensure_test_db_migrated()

requires_db = pytest.mark.skipif(
    not _DB_OK, reason="Postgres not reachable (run docker compose up -d db)"
)


@pytest.fixture
def clean_db():
    """Isolate a DB test by truncating the *test* DB tables (never dev)."""
    from sqlalchemy import text

    from adp.core.db import session_scope

    with session_scope() as s:
        s.execute(
            text(
                "TRUNCATE features, signals, silver_observations, universe "
                "RESTART IDENTITY"
            )
        )
    yield
