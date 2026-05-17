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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
