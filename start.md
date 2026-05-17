# Startup Guide — Alternative Data Platform (ADP)

End-to-end instructions to get this tool running from a clean machine. Targets
**Windows 11 + Docker Desktop + PowerShell** (the environment this repo is
developed on). Follow the sections in order the first time; later you only need
**§6 Daily run**.

---

## 1. What you are starting

A 6-layer pipeline for Indian-equity alternative data:

```
SOURCES ─▶ INGEST ─▶ BRONZE (raw, MinIO) ─▶ SILVER (normalized, Postgres)
        ─▶ GOLD (point-in-time feature store) ─▶ SIGNALS ─▶ BACKTEST
        ─▶ DELIVERY (FastAPI + Grafana)
```

Only the **POSOCO** (national power demand) source is wired end-to-end; the
other five are stubs (see `ROADMAP.md`). You can run the whole platform
**offline** using a generated sample — no live website needed.

---

## 2. Prerequisites

| Requirement | Check | Notes |
|-------------|-------|-------|
| Docker Desktop | `docker version` | Must be **running** before any step. Backs Postgres/MinIO/Prefect/Grafana. |
| Python 3.11+ | `python --version` | `pyproject.toml` requires `>=3.11`. |
| Git | `git --version` | Repo already cloned at `C:\Users\Dharun\Desktop\dq`. |
| PowerShell | (default shell) | All commands below are PowerShell syntax. |

Free local ports: **5432** (Postgres), **9000/9001** (MinIO),
**4200** (Prefect), **6379** (Redis), **8000** (API), **3000** (Grafana).

---

## 3. One-time setup

Run from the repo root (`C:\Users\Dharun\Desktop\dq`):

```powershell
# 3.1 Environment file (already present, but ensure it exists)
copy .env.example .env

# 3.2 Start infrastructure containers
docker compose up -d                 # db, minio, prefect, redis, api, grafana
docker compose ps                    # confirm db + minio are "healthy"

# 3.3 Python environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"              # installs the `adp` CLI + dev tools

# 3.4 Initialize the database + object store
python tasks.py init                 # alembic migrate + seed universe + create bronze bucket
```

`python tasks.py init` is idempotent — safe to re-run. It runs three steps you
can also run individually: `migrate`, `seed`, `bucket`.

> **Minimal infra:** if you only need the offline slice you can start just the
> stateful services: `docker compose up -d db minio`.

---

## 4. First run — offline end-to-end (recommended)

This proves the full pipeline with **no live-site dependency**. Generates
~2.5 years of synthetic POSOCO data, then ingests → features → backtests.

```powershell
# 4.1 Generate the sample dataset
python scripts/gen_sample_posoco.py --start 2023-01-01 --end 2025-05-10 --out data/posoco_sample

# 4.2 Point the source at the local sample (note: backslash path on Windows)
$env:ADP_POSOCO_LOCAL_DIR = "data\posoco_sample"

# 4.3 Run the slice — either via the Prefect flow…
python -m flows.posoco_flow --start 2024-06-01 --end 2025-05-01

#     …or step-by-step via the CLI:
adp ingest posoco --start 2024-06-01 --end 2025-05-01
adp features posoco --start 2024-06-01 --end 2025-05-01
adp backtest --factor posoco_industrial_yoy --start 2024-08-01 --end 2025-05-01
```

A successful backtest prints a summary line. The numbers are positive **by
construction of the sample generator** — this validates plumbing, not edge.

---

## 5. Live POSOCO (optional, only when you need real data)

1. Leave `ADP_POSOCO_LOCAL_DIR` **unset** (open a fresh shell or
   `Remove-Item Env:ADP_POSOCO_LOCAL_DIR`).
2. Verify `ADP_POSOCO_REPORT_URL_TEMPLATE` in `.env` still matches the current
   Grid-India site. This is the **one acknowledged spot needing live
   verification** — the URL/PDF layout changes occasionally. Parser is isolated
   in `src/adp/sources/posoco/parser.py` and also accepts CSV, so a site change
   is usually an `.env` edit, not a code change.
3. Run the same `adp ingest/features/backtest` commands as §4.

---

## 6. Daily run (after setup is done once)

```powershell
docker compose up -d                 # ensure containers are up
.\.venv\Scripts\Activate.ps1         # activate the venv
$env:ADP_POSOCO_LOCAL_DIR = "data\posoco_sample"   # offline mode (skip for live)
python -m flows.posoco_flow --start <START> --end <END>
```

---

## 7. Service endpoints

| Service | URL | Credentials |
|---------|-----|-------------|
| **Dashboard** | **http://127.0.0.1:8000** | — start here; the human-facing UI |
| API (Swagger) | http://127.0.0.1:8000/docs | — (see §8 localhost note) |
| MinIO console | http://localhost:9001 | `minioadmin` / `minioadmin` |
| Prefect UI | http://localhost:4200 | — |
| Grafana | http://localhost:3000 | anonymous enabled; admin `admin` / `admin` |

### Applying code or dashboard changes (important)

The `api` container **copies `src/` into its image at build time** — it has no
live source mount. So `docker compose up -d` keeps serving the *old* code/UI
until you rebuild. **This applies to every change inside `src/`**, including:

- Python code — e.g. API endpoints in `src/adp/api/main.py`, or anything in
  `src/adp/**` (sources, features, backtest, core).
- Dashboard files — `src/adp/api/static/` (`index.html`, `styles.css`,
  `app.js`).

Any such change requires rebuilding just that one service before it takes
effect:

```powershell
docker compose up -d --build api
```

What the command does:

| part | meaning |
|------|---------|
| `docker compose` | drive the services defined in `docker-compose.yml` |
| `up -d` | (re)create + start containers, detached (background) |
| `--build` | rebuild the image first instead of reusing the cached one |
| `api` | only the `api` service — leaves db / minio / prefect untouched |

For a fast edit→refresh loop while developing, skip Docker for the app and run
it directly (auto-reloads on save, no rebuild needed):

```powershell
uvicorn adp.api.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## 8. Troubleshooting (known gotchas — these cost real debugging time)

- **API unreachable at `localhost:8000`** → Windows resolves `localhost` to
  IPv6 `::1` but uvicorn binds IPv4. Use **`http://127.0.0.1:8000`**.
- **Dashboard / API returns `{"detail":"Not Found"}` or stale behaviour after
  a code change** → the container is running an old image. Rebuild it — see
  **§7 → "Applying code or dashboard changes"**.
- **YoY features come out empty** for a short date window → the feature
  lookback (`adp.features.compute._LOOKBACK`, currently 430d) must cover
  365 + rolling window + slack. Request a wider `--start`/`--end` range
  (the §4 example deliberately ingests from 2024-06 but backtests from 2024-08).
- **`db`/`minio` not healthy** → `docker compose ps`; wait for healthchecks,
  then re-run `python tasks.py init`.
- **`adp: command not found`** → the venv isn't activated or
  `pip install -e ".[dev]"` didn't run. Re-do §3.3.
- **Path not found for the sample** → on Windows use a backslash path:
  `$env:ADP_POSOCO_LOCAL_DIR = "data\posoco_sample"`.

---

## 9. Verify the install is green

```powershell
pytest -q                            # pure tests always run; DB tests auto-skip without Postgres
ruff check src tests                 # lint
adp sources                          # lists registered data sources
```

> **Safe by design:** pytest uses a separate **`adp_test`** database
> (auto-created and migrated by `tests/conftest.py`). It never touches the dev
> `adp` DB, so running tests will not wipe a verification run.

---

## 10. CLI quick reference

| Command | Purpose |
|---------|---------|
| `adp sources` | List registered data sources |
| `adp ingest <source> --start --end [--force]` | Ingest a date range → Silver (idempotent) |
| `adp features <source> --start --end` | Compute Gold features from Silver |
| `adp backtest --factor <f> --start --end` | Run the PIT-correct backtest |
| `python tasks.py {init\|migrate\|seed\|bucket}` | DB / object-store setup |
| `python -m flows.posoco_flow --start --end` | Run the full POSOCO slice as one flow |

For adding a new data source, see **`ROADMAP.md`** → "How to add ANY source".
