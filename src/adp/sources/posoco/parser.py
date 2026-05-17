"""POSOCO / Grid-India PSP report parser.

Two input paths, auto-detected from the payload bytes:

  * PDF  (starts with ``%PDF``) - the real daily PSP report. Parsed with
    pdfplumber. Layout drift is contained entirely to this file (the plan's
    risk mitigation): downstream contracts never change.
  * CSV  - columns ``date,state,energy_met_mu,peak_demand_met_mw``. Used for
    offline dev, CI and backfill from cleaned archives, so the whole pipeline
    is exercisable without depending on the live site.

Output: one SilverRecord per (state, metric).
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import pathlib
import re

import yaml

from adp.core.logging import get_logger
from adp.core.schemas import BronzeRef, SilverRecord

log = get_logger(__name__)

_ALIASES: dict[str, str] = yaml.safe_load(
    (pathlib.Path(__file__).parent / "config/state_aliases.yaml").read_text(
        encoding="utf-8"
    )
)["aliases"]

ENERGY_MET_MU = "energy_met_mu"
PEAK_DEMAND_MW = "peak_demand_met_mw"


def _canonical_state(label: str) -> str | None:
    return _ALIASES.get(label.strip())


def _num(x: str) -> float | None:
    try:
        return float(str(x).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _records_from_csv(ref: BronzeRef, raw: bytes) -> list[SilverRecord]:
    out: list[SilverRecord] = []
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    for row in reader:
        state = _canonical_state(row.get("state", ""))
        if not state:
            continue
        obs_date = dt.date.fromisoformat(row["date"])
        for metric, unit in ((ENERGY_MET_MU, "MU"), (PEAK_DEMAND_MW, "MW")):
            v = _num(row.get(metric, ""))
            if v is None:
                continue
            out.append(
                SilverRecord(
                    source="posoco",
                    observation_date=obs_date,
                    published_date=ref.published_date,
                    dimensions={"state": state, "metric": metric},
                    value=v,
                    unit=unit,
                    bronze_uri=ref.uri,
                )
            )
    return out


def _records_from_pdf(ref: BronzeRef, raw: bytes) -> list[SilverRecord]:
    import pdfplumber

    out: list[SilverRecord] = []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                if not table or len(table) < 2:
                    continue
                header = [(c or "").lower() for c in table[0]]
                e_idx = _find_col(header, ("energy met", "energy"))
                p_idx = _find_col(header, ("peak met", "peak demand", "max demand"))
                s_idx = _find_col(header, ("state", "states/uts", "uts"))
                if s_idx is None or (e_idx is None and p_idx is None):
                    continue
                for r in table[1:]:
                    state = _canonical_state(_clean(r[s_idx]))
                    if not state:
                        continue
                    if e_idx is not None:
                        v = _num(r[e_idx])
                        if v is not None:
                            out.append(
                                _rec(ref, state, ENERGY_MET_MU, v, "MU")
                            )
                    if p_idx is not None:
                        v = _num(r[p_idx])
                        if v is not None:
                            out.append(
                                _rec(ref, state, PEAK_DEMAND_MW, v, "MW")
                            )
    if not out:
        log.warning(
            "posoco_pdf_no_rows",
            uri=ref.uri,
            hint="PSP layout may have changed; update parser._records_from_pdf",
        )
    return out


def _rec(
    ref: BronzeRef, state: str, metric: str, value: float, unit: str
) -> SilverRecord:
    return SilverRecord(
        source="posoco",
        observation_date=ref.date,
        published_date=ref.published_date,
        dimensions={"state": state, "metric": metric},
        value=value,
        unit=unit,
        bronze_uri=ref.uri,
    )


def _clean(c: str | None) -> str:
    return re.sub(r"\s+", " ", (c or "")).strip()


def _find_col(header: list[str], needles: tuple[str, ...]) -> int | None:
    for i, h in enumerate(header):
        if any(n in h for n in needles):
            return i
    return None


def parse(ref: BronzeRef, raw: bytes) -> list[SilverRecord]:
    if raw[:4] == b"%PDF":
        return _records_from_pdf(ref, raw)
    return _records_from_csv(ref, raw)
