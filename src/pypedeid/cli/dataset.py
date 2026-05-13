"""``dataset`` subgroup — register, browse, transform, export."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import click

from pypedeid.cli._common import corpora_dir
from pypedeid.cli.root import main
from pypedeid.domain import AnnotatedDocument

logger = logging.getLogger(__name__)


@main.group()
def dataset() -> None:
    """Dataset management (register, browse, delete)."""


@dataset.command(name="list")
@click.option("--limit", type=int, default=50, show_default=True)
def dataset_list(limit: int) -> None:
    """List registered datasets."""
    from pypedeid.dataset_store import list_datasets

    datasets = list_datasets(corpora_dir())[:limit]
    if not datasets:
        click.echo("No datasets registered.")
        return

    header = f"{'Name':<25} {'Format':<12} {'Docs':>6} {'Spans':>8} {'Labels'}"
    click.echo(header)
    click.echo("-" * len(header))
    for ds in datasets:
        labels_str = ", ".join(ds.labels[:5])
        if len(ds.labels) > 5:
            labels_str += f" (+{len(ds.labels) - 5})"
        click.echo(
            f"{ds.name:<25} {ds.format:<12} {ds.document_count:>6} "
            f"{ds.total_spans:>8} {labels_str}"
        )


@dataset.command(name="register")
@click.argument("data_path", type=click.Path(exists=True))
@click.option("--name", required=True, help="Dataset name.")
@click.option("--description", default="", help="Optional description.")
def dataset_register(data_path: str, name: str, description: str) -> None:
    """Import a JSONL corpus into a new dataset home.

    BRAT trees must be converted first with ``pypedeid dataset import-brat``.

    \b
    Examples:
      pypedeid dataset register data/corpus.jsonl --name i2b2-2014
    """
    from pypedeid.dataset_store import import_jsonl_dataset

    src = Path(data_path)
    if src.suffix.lower() != ".jsonl":
        click.echo(
            f"Error: {src.name!r} is not a .jsonl file. "
            "Use `pypedeid dataset import-brat` for BRAT trees.",
            err=True,
        )
        raise SystemExit(1)

    try:
        manifest = import_jsonl_dataset(
            corpora_dir(),
            name,
            str(src.resolve()),
            description=description,
        )
    except (ValueError, FileNotFoundError) as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)

    click.echo(
        f"Registered {name!r}: {manifest['document_count']} docs, "
        f"{manifest['total_spans']} spans, "
        f"labels: {', '.join(manifest['labels'])}"
    )


@dataset.command(name="import-brat")
@click.argument("brat_path", type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option("--name", required=True, help="Dataset name.")
@click.option("--description", default="", help="Optional description.")
def dataset_import_brat(brat_path: str, name: str, description: str) -> None:
    """Convert a BRAT tree (flat or split) into a new JSONL dataset home.

    \b
    Examples:
      pypedeid dataset import-brat data/physionet-brat/ --name physionet
      pypedeid dataset import-brat data/2014-i2b2-brat/ --name i2b2-2014
    """
    from pypedeid.dataset_store import import_brat_to_jsonl

    try:
        manifest = import_brat_to_jsonl(
            corpora_dir(),
            name,
            Path(brat_path),
            description=description,
        )
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)

    click.echo(
        f"Imported {name!r} from BRAT: {manifest['document_count']} docs, "
        f"{manifest['total_spans']} spans, "
        f"labels: {', '.join(manifest['labels'])}"
    )


@dataset.command(name="refresh")
@click.argument("name")
def dataset_refresh(name: str) -> None:
    """Recompute cached analytics for one dataset from ``corpus.jsonl``."""
    from pypedeid.dataset_store import refresh_dataset

    try:
        manifest = refresh_dataset(corpora_dir(), name)
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
    click.echo(
        f"Refreshed {name!r}: {manifest['document_count']} docs, "
        f"{manifest['total_spans']} spans"
    )


@dataset.command(name="refresh-all")
def dataset_refresh_all() -> None:
    """Recompute analytics for every discovered dataset; per-home errors are reported inline."""
    from pypedeid.dataset_store import refresh_all_datasets

    results = refresh_all_datasets(corpora_dir())
    if not results:
        click.echo("No datasets discovered.")
        return
    ok = err = 0
    for r in results:
        if r.status == "ok":
            click.echo(f"  [ok]    {r.name}")
            ok += 1
        else:
            click.echo(f"  [error] {r.name}: {r.error}")
            err += 1
    click.echo(f"\n{ok} ok, {err} error(s)")
    if err and ok == 0:
        raise SystemExit(1)


@dataset.command(name="show")
@click.argument("name")
def dataset_show(name: str) -> None:
    """Show details of a registered dataset."""
    from pypedeid.config import get_settings
    from pypedeid.dataset_store import load_dataset_manifest, public_data_path

    try:
        m = load_dataset_manifest(corpora_dir(), name)
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)

    click.echo(f"Name:          {m['name']}")
    click.echo(f"Description:   {m.get('description', '')}")
    click.echo(f"Data path:     {public_data_path(get_settings().corpora_dir, name, m)}")
    click.echo(f"Format:        {m['format']}")
    click.echo(f"Documents:     {m.get('document_count', 0)}")
    click.echo(f"Total spans:   {m.get('total_spans', 0)}")
    click.echo(f"Labels:        {', '.join(m.get('labels', []))}")
    click.echo(f"Created:       {m.get('created_at', '')}")
    if m.get("metadata"):
        click.echo(f"Metadata:      {json.dumps(m['metadata'], indent=2)}")
    analytics = m.get("analytics", {})
    if analytics:
        label_counts = analytics.get("label_counts", {})
        if label_counts:
            click.echo("\nLabel distribution:")
            for label, count in sorted(label_counts.items(), key=lambda x: -x[1]):
                click.echo(f"  {label:<20} {count:>6}")


@dataset.command(name="delete")
@click.argument("name")
def dataset_delete(name: str) -> None:
    """Delete the dataset directory (manifest and corpus files)."""
    from pypedeid.dataset_store import delete_dataset

    try:
        delete_dataset(corpora_dir(), name)
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
    click.echo(f"Deleted dataset {name!r}")


@dataset.command(name="ingest-run")
@click.option(
    "--input",
    "input_path",
    type=click.Path(exists=True),
    required=True,
    help="Directory of .txt files, a single .txt, or a .jsonl of {id, text} rows.",
)
@click.option("--pipeline", "pipeline_name", required=True, help="Saved pipeline name.")
@click.option(
    "--output-name",
    default=None,
    help="Register result as a new dataset under CORPORA_DIR/<name>/.",
)
@click.option(
    "--output-jsonl",
    type=click.Path(),
    default=None,
    help="Write a one-off JSONL file (no registration). Mutually exclusive with --output-name.",
)
@click.option(
    "--on-error",
    type=click.Choice(["skip", "stop"]),
    default="skip",
    show_default=True,
)
@click.option("--description", default="", help="Description for the registered dataset.")
def dataset_ingest_run(
    input_path: str,
    pipeline_name: str,
    output_name: str | None,
    output_jsonl: str | None,
    on_error: str,
    description: str,
) -> None:
    """Run a saved pipeline over raw text and register/export the annotated output.

    \b
    Examples:
      pypedeid dataset ingest-run --input notes/ \\
        --pipeline clinical-fast --output-name notes_clinical_fast_silver
      pypedeid dataset ingest-run --input notes.jsonl \\
        --pipeline clinical-fast --output-jsonl /tmp/out.jsonl
    """
    from pypedeid.config import get_settings
    from pypedeid.dataset_store import commit_colocated_dataset, list_datasets
    from pypedeid.ingest.from_batch import ingest_paths_with_pipeline
    from pypedeid.ingest.sink import write_annotated_corpus

    if bool(output_name) == bool(output_jsonl):
        click.echo(
            "Error: provide exactly one of --output-name or --output-jsonl.",
            err=True,
        )
        raise SystemExit(1)

    settings = get_settings()
    corp_dir = settings.corpora_dir

    if output_name:
        existing = {d.name for d in list_datasets(corp_dir)}
        if output_name in existing:
            click.echo(f"Error: dataset {output_name!r} already exists.", err=True)
            raise SystemExit(1)

    t0 = time.perf_counter()
    docs: list[AnnotatedDocument] = []
    errors: list[dict[str, Any]] = []
    try:
        stream = ingest_paths_with_pipeline(
            [Path(input_path)],
            pipeline_name=pipeline_name,
        )
        for doc in stream:
            try:
                docs.append(doc)
            except Exception as exc:
                if on_error == "stop":
                    raise
                errors.append({"doc_id": doc.document.id, "error": str(exc)})
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
    except RuntimeError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)

    duration = time.perf_counter() - t0

    if not docs:
        click.echo("No documents produced.", err=True)
        raise SystemExit(1)

    total_spans = sum(len(d.spans) for d in docs)

    if output_name:
        home = corp_dir / output_name
        home.mkdir(parents=True)
        write_annotated_corpus(docs, jsonl=home / "corpus.jsonl")
        manifest = commit_colocated_dataset(
            corp_dir,
            output_name,
            "jsonl",
            description=description or f"Ingested via pipeline {pipeline_name!r}",
            metadata={
                "provenance": {
                    "ingested_from": str(Path(input_path).resolve()),
                    "pipeline_name": pipeline_name,
                }
            },
        )
        click.echo(
            f"Registered {output_name!r}: {manifest['document_count']} docs, "
            f"{manifest['total_spans']} spans"
        )
    else:
        assert output_jsonl is not None
        out = Path(output_jsonl)
        out.parent.mkdir(parents=True, exist_ok=True)
        write_annotated_corpus(docs, jsonl=out)
        click.echo(f"Wrote {len(docs)} docs ({total_spans} spans) to {out}")

    try:
        from pypedeid.audit import log_run

        log_run(
            command="dataset_ingest",
            pipeline_name=pipeline_name,
            dataset_source=str(Path(input_path).resolve()),
            doc_count=len(docs),
            error_count=len(errors),
            span_count=total_spans,
            duration_seconds=duration,
            source="cli",
        )
    except Exception:
        logger.warning("Failed to write audit record", exc_info=True)


@dataset.command(name="export")
@click.argument("name")
@click.option("-o", "--output", "output_dir", type=click.Path(), required=False, default=None)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["conll", "spacy", "huggingface", "brat", "jsonl"]),
    default="conll",
    show_default=True,
    help="Downstream format (training, annotated JSONL, or BRAT for external tools).",
)
@click.option("--filename", default=None, help="Override output filename (ignored for brat).")
@click.option(
    "--target-text",
    type=click.Choice(["original", "surrogate"]),
    default="original",
    show_default=True,
    help="Emit docs with original text or surrogate-aligned replacements.",
)
@click.option(
    "--seed",
    "surrogate_seed",
    type=int,
    default=None,
    help="Seed for --target-text surrogate (determinism).",
)
def dataset_export(
    name: str,
    output_dir: str | None,
    fmt: str,
    filename: str | None,
    target_text: str,
    surrogate_seed: int | None,
) -> None:
    """Export a registered dataset to a training or tooling format.

    ``-o``/``--output`` is required for ``conll``/``spacy``/``huggingface``/``jsonl``. For
    ``--format brat`` it defaults to ``$EXPORTS_DIR/<name>/brat`` when unset.

    The ``jsonl`` format writes one ``AnnotatedDocument`` per line and can be
    re-registered via ``POST /datasets`` (``format: "jsonl"``). Use
    ``--target-text surrogate`` to replace each document's text with a surrogate
    and realign spans.

    \b
    Examples:
      pypedeid dataset export i2b2-2014 -o training/ --format conll
      pypedeid dataset export physionet -o training/ --format spacy
      pypedeid dataset export i2b2-2014 -o exports/ --format jsonl
      pypedeid dataset export i2b2-2014 --format brat
      pypedeid dataset export i2b2-2014 -o exports/ --format jsonl \\
        --target-text surrogate --seed 42
    """
    from pypedeid.config import get_settings
    from pypedeid.dataset_store import load_dataset_documents
    from pypedeid.ingest.sink import write_annotated_corpus
    from pypedeid.training_export import export_training_data

    try:
        docs = load_dataset_documents(corpora_dir(), name)
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)

    if not docs:
        click.echo("Dataset has no documents.", err=True)
        raise SystemExit(1)

    if target_text == "surrogate":
        try:
            from pypedeid.pipes.surrogate.align import surrogate_text_with_spans
        except ImportError as exc:
            click.echo(f"Error: surrogate export requires faker: {exc}", err=True)
            raise SystemExit(1)
        projected: list[AnnotatedDocument] = []
        offenders: list[str] = []
        for d in docs:
            try:
                new_text, new_spans = surrogate_text_with_spans(
                    d.document.text, list(d.spans), seed=surrogate_seed
                )
            except ValueError:
                offenders.append(d.document.id)
                continue
            projected.append(
                AnnotatedDocument(
                    document=d.document.model_copy(update={"text": new_text}),
                    spans=new_spans,
                )
            )
        if offenders:
            click.echo(
                f"Error: overlapping spans prevent surrogate alignment for "
                f"{len(offenders)} doc(s): {offenders[:10]}",
                err=True,
            )
            raise SystemExit(1)
        docs = projected

    if output_dir is None:
        if fmt != "brat":
            click.echo(
                f"Error: -o/--output is required for --format {fmt}.",
                err=True,
            )
            raise SystemExit(1)
        out_path = get_settings().exports_dir / name / "brat"
    else:
        out_path = Path(output_dir)

    try:
        if fmt == "brat":
            write_annotated_corpus(docs, brat_dir=out_path)
            path = out_path
        else:
            path = export_training_data(docs, out_path, fmt, filename=filename)
    except ImportError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)

    total_spans = sum(len(d.spans) for d in docs)
    click.echo(
        f"Exported {len(docs)} docs ({total_spans} spans) to {path}"
    )
