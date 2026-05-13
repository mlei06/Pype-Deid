"""Shared helpers for CLI commands."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import click

from pypedeid.domain import AnnotatedDocument, Document, EntitySpan, tag_replace
from pypedeid.export import ProcessedResult

logger = logging.getLogger(__name__)


def build_pipeline(
    profile: str,
    config_path: str | None,
    pipeline_name: str | None,
) -> tuple[Any, dict[str, Any], str]:
    """Return ``(pipe_chain, config_dict, resolved_pipeline_name)``."""
    from pypedeid.pipes.registry import load_pipeline

    resolved_name = ""

    if pipeline_name:
        from pypedeid.config import get_settings
        from pypedeid.pipeline_store import load_pipeline_config

        try:
            config = load_pipeline_config(get_settings().pipelines_dir, pipeline_name)
        except FileNotFoundError as exc:
            click.echo(f"Error: {exc}", err=True)
            raise SystemExit(1)
        resolved_name = pipeline_name
    elif config_path:
        config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        resolved_name = Path(config_path).stem
    else:
        from pypedeid.profiles import get_profile_config

        config = get_profile_config(profile)
        resolved_name = f"profile:{profile}"

    try:
        pipeline = load_pipeline(config)
    except RuntimeError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)

    return pipeline, config, resolved_name


def apply_output_mode(text: str, spans: list[EntitySpan], output_mode: str) -> str:
    """Apply the requested output mode to produce final text."""
    if output_mode == "annotated":
        return text

    if output_mode == "surrogate":
        from pypedeid.pipes.surrogate.strategies import SurrogateGenerator

        gen = SurrogateGenerator()
        sorted_spans = sorted(spans, key=lambda s: s.start, reverse=True)
        result = text
        for s in sorted_spans:
            original = text[s.start : s.end]
            replacement = gen.replace(s.label, original)
            result = result[: s.start] + replacement + result[s.end :]
        return result

    return tag_replace(text, spans)


def process_doc(
    pipeline: Any,
    doc_id: str,
    text: str,
    output_mode: str,
) -> ProcessedResult:
    """Run pipeline on one document and return a ProcessedResult."""
    doc = AnnotatedDocument(document=Document(id=doc_id, text=text), spans=[])
    out = pipeline.forward(doc)

    output_text = apply_output_mode(text, out.spans, output_mode)

    return ProcessedResult(
        doc_id=doc_id,
        original_text=text,
        output_text=output_text,
        spans=[s.model_dump() for s in out.spans],
        metadata={},
    )


def corpora_dir() -> Path:
    from pypedeid.config import get_settings

    return get_settings().corpora_dir


def models_dir() -> Path:
    from pypedeid.config import get_settings

    return get_settings().models_dir


def dict_store():
    from pypedeid.config import get_settings
    from pypedeid.dictionary_store import DictionaryStore

    return DictionaryStore(get_settings().dictionaries_dir)
