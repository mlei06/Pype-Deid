"""Strategies for mapping :class:`~pypedeid.domain.AnnotatedDocument` ids to BRAT filenames."""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from pypedeid.domain import AnnotatedDocument


@runtime_checkable
class BratWriteStemStrategy(Protocol):
    """Given a document, return a filesystem-safe stem for ``{stem}.txt`` / ``{stem}.ann``."""

    def __call__(self, ad: AnnotatedDocument) -> str: ...


def sanitize_stem(stem: str, *, max_len: int = 200) -> str:
    """Allow word chars, hyphen, dot; replace other characters with underscore."""
    s = re.sub(r"[^\w\-.]", "_", stem.strip())
    s = s.strip("._") or "doc"
    return s[:max_len]


def default_brat_write_stem(ad: AnnotatedDocument) -> str:
    """
    Use ``document.id``, stripping a leading ``{split}__`` prefix when ``metadata['split']`` matches
    (typical after :func:`~pypedeid.ingest.brat.load_brat_corpus_with_splits`).
    """
    doc_id = ad.document.id
    split = ad.document.metadata.get("split")
    if isinstance(split, str) and doc_id.startswith(f"{split}__"):
        doc_id = doc_id[len(split) + 2 :]
    return sanitize_stem(doc_id)
