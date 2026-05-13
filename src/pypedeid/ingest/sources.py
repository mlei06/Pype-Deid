"""Load ``list[AnnotatedDocument]`` from JSONL or BRAT paths (shared by CLI scripts)."""

from __future__ import annotations

from pathlib import Path

from pypedeid.domain import AnnotatedDocument
from pypedeid.ingest.brat import load_brat_corpus_with_splits, load_brat_directory
from pypedeid.ingest.jsonl import load_annotated_documents_from_jsonl_bytes


def load_annotated_corpus(
    *,
    jsonl: Path | None = None,
    brat_dir: Path | None = None,
    brat_corpus: Path | None = None,
) -> list[AnnotatedDocument]:
    """Exactly one of the path arguments must be set."""
    provided = sum(
        1 for x in (jsonl, brat_dir, brat_corpus) if x is not None
    )
    if provided != 1:
        raise ValueError("exactly one of jsonl, brat_dir, brat_corpus must be set")

    if jsonl is not None:
        return load_annotated_documents_from_jsonl_bytes(jsonl.read_bytes())
    if brat_dir is not None:
        return load_brat_directory(brat_dir)
    assert brat_corpus is not None
    return load_brat_corpus_with_splits(brat_corpus)
