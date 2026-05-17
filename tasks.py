"""Developer task runner.

    python tasks.py init      # migrate + seed + create bronze bucket
    python tasks.py migrate   # alembic upgrade head
    python tasks.py seed      # load infra/db/seed/seed.sql
    python tasks.py bucket    # ensure MinIO bronze bucket exists

Kept dependency-light on purpose; assumes `pip install -e .` has run.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).parent


def migrate() -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        cwd=ROOT,
    )


def seed() -> None:
    from sqlalchemy import text

    from adp.core.db import session_scope

    sql = (ROOT / "infra/db/seed/seed.sql").read_text(encoding="utf-8")
    with session_scope() as s:
        s.execute(text(sql))
    print("seeded universe")


def bucket() -> None:
    from adp.core.storage import ensure_bucket

    ensure_bucket()
    print("bronze bucket ready")


def init() -> None:
    migrate()
    seed()
    bucket()
    print("init complete")


_COMMANDS = {"migrate": migrate, "seed": seed, "bucket": bucket, "init": init}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "init"
    if cmd not in _COMMANDS:
        print(f"unknown task '{cmd}'. options: {list(_COMMANDS)}")
        raise SystemExit(2)
    _COMMANDS[cmd]()
