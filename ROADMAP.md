# ROADMAP — what's built, what's left

> This is the "**oh, I still need to add that**" memory doc. The platform is
> deliberately built as a *scalable skeleton + one deep vertical slice*
> (POSOCO). Every remaining source plugs into the **same proven contracts** —
> nothing below requires touching the core, signals, backtest, or API.

## How to add ANY source (the entire integration surface)

1. `cp -r src/adp/sources/_template src/adp/sources/<name>`
2. Implement `discover()` / `fetch()` / `parse()` in `source.py`, set `name`,
   decorate the class with `@register`. Put **all** fragile parsing in
   `parser.py` so layout drift is a one-file fix.
3. Add `from adp.sources import <name>` to `src/adp/sources/__init__.py`.
4. Add a feature recipe in `src/adp/features/<name>_features.py` decorated with
   `@feature_recipe("<name>")` (see `posoco_features.py` as the reference).
5. Run `adp ingest <name> --start ... --end ...` then `adp features <name> ...`.

Set `published_date` = when the data **actually became public** (not the
observation date). The point-in-time layer (`adp.core.pit`) does the rest;
no backtest can ever see unpublished data.

## Source status

| # | Source | Status | Cadence | Granularity | Key libs | Hardest part |
|---|--------|--------|---------|-------------|----------|--------------|
| 1 | **POSOCO power demand** | ✅ DONE (reference slice) | Daily | State | pdfplumber | Company mapping → state-level only |
| 2 | **GST e-way bill** | ✅ DONE | Monthly | Industry (HSN) | openpyxl, pdfplumber | Messy XLSX/PDF tables; HSN→industry→ticker map |
| 3 | **Indian Railways freight** | ✅ DONE | Monthly | Commodity | pdfplumber/camelot | PDF parse; commodity→consuming-industry map |
| 4 | Indian Ports / DGFT | ⬜ TODO | Monthly | Port / commodity | requests, bs4 | Per-port scraping; port→company map |
| 5 | Naukri / career-page jobs | ⬜ TODO | Daily/Weekly | Company | scrapy, playwright, spaCy | ToS/legal grey area; JS pages; dedupe |
| 6 | Satellite imagery | ⬜ TODO (hardest) | ~5-day | Plant | sentinelsat, rasterio, gdal, ultralytics | Cloud cover (monsoon); GPU; plant geocoords |

### Per-source notes (distilled from `idea.md`)

- **GST e-way bill** — GSTN monthly state/commodity volume+value PDFs. Build the
  `HSN → industry → ticker` map as seed data (extend `infra/db/seed/`). Signal:
  YoY growth, MoM acceleration. Aggregate only → industry/sector baskets.
- **Railway freight** — monthly commodity tonne-km. Coal loadings → thermal
  power; iron ore → steel; cement → cement cos. Genuinely underexploited (US
  funds watch AAR weekly; no India equivalent). RTI-able if needed.
- **Ports / DGFT** — IPA monthly + per-port sites (JNPT/Mundra/Chennai) for
  better granularity. Some ports ≈ single company (Mundra → ADANIPORTS) so this
  one *can* hit single-stock signals. POL imports → OMC refining margins.
- **Naukri / jobs** — career pages are the safest legal path; respect
  robots.txt, no auth-bypass. NLP skill extraction (hiring AI/ML = new
  direction). Strongest for IT services (INFY/TCS/WIPRO): hiring = capacity =
  revenue 2-3 quarters out. Add residential-proxy rotation only if scaling.
- **Satellite** — Sentinel-2 (free, 10m, 5-day) via Copernicus/AWS Open Data;
  Planet (paid, academic access) for 3m daily. Pipeline: plant polygons →
  weekly pull → SCL cloud mask → Sen2Cor → YOLOv8 vehicle count → 4-week
  rolling delta vs prior quarter. Sentinel-1 SAR sees through monsoon clouds
  but is harder to interpret. Inference fits RTX 3050; train on Colab/Kaggle.

## Platform phase roadmap

- [x] **Phase 0** — Scalable skeleton: contracts, medallion storage, PIT
      feature store, registry, docker-compose, migrations, CI.
- [x] **Phase 1** — POSOCO vertical slice end-to-end (ingest → bronze → silver
      → gold → signal → backtest → API → Grafana).
- [~] **Phase 2** — Add sources in ROI order: Railway freight ✅ → GST ✅ →
      **Ports → Jobs → Satellite** (cheap/structured first, satellite last).
      GST + Railway shipped as full vertical slices (monthly cadence, YoY +
      MoM-accel + composite features, flows, dashboard, multi-factor research).
- [ ] **Phase 3** — Multi-factor signals: cross-sectional Fama-MacBeth, IC
      decay analysis, ML combine (xgboost/lightgbm) with leak-free CV.
- [ ] **Phase 4** — Backtest realism: swap `MarketDataProvider` to a paid/
      survivorship-bias-free feed; corporate actions; borrow costs for shorts.
- [ ] **Phase 5** — React + Plotly dashboard; richer Grafana SLOs.
- [ ] **Phase 6** — Lift to Proxmox: same containers, Azure-for-Students GPU
      for the satellite batch jobs, GitHub Actions deploy.

## Known open doors (deliberately not closed)

- **Feature store** is custom on Postgres but the read/write interface
  (`adp.core.pit`) is small — swap to Feast/ClickHouse without touching callers.
- **Market data** is free `yfinance` — `MarketDataProvider` is a clean seam.
- **Orchestration** is Prefect; flows are thin so Airflow port is mechanical.
- **Silver schema** is generic (`dimensions jsonb`) — new sources need **no
  migration**.
- **Signal combine** is linear `FactorModel` today; ML model = one new class.
