"""Shared helpers for computing per-mode availability.

Used by the deploy router (``/deploy/health``) to report which configured
modes can actually serve requests given current pipe installs and model
availability.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pypedeid.mode_config import DeployConfig
from pypedeid.pipeline_store import load_pipeline_config
from pypedeid.pipes.registry import pipe_availability, pipe_dependencies


def pipeline_missing_deps(config: dict[str, Any]) -> list[str]:
    """Return missing dependency tags for a pipeline config.

    Each ``pipes`` entry is checked for: registration, install/ready status,
    and any per-pipe dependency hook declared on the catalog
    (``dependencies_fn``). Returns tags like ``"pipe:foo"``
    (uninstalled / not ready) and ``"model:bar"`` (from the pipe's own
    dependency check).
    """
    avail = {entry["name"]: entry for entry in pipe_availability()}
    missing: list[str] = []
    for pipe in config.get("pipes", []) or []:
        pipe_type = pipe.get("type")
        if not pipe_type:
            continue
        info = avail.get(pipe_type)
        if info is None or not info.get("installed") or not info.get("ready", True):
            missing.append(f"pipe:{pipe_type}")
            continue
        missing.extend(pipe_dependencies(pipe_type, pipe.get("config") or {}))
    return missing


def mode_missing_deps(
    cfg: DeployConfig,
    pipelines_dir: Path,
    mode_name: str,
) -> list[str]:
    """Missing dep tags for a single mode.

    Returns ``["mode:<name>"]`` if the mode is not in the config,
    ``["pipeline:<name>"]`` if the backing pipeline file is missing, else the
    union of missing-pipe/missing-dep tags for every step in the pipeline.
    """
    entry = cfg.modes.get(mode_name)
    if entry is None:
        return [f"mode:{mode_name}"]
    try:
        pipeline_cfg = load_pipeline_config(pipelines_dir, entry.pipeline)
    except FileNotFoundError:
        return [f"pipeline:{entry.pipeline}"]
    return pipeline_missing_deps(pipeline_cfg)
