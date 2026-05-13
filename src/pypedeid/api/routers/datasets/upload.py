"""Multipart JSONL upload → registered dataset (same as path-based import)."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from fastapi import File, Form, HTTPException, UploadFile

from pypedeid.api.routers.datasets import router
from pypedeid.api.routers.datasets.helpers import corpora_dir, manifest_to_detail
from pypedeid.api.routers.datasets.schemas import DatasetDetail
from pypedeid.dataset_store import import_jsonl_dataset, list_datasets
from pypedeid.ingest.production_export_jsonl import (
    production_export_bytes_to_annotated_jsonl_bytes,
)

logger = logging.getLogger(__name__)

def _parse_metadata_field(raw: str) -> dict[str, Any]:
    s = (raw or "").strip()
    if not s:
        return {}
    try:
        out = json.loads(s)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=422, detail=f"metadata must be valid JSON: {e}"
        ) from e
    if not isinstance(out, dict):
        raise HTTPException(status_code=422, detail="metadata must be a JSON object")
    return out  # type: ignore[return-value]


@router.post("/upload", response_model=DatasetDetail, status_code=201)
async def upload_dataset(
    name: str = Form(..., description="Dataset directory name (same rules as POST /datasets)."),
    file: UploadFile = File(
        ..., description="JSONL file (AnnotatedDocument per line, or production_v1 export)."
    ),
    description: str = Form(""),
    metadata: str = Form(""),
    line_format: str = Form(
        "annotated_jsonl",
        description="'annotated_jsonl' (default) or 'production_v1' (Production UI export).",
    ),
) -> DatasetDetail:
    """Upload a JSONL file and register it as a new dataset (multipart ``file`` on disk at API)."""
    if line_format not in ("annotated_jsonl", "production_v1"):
        raise HTTPException(
            status_code=422,
            detail="line_format must be 'annotated_jsonl' or 'production_v1'",
        )
    metadata_dict = _parse_metadata_field(metadata)
    ds_dir = corpora_dir()
    existing = [d.name for d in list_datasets(ds_dir)]
    if name in existing:
        raise HTTPException(status_code=409, detail=f"Dataset {name!r} already exists")

    body = await file.read()
    if not body or not body.strip():
        raise HTTPException(status_code=422, detail="uploaded file is empty")

    if line_format == "production_v1":
        try:
            body = production_export_bytes_to_annotated_jsonl_bytes(body)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Write to a temp file on the same filesystem as the corpora root, then reuse import_jsonl_dataset.
    corpora = ds_dir
    with tempfile.NamedTemporaryFile(
        mode="wb", suffix=".jsonl", delete=False, dir=corpora
    ) as tmp:
        tmp.write(body)
        tmp_path = tmp.name
    try:
        try:
            manifest = import_jsonl_dataset(
                ds_dir,
                name,
                tmp_path,
                description=description,
                metadata=metadata_dict,
            )
        except ValueError as exc:
            msg = str(exc)
            if "already exists" in msg:
                raise HTTPException(status_code=409, detail=msg) from exc
            raise HTTPException(status_code=422, detail=msg) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("upload import failed")
            raise HTTPException(
                status_code=500, detail=f"Failed to register dataset: {exc}"
            ) from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return manifest_to_detail(manifest)
