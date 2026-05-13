"""Deploy configuration API — manage modes.json from the playground UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from pypedeid.api.auth import require_admin, require_admin_or_inference
from pypedeid.config import get_settings
from pypedeid.deploy_health import pipeline_missing_deps
from pypedeid.mode_config import DeployConfig, ModeEntry, load_mode_config, save_mode_config
from pypedeid.pipeline_store import list_pipelines, load_pipeline_config

router = APIRouter(prefix="/deploy", tags=["deploy"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ModeEntrySchema(BaseModel):
    pipeline: str
    description: str = ""


class DeployConfigResponse(BaseModel):
    modes: dict[str, ModeEntrySchema]
    default_mode: str | None = None
    allowed_pipelines: list[str] | None = None


class UpdateDeployConfigRequest(BaseModel):
    modes: dict[str, ModeEntrySchema]
    default_mode: str | None = None
    allowed_pipelines: list[str] | None = None


class ModeHealth(BaseModel):
    name: str
    pipeline: str
    description: str = ""
    available: bool
    missing: list[str] = []


class DeployHealthResponse(BaseModel):
    modes: list[ModeHealth]
    default_mode: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _modes_path() -> Path:
    return get_settings().modes_path


@router.get("", response_model=DeployConfigResponse, dependencies=[require_admin])
def get_deploy_config() -> DeployConfigResponse:
    """Read the current deploy configuration (modes + allowlist)."""
    cfg = load_mode_config(_modes_path())
    return DeployConfigResponse(
        modes={
            name: ModeEntrySchema(pipeline=entry.pipeline, description=entry.description)
            for name, entry in cfg.modes.items()
        },
        default_mode=cfg.default_mode,
        allowed_pipelines=cfg.allowed_pipelines,
    )


@router.get("/health", response_model=DeployHealthResponse, dependencies=[require_admin_or_inference])
def get_deploy_health() -> DeployHealthResponse:
    """Report per-mode availability so the UI can gray out broken modes.

    For each mode, loads its pipeline config and walks the ``pipes`` list,
    reporting any uninstalled pipe types or missing models.
    """
    cfg = load_mode_config(_modes_path())
    pipelines_dir = get_settings().pipelines_dir
    out: list[ModeHealth] = []
    for name, entry in cfg.modes.items():
        try:
            pipeline_cfg = load_pipeline_config(pipelines_dir, entry.pipeline)
            missing = pipeline_missing_deps(pipeline_cfg)
        except FileNotFoundError:
            missing = [f"pipeline:{entry.pipeline}"]
        out.append(
            ModeHealth(
                name=name,
                pipeline=entry.pipeline,
                description=entry.description,
                available=not missing,
                missing=missing,
            )
        )
    out.sort(key=lambda m: m.name)
    return DeployHealthResponse(modes=out, default_mode=cfg.default_mode)


@router.get("/pipelines", response_model=list[str], dependencies=[require_admin])
def list_available_pipeline_names() -> list[str]:
    """List all saved pipeline names (for the UI to populate dropdowns)."""
    return [p.name for p in list_pipelines(get_settings().pipelines_dir)]


@router.put("", response_model=DeployConfigResponse, dependencies=[require_admin])
def update_deploy_config(body: UpdateDeployConfigRequest) -> DeployConfigResponse:
    """Write an updated deploy configuration."""
    modes = {
        name: ModeEntry(pipeline=entry.pipeline, description=entry.description)
        for name, entry in body.modes.items()
    }
    cfg = DeployConfig(
        modes=modes,
        default_mode=body.default_mode,
        allowed_pipelines=body.allowed_pipelines,
    )
    save_mode_config(cfg, _modes_path())
    return DeployConfigResponse(
        modes=body.modes,
        default_mode=body.default_mode,
        allowed_pipelines=body.allowed_pipelines,
    )
