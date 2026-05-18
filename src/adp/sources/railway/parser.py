"""Indian Railways monthly freight report parser.

Input paths auto-detected from magic bytes (layout fragility contained here —
the ROADMAP firewall; downstream contracts never change):

  * PDF  (``%PDF``)        — the real Ministry-of-Railways / PIB monthly
    freight statement. pdfplumber table extraction.
  * XLSX (``PK\\x03\\x04``) — workbook variant. openpyxl.
  * CSV                    — columns ``commodity,freight_mt,freight_revenue_cr``.
    The path for committed real-extract test fixtures and cleaned-archive
    backfill, so the pipeline runs offline / in CI without the live site.

A commodity can feed several consuming industries (commodity_map values are
lists), so its tonnage/revenue is fanned out to every mapped sector. Output:
one SilverRecord per (industry, metric).
"""

from __future__ import annotations

import csv
import io
import pathlib
import re

import yaml

from adp.core.logging import get_logger
from adp.core.schemas import BronzeRef, SilverRecord
from adp.sources._periodic import month_end

log = get_logger(__name__)

_ALIASES: dict[str, list[str]] = yaml.safe_load(
    (pathlib.Path(__file__).parent / "config/commodity_map.yaml").read_text(
        encoding="utf-8"
    )
)["aliases"]
_ALIAS_KEYS = sorted(_ALIASES, key=len, reverse=True)

FREIGHT_MT = "freight_mt"
FREIGHT_REVENUE_CR = "freight_revenue_cr"


def _sectors(label: str) -> list[str]:
    low = re.sub(r"\s+", " ", (label or "")).strip().lower()
    if not low:
        return []
    for k in _ALIAS_KEYS:
        if k in low:
            return _ALIASES[k]
    return []


def _num(x: object) -> float | None:
    try:
        return float(str(x).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _accumulate(
    agg: dict[tuple[str, str], float],
    label: str,
    mt: float | None,
    rev_cr: float | None,
) -> None:
    for sector in _sectors(label):
        if mt is not None:
            agg[(sector, FREIGHT_MT)] = (
                agg.get((sector, FREIGHT_MT), 0.0) + mt
            )
        if rev_cr is not None:
            agg[(sector, FREIGHT_REVENUE_CR)] = (
                agg.get((sector, FREIGHT_REVENUE_CR), 0.0) + rev_cr
            )


def _emit(
    ref: BronzeRef, agg: dict[tuple[str, str], float]
) -> list[SilverRecord]:
    obs = month_end(ref.date)
    unit = {FREIGHT_MT: "MT", FREIGHT_REVENUE_CR: "INR_cr"}
    out = [
        SilverRecord(
            source="railway",
            observation_date=obs,
            published_date=ref.published_date,
            dimensions={"industry": sector, "metric": metric},
            value=val,
            unit=unit[metric],
            bronze_uri=ref.uri,
        )
        for (sector, metric), val in sorted(agg.items())
    ]
    if not out:
        log.warning(
            "railway_no_rows",
            uri=ref.uri,
            hint="layout/commodity labels may have changed; update railway "
            "commodity_map.yaml or parser",
        )
    return out


def _find_col(header: list[str], needles: tuple[str, ...]) -> int | None:
    for i, h in enumerate(header):
        if any(n in h for n in needles):
            return i
    return None


def _from_table_rows(
    ref: BronzeRef, rows: list[list[object]]
) -> dict[tuple[str, str], float]:
    agg: dict[tuple[str, str], float] = {}
    if not rows or len(rows) < 2:
        return agg
    header = [str(c or "").lower() for c in rows[0]]
    c_label = _find_col(header, ("commodity", "commodities", "goods"))
    c_mt = _find_col(header, ("loading", "tonne", "mt", "quantity"))
    c_rev = _find_col(header, ("revenue", "earning", "freight earn"))
    if c_label is None or (c_mt is None and c_rev is None):
        return agg
    for r in rows[1:]:
        if c_label >= len(r):
            continue
        _accumulate(
            agg,
            str(r[c_label] or ""),
            _num(r[c_mt]) if c_mt is not None and c_mt < len(r) else None,
            _num(r[c_rev]) if c_rev is not None and c_rev < len(r) else None,
        )
    return agg


def _from_csv(ref: BronzeRef, raw: bytes) -> list[SilverRecord]:
    agg: dict[tuple[str, str], float] = {}
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    for row in reader:
        _accumulate(
            agg,
            row.get("commodity") or "",
            _num(row.get(FREIGHT_MT, "")),
            _num(row.get(FREIGHT_REVENUE_CR, "")),
        )
    return _emit(ref, agg)


def _from_xlsx(ref: BronzeRef, raw: bytes) -> list[SilverRecord]:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    agg: dict[tuple[str, str], float] = {}
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        for i, row in enumerate(rows):
            cells = [str(c or "").lower() for c in row]
            if any("commodit" in c or "goods" in c for c in cells):
                for k, v in _from_table_rows(ref, rows[i:]).items():
                    agg[k] = agg.get(k, 0.0) + v
                break
    wb.close()
    return _emit(ref, agg)


def _from_pdf(ref: BronzeRef, raw: bytes) -> list[SilverRecord]:
    import pdfplumber

    agg: dict[tuple[str, str], float] = {}
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for k, v in _from_table_rows(ref, table).items():
                    agg[k] = agg.get(k, 0.0) + v
    return _emit(ref, agg)


def parse(ref: BronzeRef, raw: bytes) -> list[SilverRecord]:
    if raw[:4] == b"%PDF":
        return _from_pdf(ref, raw)
    if raw[:4] == b"PK\x03\x04":
        return _from_xlsx(ref, raw)
    return _from_csv(ref, raw)
