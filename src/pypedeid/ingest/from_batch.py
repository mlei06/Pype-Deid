"""Run a saved pipeline across raw inputs to produce ``AnnotatedDocument`` records.

The on-ramp for turning a folder of ``.txt`` files (or a plain JSONL of
``{id, text}`` rows) into a registered dataset without writing code.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Literal

from pypedeid.domain import AnnotatedDocument, Document
from pypedeid.pipes.base import Pipe


def batch_to_annotated_docs(
    inputs: Iterable[tuple[str, str]],
    *,
    pipeline: Pipe,
) -> Iterator[AnnotatedDocument]:
    """Apply *pipeline* to each ``(doc_id, text)`` pair and yield results."""
    for doc_id, text in inputs:
        doc = AnnotatedDocument(document=Document(id=doc_id, text=text), spans=[])
        yield pipeline.forward(doc)


def _iter_text_inputs(path: Path) -> Iterator[tuple[str, str]]:
    """Yield ``(doc_id, text)`` pairs for a file or directory of ``.txt`` / ``.jsonl``."""
    if path.is_dir():
        for p in sorted(path.glob("*.txt")):
            yield p.stem, p.read_text(encoding="utf-8")
        return

    if path.suffix.lower() == ".jsonl":
        with path.open(encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if not line.strip():
                    continue
                obj = json.loads(line)
                doc_id = (
                    obj.get("id")
                    or obj.get("document", {}).get("id")
                    or f"{path.stem}_line_{i}"
                )
                text = obj.get("text") or obj.get("document", {}).get("text", "")
                yield str(doc_id), text
        return

    # Single text file
    yield path.stem, path.read_text(encoding="utf-8")


def ingest_paths_with_pipeline(
    paths: Sequence[Path],
    *,
    pipeline_name: str,
    output_mode: Literal["annotated"] = "annotated",  # kept for future redactor support
) -> Iterator[AnnotatedDocument]:
    """Stream documents produced by running *pipeline_name* across *paths*.

    ``paths`` may mix directories of ``.txt``, single ``.txt`` files, and JSONL
    files of ``{id, text}`` / ``{document: {id, text}}`` rows.
    """
    from pypedeid.config import get_settings
    from pypedeid.pipeline_store import load_pipeline_config
    from pypedeid.pipes.registry import load_pipeline

    del output_mode  # reserved for future surrogate output support

    config = load_pipeline_config(get_settings().pipelines_dir, pipeline_name)
    pipeline = load_pipeline(config)

    def _iter_all() -> Iterator[tuple[str, str]]:
        for p in paths:
            yield from _iter_text_inputs(p)

    yield from batch_to_annotated_docs(_iter_all(), pipeline=pipeline)
