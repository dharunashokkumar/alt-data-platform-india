"""Generate synthetic POSOCO CSVs for offline end-to-end runs / CI / demos.

Writes `<out>/posoco_<YYYY-MM-DD>.csv` with columns
`date,state,energy_met_mu,peak_demand_met_mw` for a date range, using a
trend + annual seasonality + per-state level + noise so the YoY feature and
backtest are non-degenerate. NOT real data — for pipeline exercise only.

    python scripts/gen_sample_posoco.py --start 2023-01-01 --end 2025-05-10 \
        --out data/posoco_sample
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
import pathlib
import random

# canonical states present in the seeded universe
STATES = {
    "Maharashtra": 95000,
    "Gujarat": 105000,
    "Rajasthan": 70000,
    "Tamil Nadu": 90000,
    "Karnataka": 65000,
    "Chhattisgarh": 60000,
    "Jharkhand": 35000,
    "Haryana": 55000,
    "Delhi": 30000,
    "West Bengal": 45000,
    "Madhya Pradesh": 60000,
    "Uttarakhand": 20000,
}
# state-specific annual growth rate -> creates cross-sectional signal
GROWTH = {
    "Gujarat": 0.11, "Maharashtra": 0.06, "Tamil Nadu": 0.09,
    "Karnataka": 0.08, "Rajasthan": 0.04, "Chhattisgarh": 0.10,
    "Jharkhand": 0.03, "Haryana": 0.05, "Delhi": 0.02,
    "West Bengal": 0.03, "Madhya Pradesh": 0.07, "Uttarakhand": 0.04,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", default="data/posoco_sample")
    a = ap.parse_args()

    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    sd = dt.date.fromisoformat(a.start)
    ed = dt.date.fromisoformat(a.end)
    rng = random.Random(42)

    d = sd
    n = 0
    while d <= ed:
        doy = d.timetuple().tm_yday
        season = 1.0 + 0.12 * math.sin(2 * math.pi * (doy - 110) / 365)
        years = (d - sd).days / 365.0
        rows = []
        for st, base in STATES.items():
            level = base * season * (1 + GROWTH[st]) ** years
            energy = level / 1000.0 * (1 + rng.uniform(-0.03, 0.03))  # MU
            peak = level / 22.0 * (1 + rng.uniform(-0.03, 0.03))  # MW
            rows.append((d.isoformat(), st, round(energy, 2), round(peak, 1)))
        with (out / f"posoco_{d.isoformat()}.csv").open(
            "w", newline="", encoding="utf-8"
        ) as f:
            w = csv.writer(f)
            w.writerow(["date", "state", "energy_met_mu", "peak_demand_met_mw"])
            w.writerows(rows)
        n += 1
        d += dt.timedelta(days=1)
    print(f"wrote {n} sample files to {out}")


if __name__ == "__main__":
    main()
