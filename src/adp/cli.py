"""Unified CLI: `adp <command>`.

Thin wrapper over the layers so every operation is scriptable and CI-testable.
"""

from __future__ import annotations

import datetime as dt

import typer

from adp.core.logging import get_logger
from adp.core.registry import get_source, list_sources

app = typer.Typer(add_completion=False, help="Alternative Data Platform CLI")
log = get_logger("adp.cli")


def _drange(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


@app.command("sources")
def sources() -> None:
    """List registered data sources."""
    for s in list_sources():
        typer.echo(s)


@app.command("ingest")
def ingest(
    source: str,
    start: str = typer.Option(..., help="YYYY-MM-DD"),
    end: str | None = typer.Option(None, help="YYYY-MM-DD (default = start)"),
    force: bool = typer.Option(False, help="re-download even if Bronze exists"),
) -> None:
    """Ingest a date range for a source (idempotent, backfill-safe)."""
    s = get_source(source)
    sd = dt.date.fromisoformat(start)
    ed = dt.date.fromisoformat(end) if end else sd
    total = 0
    for d in _drange(sd, ed):
        total += s.run_ingest(d, force=force)
    typer.echo(f"ingested {total} silver rows for {source} [{sd}..{ed}]")


@app.command("features")
def features(
    source: str,
    start: str = typer.Option(...),
    end: str | None = typer.Option(None),
) -> None:
    """Compute Gold features from Silver for a source/date range."""
    from adp.features import compute as feat

    sd = dt.date.fromisoformat(start)
    ed = dt.date.fromisoformat(end) if end else sd
    n = feat.run(source, sd, ed)
    typer.echo(f"wrote {n} feature rows for {source} [{sd}..{ed}]")


@app.command("backtest")
def backtest(
    factor: str = typer.Option("posoco_industrial_yoy"),
    start: str = typer.Option(...),
    end: str = typer.Option(...),
) -> None:
    """Run the PIT-correct backtest for a factor."""
    from adp.backtest.engine import run_backtest

    res = run_backtest(
        factor, dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    )
    typer.echo(res.summary())


@app.command("backfill")
def backfill(
    source: str = typer.Argument(..., help="railway"),
    start: str = typer.Option(..., help="YYYY-MM (inclusive)"),
    end: str = typer.Option(..., help="YYYY-MM (inclusive)"),
    out: str | None = typer.Option(
        None, help="output dir (default: ADP_<SOURCE>_LOCAL_DIR)"
    ),
) -> None:
    """Fetch real monthly history into the offline dir from public releases.

    railway: scrapes PIB monthly freight press releases (no API key, no
    synthetic data) into `<out>/railway_YYYY-MM.csv`, ready for
    `adp ingest railway`.
    """
    from pathlib import Path

    from adp.core.config import get_settings

    if source != "railway":
        raise typer.BadParameter(
            f"backfill not implemented for '{source}' (only 'railway')"
        )
    from adp.sources.railway.backfill import backfill_railway

    s = get_settings()
    out_dir = Path(out or s.railway_local_dir or "data/railway")
    sd = dt.date.fromisoformat(f"{start}-01")
    ed = dt.date.fromisoformat(f"{end}-01")
    written, skipped = backfill_railway(sd, ed, out_dir)
    typer.echo(
        f"backfilled {written} month(s) to {out_dir}"
        + (f"; skipped {len(skipped)}: {', '.join(skipped)}" if skipped else "")
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
