"""GST e-way bill monthly report parser.

Three input paths, auto-detected from the payload's magic bytes — the layout
fragility is contained entirely to this file (the ROADMAP risk mitigation);
downstream contracts never change:

  * XLSX (``PK\\x03\\x04``) — the real GSTN/e-way-bill monthly statistics
    workbook. Parsed with openpyxl.
  * PDF  (``%PDF``)        — the PIB/GSTN press-release PDF variant. pdfplumber.
  * CSV                    — columns ``commodity,eway_count,eway_value_cr``.
    The path for committed real-extract test fixtures and cleaned-archive
    backfill, so the whole pipeline is exercisable offline / in CI without the
    live portal (same rationale POSOCO documents for its CSV branch).

Output: one SilverRecord per (industry, metric), value aggregated across every
HSN commodity that maps to the same canonical sector.
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

_ALIASES: dict[str, str] = yaml.safe_load(
    (pathlib.Path(__file__).parent / "config/hsn_map.yaml").read_text(
        encoding="utf-8"
    )
)["aliases"]
# longest key first so the most specific commodity label wins
_ALIAS_KEYS = sorted(_ALIASES, key=len, reverse=True)

EWAY_COUNT = "eway_count"
EWAY_VALUE_CR = "eway_value_cr"


def _sector(label: str) -> str | None:
    low = re.sub(r"\s+", " ", (label or "")).strip().lower()
    if not low:
        return None
    for k in _ALIAS_KEYS:
        if k in low:
            return _ALIASES[k]
    return None


def _num(x: object) -> float | None:
    try:
        return float(str(x).replace(",", "").replace("₹", "").strip())
    except (ValueError, AttributeError):
        return None


def _emit(
    ref: BronzeRef, agg: dict[tuple[str, str], float]
) -> list[SilverRecord]:
    """agg: {(sector, metric): value} -> SilverRecords (sector = `industry`)."""
    obs = month_end(ref.date)
    unit = {EWAY_COUNT: "count", EWAY_VALUE_CR: "INR_cr"}
    out = [
        SilverRecord(
            source="gst",
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
            "gst_no_rows",
            uri=ref.uri,
            hint="layout/HSN labels may have changed; update gst hsn_map.yaml "
            "or parser",
        )
    return out


def _accumulate(
    agg: dict[tuple[str, str], float],
    label: str,
    count: float | None,
    value_cr: float | None,
) -> None:
    sector = _sector(label)
    if sector is None:
        return
    if count is not None:
        agg[(sector, EWAY_COUNT)] = agg.get((sector, EWAY_COUNT), 0.0) + count
    if value_cr is not None:
        agg[(sector, EWAY_VALUE_CR)] = (
            agg.get((sector, EWAY_VALUE_CR), 0.0) + value_cr
        )


def _from_csv(ref: BronzeRef, raw: bytes) -> list[SilverRecord]:
    agg: dict[tuple[str, str], float] = {}
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    for row in reader:
        label = row.get("commodity") or row.get("hsn") or ""
        _accumulate(
            agg,
            label,
            _num(row.get(EWAY_COUNT, "")),
            _num(row.get(EWAY_VALUE_CR, "")),
        )
    return _emit(ref, agg)


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
    c_label = _find_col(header, ("commodity", "hsn", "description", "goods"))
    c_count = _find_col(header, ("count", "no. of", "number", "ewb"))
    c_value = _find_col(header, ("value", "amount", "assessable"))
    if c_label is None or (c_count is None and c_value is None):
        return agg
    for r in rows[1:]:
        if c_label >= len(r):
            continue
        _accumulate(
            agg,
            str(r[c_label] or ""),
            _num(r[c_count]) if c_count is not None and c_count < len(r) else None,
            _num(r[c_value]) if c_value is not None and c_value < len(r) else None,
        )
    return agg


def _from_xlsx(ref: BronzeRef, raw: bytes) -> list[SilverRecord]:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    agg: dict[tuple[str, str], float] = {}
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        # find the header row (first row that names a commodity column)
        for i, row in enumerate(rows):
            cells = [str(c or "").lower() for c in row]
            if any(
                n in c
                for c in cells
                for n in ("commodity", "hsn", "description")
            ):
                merged = _from_table_rows(ref, rows[i:])
                for k, v in merged.items():
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
