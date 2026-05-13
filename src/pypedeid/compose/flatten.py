"""Normalize corpus layout: strip folder-based ``split``, namespace document ids."""

from __future__ import annotations

from pypedeid.domain import AnnotatedDocument, Document


def flatten_annotated_document(
    ad: AnnotatedDocument,
    *,
    new_id: str,
    source_index: int,
    provenance: bool = True,
) -> AnnotatedDocument:
    """
    Copy document for a flat merged corpus: drop ``metadata[\"split\"]`` (train/valid/test layout).

    When ``provenance`` is True, stores ``compose_source_index``, ``compose_original_id``, and
    ``compose_original_split`` (if the input had a split).
    """
    meta = dict(ad.document.metadata)
    orig_id = ad.document.id
    split_was = meta.pop("split", None)

    if provenance:
        meta["compose_source_index"] = source_index
        meta["compose_original_id"] = orig_id
        if split_was is not None:
            meta["compose_original_split"] = split_was

    doc = Document(id=new_id, text=ad.document.text, metadata=meta)
    spans = [s.model_copy() for s in ad.spans]
    return AnnotatedDocument(document=doc, spans=spans)


def flatten_corpus(
    docs: list[AnnotatedDocument],
    source_index: int,
    *,
    id_prefix: str,
    provenance: bool = True,
) -> list[AnnotatedDocument]:
    """Flatten every document in one source block (same ``source_index`` / id namespace)."""
    prefix = f"{id_prefix}{source_index}__"
    return [
        flatten_annotated_document(
            ad,
            new_id=f"{prefix}{ad.document.id}",
            source_index=source_index,
            provenance=provenance,
        )
        for ad in docs
    ]
