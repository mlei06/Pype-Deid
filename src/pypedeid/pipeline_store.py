"""Filesystem-based pipeline store.

Pipelines are JSON files in the ``pipelines/`` directory.  A pipeline named
``"production-deid"`` lives at ``pipelines/production-deid.json``.

No database, no versioning — use git for history.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def _validate_name(name: str) -> None:
    """Reject names that could escape the target directory."""
    if not _SAFE_NAME.match(name) or ".." in name:
        raise ValueError(
            f"Invalid pipeline name {name!r}: must match {_SAFE_NAME.pattern} "
            f"and not contain '..'"
        )


@dataclass(frozen=True)
class PipelineInfo:
    """Metadata for a discovered pipeline file."""

    name: str
    path: Path
    config: dict[str, Any]


def _ensure_dir(pipelines_dir: Path) -> None:
    pipelines_dir.mkdir(parents=True, exist_ok=True)


def list_pipelines(pipelines_dir: Path) -> list[PipelineInfo]:
    """Return all ``*.json`` pipelines in *pipelines_dir*, sorted by name."""
    _ensure_dir(pipelines_dir)
    results: list[PipelineInfo] = []
    for p in sorted(pipelines_dir.glob("*.json")):
        try:
            config = json.loads(p.read_text(encoding="utf-8"))
            results.append(PipelineInfo(name=p.stem, path=p, config=config))
        except (json.JSONDecodeError, OSError):
            logger.warning("Skipping broken pipeline file: %s", p)
            continue
    return results


def load_pipeline_config(pipelines_dir: Path, name: str) -> dict[str, Any]:
    """Load a pipeline config by name.  Raises ``FileNotFoundError`` if missing."""
    _validate_name(name)
    path = pipelines_dir / f"{name}.json"
    if not path.is_file():
        available = [p.stem for p in pipelines_dir.glob("*.json")]
        raise FileNotFoundError(
            f"Pipeline {name!r} not found in {pipelines_dir}. "
            f"Available: {', '.join(sorted(available)) or '(none)'}"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def save_pipeline_config(
    pipelines_dir: Path,
    name: str,
    config: dict[str, Any],
) -> Path:
    """Write a pipeline config to ``pipelines/{name}.json``.  Returns the path."""
    _validate_name(name)
    _ensure_dir(pipelines_dir)
    path = pipelines_dir / f"{name}.json"
    path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def delete_pipeline(pipelines_dir: Path, name: str) -> None:
    """Delete a pipeline file.  Raises ``FileNotFoundError`` if missing."""
    _validate_name(name)
    path = pipelines_dir / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Pipeline {name!r} not found in {pipelines_dir}")
    path.unlink()


def rename_pipeline(pipelines_dir: Path, from_name: str, to_name: str) -> Path:
    """Move ``{from_name}.json`` to ``{to_name}.json`` (same config).

    Returns the new path. Raises ``FileNotFoundError`` if the source is missing;
    ``ValueError`` if the target name is invalid; ``FileExistsError`` if the
    destination already exists.
    """
    _validate_name(from_name)
    _validate_name(to_name)
    if from_name == to_name:
        p = pipelines_dir / f"{from_name}.json"
        if not p.is_file():
            raise FileNotFoundError(f"Pipeline {from_name!r} not found in {pipelines_dir}")
        return p
    _ensure_dir(pipelines_dir)
    old_path = pipelines_dir / f"{from_name}.json"
    new_path = pipelines_dir / f"{to_name}.json"
    if not old_path.is_file():
        raise FileNotFoundError(f"Pipeline {from_name!r} not found in {pipelines_dir}")
    if new_path.exists():
        raise FileExistsError(f"Pipeline {to_name!r} already exists in {pipelines_dir}")
    old_path.rename(new_path)
    return new_path
