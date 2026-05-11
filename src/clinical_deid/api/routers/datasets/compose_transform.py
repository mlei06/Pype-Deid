"""Compose + transform (preview and materialize) endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Response

from clinical_deid.api.routers.datasets import router
from clinical_deid.api.routers.datasets.helpers import (
    corpora_dir,
    manifest_to_detail,
)
from clinical_deid.api.routers.datasets.schemas import (
    ComposeRequest,
    DatasetDetail,
    TransformPreviewRequest,
    TransformPreviewResponse,
    TransformRequest,
)
from clinical_deid.config import get_settings
from clinical_deid.dataset_store import (
    CORPUS_JSONL_NAME,
    commit_colocated_dataset,
    list_datasets,
    load_dataset_documents,
    load_dataset_manifest,
    validate_name as validate_dataset_name,
)


@router.post("/compose", response_model=DatasetDetail, status_code=201)
def compose_datasets(body: ComposeRequest) -> DatasetDetail:
    """Compose multiple datasets into a new registered dataset.

    Strategies:
    - **merge**: concatenate in order
    - **interleave**: round-robin across sources
    - **proportional**: weighted sampling (requires ``weights``)
    """
    from clinical_deid.compose.pipeline import compose_corpora
    from clinical_deid.ingest.sink import write_annotated_corpus

    corp = corpora_dir()

    existing = [d.name for d in list_datasets(corp)]
    if body.output_name in existing:
        raise HTTPException(status_code=409, detail=f"Dataset {body.output_name!r} already exists")

    source_docs: list[list[Any]] = []
    for src_name in body.source_datasets:
        try:
            docs = load_dataset_documents(corp, src_name)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Source dataset {src_name!r} not found")
        if not docs:
            raise HTTPException(status_code=422, detail=f"Source dataset {src_name!r} is empty")
        source_docs.append(docs)

    if body.strategy == "proportional" and body.weights:
        if len(body.weights) != len(body.source_datasets):
            raise HTTPException(
                status_code=422,
                detail=f"weights length ({len(body.weights)}) must match source_datasets length ({len(body.source_datasets)})",
            )

    composed = compose_corpora(
        source_docs,
        strategy=body.strategy,
        weights=body.weights,
        target_documents=body.target_documents,
        seed=body.seed,
        shuffle=body.shuffle,
    )

    if not composed:
        raise HTTPException(status_code=422, detail="Composition produced no documents")

    settings = get_settings()
    try:
        validate_dataset_name(body.output_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    home = settings.corpora_dir / body.output_name
    home.mkdir(parents=True)
    output_path = home / CORPUS_JSONL_NAME
    write_annotated_corpus(composed, jsonl=output_path)

    provenance = {
        "composed_from": body.source_datasets,
        "strategy": body.strategy,
        "weights": body.weights,
        "target_documents": body.target_documents,
        "seed": body.seed,
        "shuffle": body.shuffle,
    }
    manifest = commit_colocated_dataset(
        settings.corpora_dir,
        body.output_name,
        "jsonl",
        description=body.description or f"Composed from: {', '.join(body.source_datasets)}",
        metadata={"provenance": provenance},
    )
    return manifest_to_detail(manifest)


@router.post("/transform/preview", response_model=TransformPreviewResponse)
def preview_transform_dataset(body: TransformPreviewRequest) -> TransformPreviewResponse:
    """Dry-run transform: span keep/drop/rename counts and projected corpus size."""
    from clinical_deid.transform.ops import compute_transform_preview, get_work_and_rest

    corp = corpora_dir()
    try:
        all_docs = load_dataset_documents(corp, body.source_dataset)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Source dataset {body.source_dataset!r} not found",
        ) from None
    if not all_docs:
        raise HTTPException(
            status_code=422,
            detail=f"Source dataset {body.source_dataset!r} is empty",
        )

    work, rest = get_work_and_rest(all_docs, body.source_splits)
    if body.source_splits and any(str(s).strip() for s in body.source_splits) and not work:
        raise HTTPException(
            status_code=422,
            detail=(
                f"No documents match source_splits for dataset {body.source_dataset!r}; "
                "set metadata['split'] on documents or adjust the filter."
            ),
        )

    try:
        raw = compute_transform_preview(
            work,
            drop_labels=body.drop_labels,
            keep_labels=body.keep_labels,
            label_mapping=body.label_mapping,
            target_documents=body.target_documents,
            boost_label=body.boost_label,
            boost_extra_copies=body.boost_extra_copies,
            resplit=body.resplit,
            strip_splits=body.strip_splits,
            seed=body.seed,
            transform_mode=body.transform_mode,
            resplit_shuffle=body.resplit_shuffle,
            flatten_before_resplit=body.flatten_target_splits,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    n_rest = len(rest)
    raw["untouched_document_count"] = n_rest
    # In-place: output corpus includes untouched splits (merge). New dataset with source_splits:
    # output is the filtered work set only.
    has_split_filter = body.source_splits and any(
        str(s).strip() for s in (body.source_splits or [])
    )
    if body.in_place or not has_split_filter:
        raw["projected_document_count"] = int(raw["projected_document_count"]) + n_rest
    return TransformPreviewResponse(**raw)


@router.post("/transform", response_model=DatasetDetail, status_code=201)
def transform_dataset(
    body: TransformRequest, response: Response
) -> DatasetDetail:
    """Apply transforms to a dataset and register the result (new dataset) or update in place.

    Available transforms (applied in order):
    1. **drop_labels** / **keep_labels** — filter spans by label
    2. **label_mapping** — rename labels (e.g. ``{"DOCTOR": "PERSON"}``)
    3. **target_documents** — resize corpus to exact document count
    4. **boost_label** + **boost_extra_copies** — oversample docs with a rare label
    5. **resplit** — reassign train/valid/test splits (e.g. ``{"train": 0.7, "valid": 0.15, "test": 0.15}``)
    6. **strip_splits** — remove split metadata for flat corpus

    Set **in_place** to true to write back to the source dataset (same name and path); new datasets require a unique
    **output_name** when in_place is false.
    """
    from clinical_deid.ingest.sink import write_annotated_corpus
    from clinical_deid.transform.ops import get_work_and_rest, merge_rest_work, run_transform_by_mode

    corp = corpora_dir()

    if not body.in_place and not (body.output_name and str(body.output_name).strip()):
        raise HTTPException(
            status_code=422,
            detail="output_name is required when not transforming in place",
        )
    out_name = body.source_dataset if body.in_place else str(body.output_name).strip()
    if not out_name and body.in_place:
        raise HTTPException(status_code=422, detail="source_dataset is required for in-place transform")

    try:
        validate_dataset_name(out_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = [d.name for d in list_datasets(corp)]
    if not body.in_place and out_name in existing:
        raise HTTPException(status_code=409, detail=f"Dataset {out_name!r} already exists")

    try:
        all_docs = load_dataset_documents(corp, body.source_dataset)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Source dataset {body.source_dataset!r} not found")

    if not all_docs:
        raise HTTPException(status_code=422, detail=f"Source dataset {body.source_dataset!r} is empty")

    work, rest = get_work_and_rest(all_docs, body.source_splits)
    if body.source_splits and any(str(s).strip() for s in body.source_splits) and not work:
        raise HTTPException(
            status_code=422,
            detail=(
                f"No documents match source_splits for dataset {body.source_dataset!r}; "
                "set metadata['split'] on documents or adjust the filter."
            ),
        )

    try:
        work_out = run_transform_by_mode(
            work,
            body.transform_mode,
            drop_labels=body.drop_labels,
            keep_labels=body.keep_labels,
            label_mapping=body.label_mapping,
            target_documents=body.target_documents,
            boost_label=body.boost_label,
            boost_extra_copies=body.boost_extra_copies,
            resplit=body.resplit,
            strip_splits=body.strip_splits,
            seed=body.seed,
            resplit_shuffle=body.resplit_shuffle,
            flatten_before_resplit=body.flatten_target_splits,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    has_split_filter = body.source_splits and any(
        str(s).strip() for s in (body.source_splits or [])
    )
    if not body.in_place and has_split_filter:
        # New dataset: source_splits limits which documents appear in the output (sub-corpus).
        transformed = work_out
    else:
        # In-place, or no split filter: full corpus; non-work docs pass through unchanged.
        transformed = merge_rest_work(rest, work_out)

    if not transformed:
        raise HTTPException(status_code=422, detail="Transform produced no documents")

    settings = get_settings()
    home = settings.corpora_dir / out_name
    if not body.in_place:
        home.mkdir(parents=True)
    else:
        if not home.is_dir() or not (home / CORPUS_JSONL_NAME).is_file():
            raise HTTPException(
                status_code=404,
                detail=f"Cannot transform in place: dataset {out_name!r} has no corpus on disk",
            )
    output_path = home / CORPUS_JSONL_NAME
    write_annotated_corpus(transformed, jsonl=output_path)

    transform_provenance: dict[str, Any] = {"transformed_from": body.source_dataset}
    for field in (
        "source_splits",
        "drop_labels", "keep_labels", "label_mapping", "target_documents",
        "boost_label", "boost_extra_copies", "resplit", "strip_splits", "seed",
    ):
        val = getattr(body, field)
        if val and val != 0:
            transform_provenance[field] = val
    if body.transform_mode != "full":
        transform_provenance["transform_mode"] = body.transform_mode
    if not body.resplit_shuffle:
        transform_provenance["resplit_shuffle"] = False
    if body.flatten_target_splits:
        transform_provenance["flatten_target_splits"] = True
    transform_provenance["in_place"] = body.in_place

    if body.in_place:
        existing = load_dataset_manifest(corp, out_name)
        old_desc = (existing.get("description") or "") if isinstance(existing, dict) else ""
        if body.description and str(body.description).strip():
            desc = str(body.description).strip()
        else:
            desc = old_desc
        old_meta: dict[str, Any] = {}
        if isinstance(existing, dict) and existing.get("metadata") and isinstance(
            existing.get("metadata"), dict
        ):
            old_meta = dict(existing["metadata"])
        old_prov = old_meta.get("provenance")
        if not isinstance(old_prov, dict):
            old_prov = {}
        new_meta: dict[str, Any] = {
            **old_meta,
            "provenance": {**old_prov, "last_transform": transform_provenance, "transformed_in_place": True},
        }
        manifest = commit_colocated_dataset(
            settings.corpora_dir,
            out_name,
            "jsonl",
            description=desc,
            metadata=new_meta,
        )
        response.status_code = 200
    else:
        manifest = commit_colocated_dataset(
            settings.corpora_dir,
            out_name,
            "jsonl",
            description=body.description or f"Transformed from: {body.source_dataset}",
            metadata={"provenance": transform_provenance},
        )
        response.status_code = 201
    return manifest_to_detail(manifest)
