"""Symmetric to :func:`~pypedeid.ingest.sources.load_annotated_corpus` — write ``AnnotatedDocument`` lists."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pypedeid.domain import AnnotatedDocument
from pypedeid.ids import BratWriteStemStrategy
from pypedeid.ingest.brat_write import (
    write_annotated_corpus_brat_flat,
    write_annotated_corpus_brat_split,
)


def write_annotated_corpus(
    docs: list[AnnotatedDocument],
    *,
    jsonl: Path | None = None,
    brat_dir: Path | None = None,
    brat_corpus: Path | None = None,
    stem_fn: Callable[[AnnotatedDocument], str] | BratWriteStemStrategy | None = None,
) -> None:
    """
    Persist documents to exactly one sink (mirrors the single-source rule on load).

    - ``jsonl``: one JSON object per line (:class:`~pypedeid.domain.AnnotatedDocument`).
    - ``brat_dir``: flat folder of ``.txt`` / ``.ann`` pairs.
    - ``brat_corpus``: split subfolders when ``metadata['split']`` is ``train``/``valid``/…; else files at root.
    """
    provided = sum(1 for x in (jsonl, brat_dir, brat_corpus) if x is not None)
    if provided != 1:
        raise ValueError("exactly one of jsonl, brat_dir, brat_corpus must be set")

    if jsonl is not None:
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        with jsonl.open("w", encoding="utf-8") as f:
            for d in docs:
                f.write(d.model_dump_json() + "\n")
        return

    if brat_dir is not None:
        write_annotated_corpus_brat_flat(docs, brat_dir, stem_fn=stem_fn)
        return

    assert brat_corpus is not None
    write_annotated_corpus_brat_split(docs, brat_corpus, stem_fn=stem_fn)
