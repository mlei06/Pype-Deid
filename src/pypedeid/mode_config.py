"""Deploy configuration — maps mode names (fast/balanced/accurate) to saved pipelines.

The mapping lives in a JSON file (default ``modes.json``; override with
``PYPEDEID_MODES_PATH`` / ``Settings.modes_path``).
Operators may edit it on the instance or use the Playground **Deploy** view / ``PUT /deploy``;
each request reloads the file (no in-memory cache).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_MODES_PATH = Path("data/modes.json")


@dataclass(frozen=True)
class ModeEntry:
    pipeline: str
    description: str = ""


@dataclass(frozen=True)
class DeployConfig:
    """Full deployment configuration: modes + allowlist."""

    modes: dict[str, ModeEntry] = field(default_factory=dict)
    default_mode: str | None = None
    allowed_pipelines: list[str] | None = None  # None = all allowed

    def resolve(self, mode_or_pipeline: str) -> str:
        """Return the pipeline name for a mode alias, or pass through as-is."""
        entry = self.modes.get(mode_or_pipeline)
        if entry is not None:
            return entry.pipeline
        return mode_or_pipeline

    def is_pipeline_allowed(self, name: str) -> bool:
        """Check if a pipeline is allowed in production."""
        if self.allowed_pipelines is None:
            return True
        return name in self.allowed_pipelines

    def mode_names(self) -> list[str]:
        return sorted(self.modes)


def load_mode_config(path: Path = DEFAULT_MODES_PATH) -> DeployConfig:
    """Load mode mapping from a JSON file.  Returns an empty config if the file is missing."""
    if not path.exists():
        logger.warning("mode config %s not found — no mode aliases available", path)
        return DeployConfig()

    with open(path) as f:
        raw = json.load(f)

    modes: dict[str, ModeEntry] = {}
    for name, entry in raw.get("modes", {}).items():
        if isinstance(entry, str):
            modes[name] = ModeEntry(pipeline=entry)
        else:
            modes[name] = ModeEntry(
                pipeline=entry["pipeline"],
                description=entry.get("description", ""),
            )

    return DeployConfig(
        modes=modes,
        default_mode=raw.get("default_mode"),
        allowed_pipelines=raw.get("allowed_pipelines"),
    )


def save_mode_config(config: DeployConfig, path: Path = DEFAULT_MODES_PATH) -> None:
    """Write the deploy config back to disk."""
    raw: dict = {
        "modes": {
            name: {"pipeline": entry.pipeline, "description": entry.description}
            for name, entry in config.modes.items()
        },
        "default_mode": config.default_mode,
    }
    if config.allowed_pipelines is not None:
        raw["allowed_pipelines"] = config.allowed_pipelines

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(raw, f, indent=2)
        f.write("\n")
