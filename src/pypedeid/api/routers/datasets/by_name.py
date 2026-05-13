"""Per-dataset endpoints — CRUD, analytics, preview, document access, export.

These are all mounted under ``/datasets/{name}...`` so this module must be
imported **after** any module that registers literal fixed paths, otherwise
FastAPI's ordered path matcher will swallow them into ``/{name}``.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Query

from pypedeid.analytics.stats import DatasetAnalytics, compute_dataset_analytics
from pypedeid.api.routers.datasets import router
from pypedeid.api.routers.datasets.helpers import (
    corpora_dir,
    manifest_to_detail,
    parse_splits_query,
    surrogate_project_docs,
)
from pypedeid.api.routers.datasets.schemas import (
    DatasetDetail,
    DatasetLabelFrequency,
    DatasetPreviewResponse,
    DatasetSchemaResponse,
    DocumentPreview,
    ExportTrainingRequest,
    ExportTrainingResponse,
    UpdateDatasetRequest,
    UpdateDocumentRequest,
    UpdateDocumentResponse,
)
from pypedeid.config import get_settings
from pypedeid.dataset_store import (
    delete_dataset,
    load_dataset_documents,
    load_dataset_manifest,
    refresh_analytics,
    save_dataset_manifest,
)


@router.get("/{name}", response_model=DatasetDetail)
def get_dataset(name: str) -> DatasetDetail:
    """Get full dataset metadata and analytics."""
    try:
        manifest = load_dataset_manifest(corpora_dir(), name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if manifest.get("format") != "jsonl":
        raise HTTPException(
            status_code=404,
            detail=(
                f"Dataset {name!r} uses a legacy on-disk format. "
                "Re-import as JSONL (e.g. POST /datasets/import/brat) or remove the directory."
            ),
        )
    return manifest_to_detail(manifest)


@router.put("/{name}", response_model=DatasetDetail)
def update_dataset(name: str, body: UpdateDatasetRequest) -> DatasetDetail:
    """Update description or metadata (does not re-scan data)."""
    ds_dir = corpora_dir()
    try:
        manifest = load_dataset_manifest(ds_dir, name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if body.description is not None:
        manifest["description"] = body.description
    if body.metadata is not None:
        manifest["metadata"] = body.metadata

    save_dataset_manifest(ds_dir, name, manifest)
    return manifest_to_detail(manifest)


@router.delete("/{name}", status_code=204)
def remove_dataset(name: str) -> None:
    """Delete the dataset directory (manifest and corpus files under ``corpora_dir/name/``)."""
    try:
        delete_dataset(corpora_dir(), name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{name}/schema", response_model=DatasetSchemaResponse)
def get_dataset_schema(name: str) -> DatasetSchemaResponse:
    """Return label frequencies for schema discovery (dropdowns, chips).

    Uses cached manifest analytics when available; otherwise loads documents once
    to compute ``label_counts``.
    """
    ds_dir = corpora_dir()
    try:
        manifest = load_dataset_manifest(ds_dir, name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    analytics_blob = manifest.get("analytics") or {}
    label_counts: dict[str, int] = dict(analytics_blob.get("label_counts") or {})
    if not label_counts and manifest.get("total_spans", 0) > 0:
        try:
            docs = load_dataset_documents(ds_dir, name)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to load dataset for schema: {exc}",
            ) from exc
        label_counts = dict(compute_dataset_analytics(docs).label_counts)

    ordered = sorted(label_counts.items(), key=lambda x: (-x[1], x[0]))
    labels = [DatasetLabelFrequency(label=k, count=v) for k, v in ordered]
    return DatasetSchemaResponse(
        dataset=name,
        document_count=int(manifest.get("document_count", 0)),
        total_spans=int(manifest.get("total_spans", 0)),
        labels=labels,
    )


@router.post("/{name}/refresh", response_model=DatasetDetail)
def refresh_dataset_analytics(name: str) -> DatasetDetail:
    """Reload data from disk and recompute cached analytics."""
    try:
        manifest = refresh_analytics(corpora_dir(), name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to refresh analytics: {exc}") from exc
    return manifest_to_detail(manifest)


@router.get("/{name}/analytics", response_model=DatasetAnalytics)
def get_dataset_subset_analytics(
    name: str,
    split: str | None = Query(
        default=None,
        description="Omit for whole-corpus stats. A split name, or (none) for documents without split.",
    ),
) -> DatasetAnalytics:
    """Recompute dataset-level analytics for the whole corpus or one split bucket."""
    from pypedeid.transform.ops import filter_documents_by_split_query

    try:
        docs = load_dataset_documents(corpora_dir(), name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if split is not None and str(split).strip() != "":
        docs = filter_documents_by_split_query(docs, [str(split).strip()])
    return compute_dataset_analytics(docs)


@router.get("/{name}/preview", response_model=DatasetPreviewResponse)
def preview_dataset(
    name: str,
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    splits: str | None = Query(
        default=None,
        description="Comma-separated split names; omit for all. Use (none) for documents without split.",
    ),
) -> DatasetPreviewResponse:
    """Preview documents from a dataset (paginated, optional split filter)."""
    from pypedeid.transform.ops import filter_documents_by_split_query

    try:
        docs = load_dataset_documents(corpora_dir(), name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load dataset: {exc}") from exc

    wanted = parse_splits_query(splits)
    filtered = filter_documents_by_split_query(docs, wanted)
    total = len(filtered)
    page = filtered[offset : offset + limit]
    max_text = 500
    items: list[DocumentPreview] = []
    for d in page:
        sp = d.document.metadata.get("split")
        split_out = sp.strip() if isinstance(sp, str) and sp.strip() else None
        items.append(
            DocumentPreview(
                document_id=d.document.id,
                text_preview=d.document.text[:max_text] + ("..." if len(d.document.text) > max_text else ""),
                span_count=len(d.spans),
                labels=sorted(set(s.label for s in d.spans)),
                split=split_out,
            )
        )
    return DatasetPreviewResponse(items=items, total=total)


@router.get("/{name}/documents/{doc_id}")
def get_document(name: str, doc_id: str) -> dict[str, Any]:
    """Return a single document with full text and spans."""
    try:
        docs = load_dataset_documents(corpora_dir(), name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    for d in docs:
        if d.document.id == doc_id:
            return {
                "document_id": d.document.id,
                "text": d.document.text,
                "metadata": d.document.metadata,
                "spans": [s.model_dump() for s in d.spans],
            }
    raise HTTPException(status_code=404, detail=f"Document {doc_id!r} not found in dataset {name!r}")


@router.put(
    "/{name}/documents/{doc_id}",
    response_model=UpdateDocumentResponse,
)
def update_document_route(
    name: str, doc_id: str, body: UpdateDocumentRequest
) -> UpdateDocumentResponse:
    """Replace a document's spans (and optionally text). Rewrites ``corpus.jsonl`` atomically."""
    from pypedeid.dataset_store import update_document as store_update_document

    try:
        updated = store_update_document(
            corpora_dir(),
            name,
            doc_id,
            spans=body.spans,
            text=body.text,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Document {doc_id!r} not found in dataset {name!r}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return UpdateDocumentResponse(
        document_id=updated.document.id,
        text=updated.document.text,
        metadata=updated.document.metadata,
        spans=[s.model_dump() for s in updated.spans],
    )


@router.post("/{name}/export", response_model=ExportTrainingResponse, status_code=200)
def export_dataset(name: str, body: ExportTrainingRequest) -> ExportTrainingResponse:
    """Export a registered dataset to a downstream format.

    - ``conll`` / ``spacy`` / ``huggingface`` / ``jsonl``: training / annotated formats
    - ``brat``: flat BRAT folder of ``.txt`` / ``.ann`` pairs (for external tools)

    Output goes under ``$EXPORTS_DIR/{name}/`` — kept out of ``$CORPORA_DIR`` so the
    corpora root stays canonical (JSONL only).

    Pass ``target_text="surrogate"`` to write surrogate-aligned text/spans instead
    of the original corpus text. Set ``surrogate_seed`` for determinism.
    """
    from pypedeid.ingest.sink import write_annotated_corpus
    from pypedeid.training_export import export_training_data

    ds_dir = corpora_dir()
    try:
        docs = load_dataset_documents(ds_dir, name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not docs:
        raise HTTPException(status_code=422, detail=f"Dataset {name!r} has no documents")

    if body.target_text == "surrogate":
        docs = surrogate_project_docs(docs, seed=body.surrogate_seed)

    output_dir = get_settings().exports_dir / name
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        if body.format == "brat":
            write_annotated_corpus(docs, brat_dir=output_dir)
            path: Any = output_dir
        else:
            path = export_training_data(docs, output_dir, body.format, filename=body.filename)
    except ImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    total_spans = sum(len(d.spans) for d in docs)
    return ExportTrainingResponse(
        path=str(path),
        format=body.format,
        document_count=len(docs),
        total_spans=total_spans,
        target_text=body.target_text,
    )
