"""``dict`` subgroup — dictionary (whitelist/blacklist) management."""

from __future__ import annotations

from pathlib import Path

import click

from pypedeid.cli._common import dict_store
from pypedeid.cli.root import main


@main.group(name="dict")
def dict_group() -> None:
    """Dictionary management (whitelist / blacklist term lists)."""


@dict_group.command(name="list")
@click.option("--kind", type=click.Choice(["whitelist", "blacklist"]), default=None)
def dict_list(kind: str | None) -> None:
    """List all dictionaries."""
    store = dict_store()
    entries = store.list_dictionaries(kind=kind)
    if not entries:
        click.echo("No dictionaries found.")
        return

    header = f"{'Kind':<12} {'Name':<32} {'Terms':>8} {'File'}"
    click.echo(header)
    click.echo("-" * len(header))
    for e in entries:
        click.echo(
            f"{e.kind:<12} {e.name:<32} {e.term_count:>8} {e.filename}"
        )


@dict_group.command(name="preview")
@click.argument("kind", type=click.Choice(["whitelist", "blacklist"]))
@click.argument("name")
@click.option("-n", "count", default=20, show_default=True, help="Number of terms to show.")
def dict_preview(kind: str, name: str, count: int) -> None:
    """Preview terms from a dictionary."""
    store = dict_store()
    try:
        terms = store.get_terms(kind, name)
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)

    click.echo(f"{kind}/{name}  ({len(terms)} terms total)")
    for t in terms[:count]:
        click.echo(f"  {t}")
    if len(terms) > count:
        click.echo(f"  ... and {len(terms) - count} more")


@dict_group.command(name="import")
@click.argument("file", type=click.Path(exists=True))
@click.option("--kind", type=click.Choice(["whitelist", "blacklist"]), required=True)
@click.option("--name", required=True, help="Dictionary name.")
def dict_import(file: str, kind: str, name: str) -> None:
    """Import a dictionary from a local file (txt, csv, or json)."""
    p = Path(file)
    content = p.read_text(encoding="utf-8")
    ext = p.suffix if p.suffix in (".txt", ".csv", ".json") else ".txt"

    store = dict_store()
    try:
        info = store.save(kind, name, content, extension=ext)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)

    click.echo(f"Saved {info.term_count} terms to {info.kind}/{info.filename}")


@dict_group.command(name="delete")
@click.argument("kind", type=click.Choice(["whitelist", "blacklist"]))
@click.argument("name")
def dict_delete(kind: str, name: str) -> None:
    """Delete a dictionary."""
    store = dict_store()
    try:
        store.delete(kind, name)
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
    click.echo(f"Deleted {kind}/{name}")
