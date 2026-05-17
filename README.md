# Alternative Data Platform — Indian Equities

Find information that moves stocks in the physical world *before* it hits
financial statements, structure it, and predict. Built as a **scalable
skeleton with hard layer contracts** plus one fully working vertical slice
(**POSOCO** power demand). Adding the other sources from `idea.md` is a
plug-in, not a rewrite — see **[ROADMAP.md](ROADMAP.md)**.

## Architecture

```
SOURCES ─▶ INGEST ─▶ BRONZE (raw, MinIO) ─▶ SILVER (normalized, Postgres)
        ─▶ GOLD (point-in-time feature store) ─▶ SIGNALS ─▶ BACKTEST
        ─▶ DELIVERY (FastAPI + Grafana)
```

| Layer | Module | Contract |
|-------|--------|----------|
| Ingestion | `adp.sources.*` | `DataSource` ABC (`adp.core.base`) |
| Storage | `adp.core.storage`, `silver_observations` | `BronzeRef` / `SilverRecord` |
| Feature store | `adp.core.pit`, `features` | `FeatureRow`, `published_date<=as_of` |
| Signals | `adp.signals` | `FactorModel`, `information_coefficient` |
| Backtest | `adp.backtest` | PIT reads only, Indian cost model |
| Delivery | `adp.api` | FastAPI; Grafana pipeline health |

**Point-in-time correctness is structural** (`idea.md`'s #1 rule): every
feature carries `(feature_date, published_date, as_of_date)` and every read
goes through `adp.core.pit.read_features(as_of)` — there is no API to see the
future.

## Quickstart (Windows / Docker Desktop)

```powershell
copy .env.example .env
docker compose up -d                       # db, minio, prefect, redis, api, grafana
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python tasks.py init                       # migrate + seed universe + bronze bucket

# Offline end-to-end (no live site dependency) — generate ~2.5y sample, run slice:
python scripts/gen_sample_posoco.py --start 2023-01-01 --end 2025-05-10 --out data/posoco_sample
$env:ADP_POSOCO_LOCAL_DIR="data/posoco_sample"
python -m flows.posoco_flow --start 2024-06-01 --end 2025-05-01
adp backtest --factor posoco_industrial_yoy --start 2024-08-01 --end 2025-05-01
```

Live POSOCO instead of the sample: leave `ADP_POSOCO_LOCAL_DIR` unset and
verify `ADP_POSOCO_REPORT_URL_TEMPLATE` against the current Grid-India site
(this is the one acknowledged spot needing live verification — see ROADMAP).

Dashboard (start here): **`http://127.0.0.1:8000`** — a clean, self-explaining
UI for signals, backtests and the universe, served by the API itself.

Services: API `http://127.0.0.1:8000/docs` · MinIO `:9001` · Prefect `:4200`
· Grafana `:3000` (anon).

## Add a data source

See **[ROADMAP.md](ROADMAP.md)** → "How to add ANY source". The whole surface
is: copy `src/adp/sources/_template`, implement 3 methods, add a feature
recipe. Nothing downstream changes.

## Tests

```powershell
pytest -q          # pure tests always run; DB tests auto-skip without Postgres
ruff check src tests
```
