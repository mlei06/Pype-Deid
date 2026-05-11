"""List datasets, enumerate import sources, import JSONL/BRAT, ingest-from-pipeline."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import HTTPException, Query

from clinical_deid.api.routers.datasets import router
from clinical_deid.api.routers.datasets.helpers import (
    corpora_dir,
    info_to_summary,
    manifest_to_detail,
    resolve_source_under_corpora,
)
from clinical_deid.api.routers.datasets.schemas import (
    BratImportCandidate,
    BratImportSourcesResponse,
    DatasetDetail,
    DatasetSummary,
    ImportBratRequest,
    ImportSourceCandidate,
    ImportSourcesResponse,
    RefreshResultResponse,
    RegisterDatasetRequest,
)
from clinical_deid.api.schemas import (
    IngestFromPipelineRequest,
    IngestFromPipelineResponse,
)
from clinical_deid.dataset_store import (
    CORPUS_JSONL_NAME,
    commit_colocated_dataset,
    import_brat_to_jsonl,
    import_jsonl_dataset,
    list_brat_import_candidates,
    list_datasets,
    list_import_candidates,
    refresh_all_datasets,
    validate_name as validate_dataset_name,
)

logger = logging.getLogger(__name__)


@router.get("", response_model=list[DatasetSummary])
def list_all_datasets(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[DatasetSummary]:
    """List registered datasets."""
    datasets = list_datasets(corpora_dir())
    datasets = datasets[offset : offset + limit]
    return [info_to_summary(d) for d in datasets]


@router.get("/import-sources", response_model=ImportSourcesResponse)
def list_dataset_import_sources() -> ImportSourcesResponse:
    """List JSONL files under the configured corpora root (BRAT candidates are separate)."""
    root = corpora_dir().resolve()
    raw = list_import_candidates(root)
    return ImportSourcesResponse(
        corpora_root=str(root),
        candidates=[ImportSourceCandidate.model_validate(x) for x in raw],
    )


@router.get("/import-sources/brat", response_model=BratImportSourcesResponse)
def list_brat_dataset_import_sources() -> BratImportSourcesResponse:
    """List BRAT directories under the corpora root (candidates for ``POST /datasets/import/brat``)."""
    root = corpora_dir().resolve()
    raw = list_brat_import_candidates(root)
    return BratImportSourcesResponse(
        corpora_root=str(root),
        candidates=[BratImportCandidate.model_validate(x) for x in raw],
    )


def _register_jsonl(body: RegisterDatasetRequest) -> DatasetDetail:
    ds_dir = corpora_dir()

    try:
        validate_dataset_name(body.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if body.format != "jsonl":
        raise HTTPException(
            status_code=422,
            detail=(
                "Only format='jsonl' is supported via POST /datasets. "
                "Use POST /datasets/import/brat to convert a BRAT tree into a JSONL dataset."
            ),
        )

    existing = [d.name for d in list_datasets(ds_dir)]
    if body.name in existing:
        raise HTTPException(status_code=409, detail=f"Dataset {body.name!r} already exists")

    resolved = resolve_source_under_corpora(body.data_path)

    try:
        manifest = import_jsonl_dataset(
            ds_dir,
            body.name,
            str(resolved),
            description=body.description,
            metadata=body.metadata,
        )
    except ValueError as exc:
        msg = str(exc)
        if "already exists" in msg:
            raise HTTPException(status_code=409, detail=msg) from exc
        raise HTTPException(status_code=422, detail=msg) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to register dataset: {exc}") from exc

    return manifest_to_detail(manifest)


@router.post("", response_model=DatasetDetail, status_code=201)
def register_new_dataset(body: RegisterDatasetRequest) -> DatasetDetail:
    """Import a JSONL corpus into a new dataset home and compute analytics."""
    return _register_jsonl(body)


@router.post("/import/jsonl", response_model=DatasetDetail, status_code=201)
def import_jsonl_dataset_route(body: RegisterDatasetRequest) -> DatasetDetail:
    """Alias of ``POST /datasets`` — explicit name for the JSONL import path."""
    return _register_jsonl(body)


@router.post("/import/brat", response_model=DatasetDetail, status_code=201)
def import_brat_dataset_route(body: ImportBratRequest) -> DatasetDetail:
    """Convert a BRAT tree (flat or split) into a new JSONL dataset home."""
    ds_dir = corpora_dir()

    try:
        validate_dataset_name(body.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = [d.name for d in list_datasets(ds_dir)]
    if body.name in existing:
        raise HTTPException(status_code=409, detail=f"Dataset {body.name!r} already exists")

    resolved = resolve_source_under_corpora(body.brat_path)

    try:
        manifest = import_brat_to_jsonl(
            ds_dir,
            body.name,
            resolved,
            description=body.description,
            metadata=body.metadata,
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to import BRAT: {exc}") from exc

    return manifest_to_detail(manifest)


@router.post("/refresh-all", response_model=list[RefreshResultResponse])
def refresh_all_datasets_route() -> list[RefreshResultResponse]:
    """Refresh analytics for every discovered dataset; per-home errors are surfaced inline."""
    results = refresh_all_datasets(corpora_dir())
    return [
        RefreshResultResponse(name=r.name, status=r.status, error=r.error) for r in results
    ]


@router.post(
    "/ingest-from-pipeline",
    response_model=IngestFromPipelineResponse,
    status_code=201,
)
def ingest_from_pipeline(body: IngestFromPipelineRequest) -> IngestFromPipelineResponse:
    """Run a saved pipeline over raw text under the corpora root and register the result."""
    from clinical_deid.audit import log_run
    from clinical_deid.ingest.from_batch import ingest_paths_with_pipeline
    from clinical_deid.ingest.sink import write_annotated_corpus

    ds_dir = corpora_dir()

    try:
        validate_dataset_name(body.output_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = [d.name for d in list_datasets(ds_dir)]
    if body.output_name in existing:
        raise HTTPException(
            status_code=409, detail=f"Dataset {body.output_name!r} already exists"
        )

    resolved = resolve_source_under_corpora(body.source_path)

    t0 = time.perf_counter()
    docs: list[Any] = []
    try:
        for doc in ingest_paths_with_pipeline(
            [resolved], pipeline_name=body.pipeline_name
        ):
            docs.append(doc)
            if len(docs) > body.max_documents:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"source_path produced more than max_documents={body.max_documents} "
                        "documents; narrow the source or raise the cap."
                    ),
                )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    duration = time.perf_counter() - t0

    if not docs:
        raise HTTPException(
            status_code=422,
            detail=f"No documents produced from {body.source_path!r}",
        )

    home = ds_dir / body.output_name
    home.mkdir(parents=True)
    try:
        write_annotated_corpus(docs, jsonl=home / CORPUS_JSONL_NAME)
        manifest = commit_colocated_dataset(
            ds_dir,
            body.output_name,
            "jsonl",
            description=body.description or f"Ingested via pipeline {body.pipeline_name!r}",
            metadata={
                "provenance": {
                    "ingested_from": str(resolved),
                    "pipeline_name": body.pipeline_name,
                }
            },
        )
    except Exception:
        import shutil
        if home.is_dir():
            shutil.rmtree(home)
        raise

    total_spans = sum(len(d.spans) for d in docs)
    try:
        log_run(
            command="dataset_ingest",
            pipeline_name=body.pipeline_name,
            dataset_source=str(resolved),
            doc_count=len(docs),
            error_count=0,
            span_count=total_spans,
            duration_seconds=duration,
            source="api-admin",
        )
    except Exception:
        logger.warning("Failed to write audit record", exc_info=True)

    return IngestFromPipelineResponse(
        name=manifest["name"],
        document_count=int(manifest.get("document_count", len(docs))),
        total_spans=int(manifest.get("total_spans", total_spans)),
    )
