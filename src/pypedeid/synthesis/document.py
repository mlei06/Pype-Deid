"""Build :class:`~pypedeid.domain.AnnotatedDocument` from LLM synthesis output."""

from __future__ import annotations

from typing import Any

from pypedeid.domain import AnnotatedDocument, Document, EntitySpan
from pypedeid.synthesis.align import drop_overlapping_spans, phi_dict_to_spans
from pypedeid.synthesis.types import SynthesisResult


def synthesis_result_to_annotated_document(
    result: SynthesisResult,
    *,
    document_id: str,
    align_spans: bool = True,
    drop_overlapping: bool = True,
    span_source: str = "llm_phi_dict",
    metadata: dict[str, Any] | None = None,
) -> AnnotatedDocument:
    """
    Convert parsed synthesis into the core domain type.

    When ``align_spans`` is True, runs :func:`~pypedeid.synthesis.align.phi_dict_to_spans`
    and optionally :func:`~pypedeid.synthesis.align.drop_overlapping_spans` so
    :class:`~pypedeid.domain.AnnotatedDocument` validation passes. Surfaces that are not
    found verbatim in the note are skipped. The full ``phi_entities`` dict is always copied into
    ``document.metadata['phi_entities']`` for audit.
    """
    meta: dict[str, Any] = dict(metadata or {})
    meta["phi_entities"] = dict(result.phi_entities)
    if result.raw_completion is not None:
        meta.setdefault("llm_raw_completion", result.raw_completion)

    text = result.clinical_note
    spans: list[EntitySpan] = []
    if align_spans and result.phi_entities and text:
        spans = phi_dict_to_spans(text, result.phi_entities, source=span_source)
        if drop_overlapping:
            spans = drop_overlapping_spans(spans)
        n = len(text)
        spans = [s for s in spans if 0 <= s.start < s.end <= n]

    doc = Document(id=document_id, text=text, metadata=meta)
    return AnnotatedDocument(document=doc, spans=spans)
