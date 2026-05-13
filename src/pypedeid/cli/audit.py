"""``audit`` subgroup — list and show audit records."""

from __future__ import annotations

import json

import click

from pypedeid.cli.root import main


@main.group()
def audit() -> None:
    """Audit trail commands."""


@audit.command(name="list")
@click.option("--limit", type=int, default=20, show_default=True)
@click.option("--source", type=click.Choice(["cli", "api-admin", "api-inference"]), default=None)
def audit_list(limit: int, source: str | None) -> None:
    """List recent audit records."""
    from pypedeid.audit import list_runs

    records = list_runs(limit=limit, source=source)
    if not records:
        click.echo("No audit records found.")
        return

    header = (
        f"{'ID':<12} {'Timestamp':<20} {'User':<10} {'Cmd':<8} "
        f"{'Pipeline':<20} {'Src':<5} {'Docs':>5} {'Spans':>7} {'Time':>8}"
    )
    click.echo(header)
    click.echo("-" * len(header))
    for r in records:
        ts = r.timestamp.strftime("%Y-%m-%d %H:%M:%S") if r.timestamp else ""
        click.echo(
            f"{r.id[:12]:<12} {ts:<20} {r.user:<10} "
            f"{r.command:<8} {r.pipeline_name[:20]:<20} {r.source:<5} "
            f"{r.doc_count:>5} {r.span_count:>7} {r.duration_seconds:>7.1f}s"
        )


@audit.command(name="show")
@click.argument("record_id")
def audit_show(record_id: str) -> None:
    """Show details of a specific audit record."""
    from pypedeid.audit import get_run

    record = get_run(record_id)
    if record is None:
        click.echo(f"No record found for {record_id!r}.", err=True)
        raise SystemExit(1)

    ts = record.timestamp.strftime("%Y-%m-%d %H:%M:%S") if record.timestamp else ""
    click.echo(f"ID:            {record.id}")
    click.echo(f"Timestamp:     {ts}")
    click.echo(f"User:          {record.user}")
    click.echo(f"Command:       {record.command}")
    click.echo(f"Pipeline:      {record.pipeline_name}")
    click.echo(f"Source:        {record.source}")
    click.echo(f"Docs:          {record.doc_count}")
    click.echo(f"Errors:        {record.error_count}")
    click.echo(f"Spans:         {record.span_count}")
    click.echo(f"Duration:      {record.duration_seconds:.1f}s")
    if record.dataset_source:
        click.echo(f"Dataset:       {record.dataset_source}")
    if record.metrics:
        click.echo(f"Metrics:       {json.dumps(record.metrics, indent=2)}")
    if record.notes:
        click.echo(f"Notes:         {record.notes}")
    click.echo(f"\nPipeline config:\n{json.dumps(record.pipeline_config, indent=2)}")
