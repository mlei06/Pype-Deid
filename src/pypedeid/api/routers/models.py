"""Models HTTP API — read-only listing of models from the filesystem."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from pypedeid.api.auth import require_admin
from pypedeid.config import get_settings

router = APIRouter(prefix="/models", tags=["models"], dependencies=[require_admin])
logger = logging.getLogger(__name__)

# Module-level cache (refreshed on POST /models/refresh)
_model_cache: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ModelSummary(BaseModel):
    name: str
    framework: str
    labels: list[str]
    description: str
    base_model: str | None
    dataset: str | None
    device: str
    created_at: str | None


class ModelDetail(ModelSummary):
    path: str
    metrics: dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scan() -> dict[str, Any]:
    from pypedeid.models import scan_models

    settings = get_settings()
    return scan_models(settings.models_dir)


def _get_cache() -> dict[str, Any]:
    global _model_cache
    if _model_cache is None:
        _model_cache = _scan()
    return _model_cache


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ModelSummary])
def list_models(
    framework: str | None = Query(default=None),
) -> list[ModelSummary]:
    """List all models from the models directory."""
    cache = _get_cache()
    items = list(cache.values())
    if framework:
        items = [m for m in items if m.framework == framework]
    items.sort(key=lambda m: (m.framework, m.name))
    return [
        ModelSummary(
            name=m.name,
            framework=m.framework,
            labels=m.labels,
            description=m.description,
            base_model=m.base_model,
            dataset=m.dataset,
            device=m.device,
            created_at=m.created_at,
        )
        for m in items
    ]


@router.get("/{framework}/{name}", response_model=ModelDetail)
def get_model(framework: str, name: str) -> ModelDetail:
    """Get model manifest details."""
    cache = _get_cache()
    model = cache.get(name)
    if model is None or model.framework != framework:
        raise HTTPException(status_code=404, detail=f"model {framework}/{name} not found")
    return ModelDetail(
        name=model.name,
        framework=model.framework,
        labels=model.labels,
        description=model.description,
        base_model=model.base_model,
        dataset=model.dataset,
        device=model.device,
        created_at=model.created_at,
        path=str(model.path),
        metrics=model.metrics,
    )


@router.post("/refresh", response_model=list[ModelSummary], dependencies=[require_admin])
def refresh_models() -> list[ModelSummary]:
    """Re-scan the models directory (after dropping in a new model)."""
    global _model_cache
    _model_cache = _scan()
    items = sorted(_model_cache.values(), key=lambda m: (m.framework, m.name))
    return [
        ModelSummary(
            name=m.name,
            framework=m.framework,
            labels=m.labels,
            description=m.description,
            base_model=m.base_model,
            dataset=m.dataset,
            device=m.device,
            created_at=m.created_at,
        )
        for m in items
    ]
