"""Root CLI group and top-level commands: run, batch, eval, setup, serve."""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import click

from pypedeid.cli._common import (
    build_pipeline,
    process_doc,
)
from pypedeid.domain import EntitySpan
from pypedeid.export import ProcessedResult

logger = logging.getLogger(__name__)


@click.group()
@click.version_option(package_name="pypedeid")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
def main(verbose: bool) -> None:
    """Clinical de-identification toolkit."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


@main.command()
@click.option(
    "--profile",
    "-p",
    type=click.Choice(["fast", "balanced", "accurate"]),
    default="balanced",
    show_default=True,
    help="Pipeline profile (speed vs accuracy trade-off).",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True),
    default=None,
    help="Custom pipeline JSON (overrides --profile).",
)
@click.option(
    "--pipeline",
    "pipeline_name",
    default=None,
    help="Name of a saved pipeline (overrides --profile and --config).",
)
@click.option(
    "--output-mode",
    type=click.Choice(["redacted", "surrogate", "annotated"]),
    default="redacted",
    show_default=True,
    help="redacted=[LABEL] tags, surrogate=fake data, annotated=original text.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "jsonl"]),
    default="text",
    show_default=True,
)
@click.argument("files", nargs=-1, type=click.Path(exists=True))
def run(
    profile: str,
    config_path: str | None,
    pipeline_name: str | None,
    output_mode: str,
    output_format: str,
    files: tuple[str, ...],
) -> None:
    """De-identify text from stdin or files.

    \b
    Examples:
      echo "Patient John Smith DOB 01/15/1980" | pypedeid run
      pypedeid run notes.txt
      pypedeid run --pipeline my-pipeline notes.txt
      pypedeid run --profile fast --output-mode surrogate notes.txt
    """
    if output_mode == "surrogate":
        from pypedeid.pipes.registry import registered_pipes

        if "surrogate" not in registered_pipes():
            click.echo(
                "Error: --output-mode surrogate requires the faker library.\n"
                "Install it with:  pip install 'pypedeid[scripts]'",
                err=True,
            )
            raise SystemExit(1)

    pipeline, config, resolved_name = build_pipeline(
        profile, config_path, pipeline_name
    )

    texts: list[tuple[str, str]] = []
    if files:
        for f in files:
            p = Path(f)
            texts.append((p.stem, p.read_text(encoding="utf-8")))
    else:
        if sys.stdin.isatty():
            click.echo("Reading from stdin (Ctrl+D to end)...", err=True)
        texts.append(("stdin", sys.stdin.read()))

    t0 = time.perf_counter()
    results = [process_doc(pipeline, doc_id, text, output_mode) for doc_id, text in texts]
    duration = time.perf_counter() - t0

    from pypedeid.export import to_json, to_jsonl, to_text

    if output_format == "text":
        click.echo(to_text(results))
    elif output_format == "json":
        click.echo(to_json(results))
    elif output_format == "jsonl":
        click.echo(to_jsonl(results))

    total_spans = sum(len(r.spans) for r in results)
    try:
        from pypedeid.audit import log_run

        log_run(
            command="run",
            pipeline_name=resolved_name,
            pipeline_config=config,
            doc_count=len(texts),
            error_count=0,
            span_count=total_spans,
            duration_seconds=duration,
            source="cli",
        )
    except Exception:
        logger.warning("Failed to write audit record", exc_info=True)


# ---------------------------------------------------------------------------
# batch
# ---------------------------------------------------------------------------


@main.command()
@click.argument("input_path", type=click.Path(exists=True))
@click.option("-o", "--output", "output_dir", type=click.Path(), required=True)
@click.option(
    "--profile",
    "-p",
    type=click.Choice(["fast", "balanced", "accurate"]),
    default="balanced",
    show_default=True,
)
@click.option(
    "--pipeline",
    "pipeline_name",
    default=None,
    help="Name of a saved pipeline (overrides --profile and --config).",
)
@click.option(
    "--on-error",
    type=click.Choice(["skip", "fail"]),
    default="skip",
    show_default=True,
    help="skip=log error and continue, fail=abort on first error.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "jsonl", "csv", "parquet"]),
    default="text",
    show_default=True,
)
@click.option(
    "--output-mode",
    type=click.Choice(["redacted", "surrogate", "annotated"]),
    default="redacted",
    show_default=True,
)
@click.option("--config", "config_path", type=click.Path(exists=True), default=None)
def batch(
    input_path: str,
    output_dir: str,
    profile: str,
    pipeline_name: str | None,
    on_error: str,
    output_format: str,
    output_mode: str,
    config_path: str | None,
) -> None:
    """Process a directory of .txt files or a JSONL file.

    \b
    Examples:
      pypedeid batch notes_dir/ -o output/ --on-error skip
      pypedeid batch corpus.jsonl -o output/ --format jsonl
      pypedeid batch notes_dir/ -o output/ --pipeline my-pipeline
    """
    pipeline, config, resolved_name = build_pipeline(
        profile, config_path, pipeline_name
    )

    inp = Path(input_path)
    texts: list[tuple[str, str]] = []
    if inp.is_dir():
        for f in sorted(inp.glob("*.txt")):
            texts.append((f.stem, f.read_text(encoding="utf-8")))
    elif inp.suffix == ".jsonl":
        with open(inp, encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if not line.strip():
                    continue
                obj = json.loads(line)
                doc_id = obj.get("id") or obj.get("document", {}).get("id") or f"line_{i}"
                text = obj.get("text") or obj.get("document", {}).get("text", "")
                texts.append((str(doc_id), text))
    else:
        texts.append((inp.stem, inp.read_text(encoding="utf-8")))

    if not texts:
        click.echo("No documents found.", err=True)
        raise SystemExit(1)

    click.echo(f"Processing {len(texts)} document(s)...", err=True)

    from pypedeid.export import write_results

    t0 = time.perf_counter()
    results: list[ProcessedResult] = []
    errors: list[dict[str, Any]] = []

    for doc_id, text in texts:
        try:
            results.append(process_doc(pipeline, doc_id, text, output_mode))
        except Exception as exc:
            if on_error == "fail":
                raise
            logger.warning("Error processing %s: %s", doc_id, exc)
            errors.append({"doc_id": doc_id, "error": str(exc)})

    duration = time.perf_counter() - t0

    out = Path(output_dir)
    write_results(results, out, output_format)

    if errors:
        errors_path = out / "errors.jsonl"
        errors_path.write_text(
            "\n".join(json.dumps(e) for e in errors) + "\n", encoding="utf-8"
        )

    click.echo(
        f"Done: {len(results)} processed, {len(errors)} errors, "
        f"{duration:.1f}s total",
        err=True,
    )

    total_spans = sum(len(r.spans) for r in results)
    try:
        from pypedeid.audit import log_run

        log_run(
            command="batch",
            pipeline_name=resolved_name,
            pipeline_config=config,
            dataset_source=input_path,
            doc_count=len(results),
            error_count=len(errors),
            span_count=total_spans,
            duration_seconds=duration,
            source="cli",
        )
    except Exception:
        logger.warning("Failed to write audit record", exc_info=True)


# ---------------------------------------------------------------------------
# eval
# ---------------------------------------------------------------------------


@main.command(name="eval")
@click.option(
    "--corpus",
    required=False,
    type=click.Path(exists=True),
    default=None,
    help="Gold-standard corpus (JSONL only). Use exactly one of --corpus or --dataset.",
)
@click.option(
    "--dataset",
    "dataset_name",
    required=False,
    default=None,
    help="Registered dataset name (see: pypedeid dataset list). Use exactly one of --corpus or --dataset.",
)
@click.option(
    "--dataset-splits",
    "dataset_splits_raw",
    default=None,
    help="Comma-separated document splits to include (metadata['split']). Applies to --corpus or --dataset.",
)
@click.option(
    "--profile",
    "-p",
    type=click.Choice(["fast", "balanced", "accurate"]),
    default="balanced",
    show_default=True,
)
@click.option(
    "--pipeline",
    "pipeline_name",
    default=None,
    help="Name of a saved pipeline (overrides --profile and --config).",
)
@click.option("--config", "config_path", type=click.Path(exists=True), default=None)
@click.option(
    "--confidence-threshold",
    type=float,
    default=0.5,
    show_default=True,
    help="Flag spans below this confidence.",
)
@click.option(
    "--risk-profile",
    "risk_profile_name",
    default=None,
    help=(
        "Risk profile for risk-weighted recall (overrides PYPEDEID_RISK_PROFILE_NAME). "
        "Built-ins: clinical_phi, generic_pii."
    ),
)
def eval_cmd(
    corpus: str | None,
    dataset_name: str | None,
    dataset_splits_raw: str | None,
    profile: str,
    pipeline_name: str | None,
    config_path: str | None,
    confidence_threshold: float,
    risk_profile_name: str | None,
) -> None:
    """Evaluate pipeline against a gold-standard corpus.

    Shows strict, partial-overlap, and token-level metrics plus risk-weighted
    recall and HIPAA coverage gaps.

    \b
    Examples:
      pypedeid eval --corpus data.jsonl --profile fast
      pypedeid eval --corpus data.jsonl --pipeline my-pipeline
      pypedeid eval --dataset eval-gold --pipeline my-pipeline
    """
    from pypedeid.eval.runner import evaluate_pipeline
    from pypedeid.ingest.sources import load_annotated_corpus
    from pypedeid.risk import default_risk_profile, get_risk_profile
    from pypedeid.transform.ops import filter_documents_by_split_query

    if (corpus is None) == (dataset_name is None):
        raise click.UsageError("Provide exactly one of --corpus PATH or --dataset NAME.")

    split_list: list[str] | None = None
    if dataset_splits_raw:
        split_list = [p.strip() for p in dataset_splits_raw.split(",") if p.strip()]

    def _source_with_splits(base: str) -> str:
        if not split_list:
            return base
        norm = sorted(set(split_list))
        return f"{base}:splits={'+'.join(norm)}"

    dataset_source: str
    if dataset_name:
        from pypedeid.config import get_settings
        from pypedeid.dataset_store import load_dataset_documents

        try:
            golds = load_dataset_documents(get_settings().corpora_dir, dataset_name)
        except FileNotFoundError as exc:
            click.echo(f"Error: {exc}", err=True)
            raise SystemExit(1)
        dataset_source = _source_with_splits(f"dataset:{dataset_name}")
    else:
        corpus_path = Path(corpus)  # type: ignore[arg-type]
        if corpus_path.suffix.lower() != ".jsonl":
            click.echo(
                f"Error: --corpus must be a .jsonl file (got {corpus_path.name!r}). "
                "Convert BRAT trees first with:  "
                "pypedeid dataset import-brat <path> --name <name>",
                err=True,
            )
            raise SystemExit(1)
        golds = load_annotated_corpus(jsonl=corpus_path)
        dataset_source = _source_with_splits(str(corpus_path.resolve()))

    if split_list:
        golds = filter_documents_by_split_query(golds, split_list)
        if not golds:
            click.echo(
                "No documents match --dataset-splits; check metadata['split'] on documents.",
                err=True,
            )
            raise SystemExit(1)

    if not golds:
        click.echo("No documents in corpus.", err=True)
        raise SystemExit(1)

    click.echo(f"Evaluating on {len(golds)} document(s)...", err=True)

    pipeline, config, resolved_name = build_pipeline(
        profile, config_path, pipeline_name
    )

    if risk_profile_name:
        try:
            eval_risk_profile = get_risk_profile(risk_profile_name)
        except KeyError as exc:
            click.echo(f"Error: {exc}", err=True)
            raise SystemExit(1) from exc
    else:
        eval_risk_profile = default_risk_profile()

    click.echo(f"Risk profile: {eval_risk_profile.name}", err=True)

    t0 = time.perf_counter()
    result = evaluate_pipeline(pipeline, golds, risk_profile=eval_risk_profile)
    duration = time.perf_counter() - t0

    click.echo("")
    header = f"{'Label':<20} {'Prec':>8} {'Recall':>8} {'F1':>8} {'TP':>6} {'FP':>6} {'FN':>6} {'Support':>8}"
    click.echo(header)
    click.echo("-" * len(header))
    for label in sorted(result.per_label):
        lm = result.per_label[label]
        s = lm.strict
        click.echo(
            f"{label:<20} {s.precision:>8.4f} {s.recall:>8.4f} {s.f1:>8.4f} "
            f"{s.tp:>6} {s.fp:>6} {s.fn:>6} {lm.support:>8}"
        )
    click.echo("-" * len(header))
    o = result.overall
    click.echo(
        f"{'MICRO (all)':<20} {o.strict.precision:>8.4f} {o.strict.recall:>8.4f} {o.strict.f1:>8.4f} "
        f"{o.strict.tp:>6} {o.strict.fp:>6} {o.strict.fn:>6}"
    )

    click.echo(f"\n{'Matching mode':<25} {'Prec':>8} {'Recall':>8} {'F1':>8}")
    click.echo("-" * 51)
    for mode_name, mr in [
        ("Strict", o.strict),
        ("Partial overlap", o.partial_overlap),
        ("Token-level", o.token_level),
        ("Exact boundary", o.exact_boundary),
    ]:
        click.echo(f"{mode_name:<25} {mr.precision:>8.4f} {mr.recall:>8.4f} {mr.f1:>8.4f}")
    click.echo(f"\n  Risk-weighted recall:  {result.risk_weighted_recall:.4f}")

    pipeline_labels: set[str] = set()
    for lm in result.per_label.values():
        pipeline_labels.add(lm.label)
    profile = default_risk_profile()
    coverage = profile.coverage_report(pipeline_labels)
    uncovered = [
        (key, profile.identifier_name(key))
        for key, status in coverage.items()
        if status == "uncovered"
    ]
    label_prefix = profile.name
    if uncovered:
        click.echo(f"\n  Coverage gaps [{label_prefix}] ({len(uncovered)} uncovered):")
        for key, name in uncovered:
            key_str = f"#{key}" if isinstance(key, int) else str(key)
            click.echo(f"    {key_str}: {name}")
    else:
        click.echo(f"\n  Coverage [{label_prefix}]: all applicable identifiers covered")

    low_conf: list[tuple[str, EntitySpan]] = []
    for dr in result.document_results:
        for span in dr.false_positives:
            if span.confidence is not None and span.confidence < confidence_threshold:
                low_conf.append((dr.document_id, span))
    if low_conf:
        click.echo(f"\n  Low-confidence false positives (conf < {confidence_threshold}): {len(low_conf)} flagged")
        for doc_id, span in low_conf[:20]:
            click.echo(
                f"    doc {doc_id!r}: [{span.start}:{span.end}] "
                f"({span.label}, conf={span.confidence:.2f}, src={span.source})"
            )
        if len(low_conf) > 20:
            click.echo(f"    ... and {len(low_conf) - 20} more")

    worst = result.document_results[:3]
    if worst and worst[0].metrics.strict.f1 < 1.0:
        click.echo("\n  Worst documents (by strict F1):")
        for dr in worst:
            click.echo(
                f"    {dr.document_id}: F1={dr.metrics.strict.f1:.4f}  "
                f"FN={len(dr.false_negatives)}  FP={len(dr.false_positives)}  "
                f"risk_recall={dr.risk_weighted_recall:.4f}"
            )

    click.echo(f"\nEval completed in {duration:.1f}s on {result.document_count} doc(s).")

    try:
        from pypedeid.config import get_settings
        from pypedeid.eval.metrics_json import build_persisted_eval_metrics
        from pypedeid.eval_store import save_eval_result

        metrics = build_persisted_eval_metrics(
            result, risk_profile_name=eval_risk_profile.name
        )
        out_path = save_eval_result(
            get_settings().evaluations_dir,
            pipeline_name=resolved_name,
            dataset_source=dataset_source,
            metrics=metrics,
            document_count=result.document_count,
        )
        click.echo(f"Saved eval result: {out_path}", err=True)
    except Exception:
        logger.warning("Failed to save eval result JSON to evaluations dir", exc_info=True)

    try:
        from pypedeid.audit import log_run

        log_run(
            command="eval",
            pipeline_name=resolved_name,
            pipeline_config=config,
            dataset_source=dataset_source,
            doc_count=result.document_count,
            error_count=0,
            span_count=o.strict.tp + o.strict.fp,
            duration_seconds=duration,
            metrics={
                "strict_precision": o.strict.precision,
                "strict_recall": o.strict.recall,
                "strict_f1": o.strict.f1,
                "partial_f1": o.partial_overlap.f1,
                "token_f1": o.token_level.f1,
                "risk_weighted_recall": result.risk_weighted_recall,
            },
            source="cli",
        )
    except Exception:
        logger.warning("Failed to write audit record", exc_info=True)


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------


@main.command()
@click.option("--check", is_flag=True, help="Verify dependencies without installing.")
def setup(check: bool) -> None:
    """Interactive setup: verify dependencies, download models, initialize database.

    \b
    Steps:
      1. Check Python version (require 3.11+)
      2. Check/install spaCy model (en_core_web_sm)
      3. Check Presidio availability
      4. Create .env from .env.example if missing
      5. Initialize SQLite database
      6. Smoke test (run RegexNER on sample text)
    """
    import shutil
    import subprocess

    ok_count = 0
    fail_count = 0

    def status(name: str, ok: bool, detail: str = "") -> None:
        nonlocal ok_count, fail_count
        symbol = "OK" if ok else "FAIL"
        msg = f"  [{symbol}] {name}"
        if detail:
            msg += f" — {detail}"
        click.echo(msg)
        if ok:
            ok_count += 1
        else:
            fail_count += 1

    click.echo("PypeDeid — Setup\n")

    py_ok = sys.version_info >= (3, 11)
    status(
        "Python version",
        py_ok,
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        + ("" if py_ok else " (need 3.11+)"),
    )

    try:
        import spacy

        try:
            spacy.load("en_core_web_sm")
            status("spaCy en_core_web_sm", True, "loaded")
        except OSError:
            if check:
                status("spaCy en_core_web_sm", False, "not installed")
            else:
                click.echo("  Downloading en_core_web_sm...")
                result = subprocess.run(
                    [sys.executable, "-m", "spacy", "download", "en_core_web_sm"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    status("spaCy en_core_web_sm", True, "downloaded")
                else:
                    status("spaCy en_core_web_sm", False, "download failed")
    except ImportError:
        status("spaCy", False, "not installed (pip install '.[ner]')")

    try:
        import presidio_analyzer  # noqa: F401

        status("Presidio analyzer", True, "installed")
    except ImportError:
        status("Presidio analyzer", False, "not installed (pip install '.[presidio]')")

    env_path = Path(".env")
    example_path = Path(".env.example")
    if env_path.exists():
        status(".env file", True, "exists")
    elif example_path.exists() and not check:
        shutil.copy2(example_path, env_path)
        status(".env file", True, "created from .env.example")
    elif example_path.exists():
        status(".env file", False, "missing (run without --check to create)")
    else:
        status(".env file", False, "no .env.example found")

    if not check:
        try:
            from pypedeid.db import init_db

            init_db()
            status("SQLite database", True, "initialized")
        except Exception as exc:
            status("SQLite database", False, str(exc))
    else:
        from pypedeid.config import get_settings

        settings = get_settings()
        db_path = settings.sqlite_path
        if db_path and db_path.exists():
            status("SQLite database", True, f"exists at {db_path}")
        else:
            status("SQLite database", False, "not initialized (run without --check)")

    if not check:
        try:
            from pypedeid.domain import AnnotatedDocument, Document
            from pypedeid.pipes.registry import load_pipe

            pipe = load_pipe({"type": "regex_ner"})
            doc = AnnotatedDocument(
                document=Document(id="smoke", text="Patient John Smith DOB 01/15/1980"),
                spans=[],
            )
            result = pipe.forward(doc)
            if result.spans:
                status("Smoke test", True, f"RegexNER found {len(result.spans)} span(s)")
            else:
                status("Smoke test", True, "RegexNER ran (0 spans — patterns may not match sample)")
        except Exception as exc:
            status("Smoke test", False, str(exc))
    else:
        status("Smoke test", True, "skipped in --check mode")

    click.echo(f"\n{ok_count} passed, {fail_count} failed")
    if fail_count > 0:
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# serve
# ---------------------------------------------------------------------------


@main.command()
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind address.")
@click.option("--port", "-p", default=8000, show_default=True, type=int, help="Port number.")
@click.option("--reload", "do_reload", is_flag=True, help="Enable auto-reload for development.")
@click.option("--workers", default=1, show_default=True, type=int, help="Number of worker processes.")
def serve(host: str, port: int, do_reload: bool, workers: int) -> None:
    """Start the FastAPI server (uvicorn).

    \b
    Examples:
      pypedeid serve
      pypedeid serve --port 9000 --reload
      pypedeid serve --host 0.0.0.0 --workers 4
    """
    try:
        import uvicorn
    except ImportError:
        click.echo(
            "uvicorn is required to serve the API. Install with:\n"
            "  pip install uvicorn[standard]",
            err=True,
        )
        raise SystemExit(1)

    click.echo(f"Starting server on {host}:{port}...", err=True)
    uvicorn.run(
        "pypedeid.api.app:app",
        host=host,
        port=port,
        reload=do_reload,
        workers=workers,
    )
