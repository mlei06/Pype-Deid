"""Dictionary CRUD — upload, list, get, delete term-list files.

Whitelist and blacklist each use a flat pool of files under ``dictionaries/``.
Dictionary names (file stems) are selected per NER label in the whitelist pipe
config; the optional ``label`` query parameter is accepted for API compatibility
and is ignored.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from clinical_deid.api.auth import require_admin
from clinical_deid.api.schemas import (
    DictionaryInfoResponse,
    DictionaryPreviewResponse,
    DictionaryTermsPageResponse,
    DictionaryTermsResponse,
    DictionaryUploadResponse,
)
from clinical_deid.config import get_settings
from clinical_deid.dictionary_store import DictionaryStore, DictKind

router = APIRouter(prefix="/dictionaries", tags=["dictionaries"], dependencies=[require_admin])

MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MB


def _store() -> DictionaryStore:
    return DictionaryStore(get_settings().dictionaries_dir)


def _info_response(info) -> DictionaryInfoResponse:
    return DictionaryInfoResponse(
        kind=info.kind,
        label=info.label,
        name=info.name,
        filename=info.filename,
        term_count=info.term_count,
    )


@router.get("", response_model=list[DictionaryInfoResponse])
def list_dictionaries(
    kind: Annotated[DictKind | None, Query()] = None,
    label: Annotated[str | None, Query()] = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[DictionaryInfoResponse]:
    """List stored dictionaries (paginated), optionally filtered by kind."""
    items = _store().list_dictionaries(kind=kind, label=label)
    items = items[offset : offset + limit]
    return [_info_response(d) for d in items]


@router.get("/{kind}/{name}", response_model=DictionaryTermsResponse)
def get_dictionary(
    kind: DictKind,
    name: str,
    label: Annotated[str | None, Query()] = None,
) -> DictionaryTermsResponse:
    """Get a dictionary's terms by kind and name."""
    try:
        terms = _store().get_terms(kind, name, label=label)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DictionaryTermsResponse(
        kind=kind,
        label=label.upper() if label else None,
        name=name,
        terms=terms,
        term_count=len(terms),
    )


@router.get("/{kind}/{name}/preview", response_model=DictionaryPreviewResponse)
def get_dictionary_preview(
    kind: DictKind,
    name: str,
    label: Annotated[str | None, Query()] = None,
) -> DictionaryPreviewResponse:
    """Get a dictionary preview with sample terms and metadata."""
    try:
        data = _store().get_preview(kind, name, label=label)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DictionaryPreviewResponse(**data)


@router.get("/{kind}/{name}/terms", response_model=DictionaryTermsPageResponse)
def get_dictionary_terms_paginated(
    kind: DictKind,
    name: str,
    label: Annotated[str | None, Query()] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    search: Annotated[str | None, Query()] = None,
) -> DictionaryTermsPageResponse:
    """Get paginated terms from a dictionary with optional text search."""
    try:
        data = _store().get_terms_paginated(kind, name, label=label, offset=offset, limit=limit, search=search)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DictionaryTermsPageResponse(**data)


@router.post("", response_model=DictionaryUploadResponse, status_code=201, dependencies=[require_admin])
async def upload_dictionary(
    file: Annotated[UploadFile, File()],
    kind: Annotated[DictKind, Form()],
    name: Annotated[str, Form()],
    label: Annotated[str | None, Form()] = None,
) -> DictionaryUploadResponse:
    """Upload a dictionary file (txt, csv, or json)."""
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"file exceeds {MAX_UPLOAD_BYTES // 1024} KB limit",
        )
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="file is not valid UTF-8") from exc

    # Determine extension from uploaded filename
    filename = file.filename or "upload.txt"
    ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".txt"
    if ext not in (".txt", ".csv", ".json"):
        ext = ".txt"

    try:
        info = _store().save(kind, name, content, label=label, extension=ext)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return DictionaryUploadResponse(
        info=_info_response(info),
        message=f"Saved {info.term_count} terms to {info.kind}/{info.filename}",
    )


@router.delete("/{kind}/{name}", status_code=204, dependencies=[require_admin])
def delete_dictionary(
    kind: DictKind,
    name: str,
    label: Annotated[str | None, Query()] = None,
) -> None:
    """Delete a dictionary by kind and name."""
    try:
        _store().delete(kind, name, label=label)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
