"""POST /datasets/preview-labels — gold label set from a JSONL under corpora (eval path mode)."""

from __future__ import annotations

from fastapi import HTTPException

from pypedeid.api.routers.datasets import router
from pypedeid.api.routers.datasets.helpers import resolve_source_under_corpora
from pypedeid.api.routers.datasets.schemas import (
    PreviewCorpusLabelsRequest,
    PreviewCorpusLabelsResponse,
)
from pypedeid.dataset_store import unique_labels_for_jsonl_corpus


@router.post(
    "/preview-labels",
    response_model=PreviewCorpusLabelsResponse,
    summary="List unique gold labels in a JSONL (under corpora root)",
)
def preview_corpus_labels(body: PreviewCorpusLabelsRequest) -> PreviewCorpusLabelsResponse:
    """Scan *body.path* the same way eval does: load annotated JSONL and return unique span labels.

    The path is scoped to the corpora directory (``PYPEDEID_CORPORA_DIR``) like
    ``POST /eval/run`` with ``dataset_path``.
    """
    resolved = resolve_source_under_corpora(body.path)
    if resolved.suffix.lower() != ".jsonl":
        raise HTTPException(
            status_code=422,
            detail="path must be a .jsonl file (use POST /datasets/import/brat to convert BRAT).",
        )
    labels, document_count = unique_labels_for_jsonl_corpus(resolved)
    return PreviewCorpusLabelsResponse(
        labels=labels,
        document_count=document_count,
        resolved_path=str(resolved),
    )
