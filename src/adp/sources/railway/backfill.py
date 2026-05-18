"""Real, automated railway-freight backfill from PIB monthly press releases.

This is an *ops tool*, deliberately kept OUT of the deterministic
``RailwaySource`` (discover/fetch/parse stays offline-only and CI-stable — the
ROADMAP firewall). It populates ``ADP_RAILWAY_LOCAL_DIR`` with real
``railway_YYYY-MM.csv`` files so the normal ingest -> silver -> features ->
backtest pipeline then runs unchanged on genuine data.

No synthetic generation, no API key:

  1. discover  — DuckDuckGo (Bing fallback) HTML search resolves the Press
     Information Bureau PRID for that month's "Indian Railways freight loading"
     release.
  2. fetch     — the PIB iframe page (browser UA + redirect; verified working).
  3. parse     — the loading sentence is plain prose, e.g.
     "... 60.27 MT in Coal (excluding imported coal), 8.82MT in imported coal,
     15.07 MT in Iron Ore, 7.56 MT in Cement (Excl. Clinker) ... during
     June 2024". A regex lifts every "<n> MT in <commodity>" pair; the existing
     tested ``commodity_map.yaml`` mapping is applied later by the ingest
     parser, so labels are written through verbatim.

Per-commodity *revenue* is not in the monthly release (only tonnage), so the
``freight_revenue_cr`` column is left blank — the railway feature recipe keys
off ``freight_mt`` anyway and the CSV parser tolerates an empty value.
"""

from __future__ import annotations

import calendar
import datetime as dt
import re
import time
import urllib.parse
from pathlib import Path

import requests

from adp.core.logging import get_logger

log = get_logger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_PIB = "https://www.pib.gov.in/PressReleaseIframePage.aspx?PRID={prid}"

# "<number> MT in <label>" — label runs until a comma, " and ", " during",
# or sentence end. Handles "60.27 MT in", "8.82MT in", "123.06MT in".
_LOAD_RE = re.compile(
    r"([0-9]+(?:\.[0-9]+)?)\s*MT\s+in\s+"
    r"([A-Za-z][A-Za-z0-9 &()./'\-]*?)"
    r"(?=,|\s+and\s+|\s+during\b|\s+as\s+against\b|\.|$)",
    re.IGNORECASE,
)
_PRID_RE = re.compile(r"PRID=(\d+)")

# Committed bibliography of real PIB monthly-freight document ids (NOT data —
# the tonnage is fetched live from each PIB page and parsed). Pinning the
# document id makes the backfill deterministic / CI-stable instead of
# depending on a flaky, bot-walled search at runtime. Live search (below) is
# only the fallback for months not yet listed here.
_MANIFEST = Path(__file__).parent / "config" / "pib_prids.csv"


def _load_manifest() -> dict[str, int]:
    if not _MANIFEST.exists():
        return {}
    out: dict[str, int] = {}
    for line in _MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.lower().startswith("month"):
            continue
        month, prid = (c.strip() for c in line.split(",")[:2])
        if prid.isdigit():
            out[month] = int(prid)
    return out


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"})
    return s


def _search_prid(sess: requests.Session, query: str) -> int | None:
    """Resolve a PIB PRID via no-key HTML search (DDG primary, Bing fallback).

    PIB PRIDs are sequential global ids, not date-derived, so the release is
    not addressable by a URL template — it must be discovered."""
    engines = (
        ("https://html.duckduckgo.com/html/", {"q": query}),
        ("https://www.bing.com/search", {"q": query}),
    )
    for url, params in engines:
        try:
            r = sess.get(url, params=params, timeout=30)
            r.raise_for_status()
        except requests.RequestException as e:
            log.info("backfill_search_fail", engine=url, err=str(e))
            continue
        # DDG wraps targets in /l/?uddg=<urlencoded>; unquote first.
        hits = _PRID_RE.findall(urllib.parse.unquote(r.text))
        if hits:
            # Most-frequent PRID = the result echoed across title/snippet/link.
            return int(max(set(hits), key=hits.count))
    return None


def _parse_loading(html: str, year: int, month: int) -> dict[str, float]:
    """Lift every '<n> MT in <commodity>' pair from a confirmed monthly
    release. Returns {raw_label: tonnage}; mapping to sectors happens later
    in the tested ingest parser."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;|&amp;", " ", text)
    text = re.sub(r"\s+", " ", text)

    mname = calendar.month_name[month]
    # PIB's monthly release is often *titled* cumulatively ("... till
    # <Month>") but its body always states the month's per-commodity loading
    # as "... during <Month>, <Year>". Require that monthly sentence; the
    # presence of extra cumulative/FY text in the same release is fine.
    if not re.search(
        rf"during\s+{mname},?\s+{year}\b", text, re.IGNORECASE
    ):
        return {}

    out: dict[str, float] = {}
    for num, label in _LOAD_RE.findall(text):
        lbl = label.strip(" .-").strip()
        # Real commodity labels never contain digits — anything with a digit is
        # captured prose ("Jan 2024 - an improvement of 6"). Also drop the
        # headline total / month-context and the bare "freight" captures.
        if (
            not lbl
            or any(c.isdigit() for c in lbl)
            or mname.lower() in lbl.lower()
            or lbl.lower() in ("freight", "freight loading")
        ):
            continue
        out.setdefault(lbl, float(num))  # first mention wins (PIB repeats it)
    return out


def _write_csv(out_dir: Path, year: int, month: int, rows: dict[str, float]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"railway_{year:04d}-{month:02d}.csv"
    lines = ["commodity,freight_mt,freight_revenue_cr"]
    for label, mt in rows.items():
        safe = label.replace('"', "").replace(",", " ")
        lines.append(f"{safe},{mt},")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _months(start: dt.date, end: dt.date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def backfill_railway(
    start: dt.date,
    end: dt.date,
    out_dir: Path,
    *,
    pause: float = 2.0,
) -> tuple[int, list[str]]:
    """Write real ``railway_YYYY-MM.csv`` files for every month in
    [start, end]. Returns (files_written, skipped_months). Missing months are
    skipped (logged) — the monthly source already treats a missing file as a
    no-op, and the YoY recipe just needs >=13 of the months present."""
    sess = _session()
    manifest = _load_manifest()
    written = 0
    skipped: list[str] = []
    for year, month in _months(start, end):
        tag = f"{year:04d}-{month:02d}"
        mname = calendar.month_name[month]
        try:
            prid = manifest.get(tag)
            if prid is None:  # fallback: best-effort live search
                prid = _search_prid(
                    sess,
                    f"site:pib.gov.in Indian Railways freight loading "
                    f"{mname} {year}",
                )
            if prid is None:
                raise RuntimeError("no PRID (not in manifest, search failed)")
            page = sess.get(_PIB.format(prid=prid), timeout=45)
            page.raise_for_status()
            rows = _parse_loading(page.text, year, month)
            if len(rows) < 3:
                raise RuntimeError(
                    f"only {len(rows)} commodities parsed (PRID={prid}); "
                    "wrong release or layout drift"
                )
            path = _write_csv(out_dir, year, month, rows)
            written += 1
            log.info(
                "backfill_month_ok",
                month=tag,
                prid=prid,
                commodities=len(rows),
                file=str(path),
            )
        except Exception as e:  # noqa: BLE001 — best-effort per month
            skipped.append(tag)
            log.warning("backfill_month_skip", month=tag, err=str(e))
        time.sleep(pause)  # be polite to the search endpoint
    return written, skipped
