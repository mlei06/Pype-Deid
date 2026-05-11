"""Model directory scanner and registry.

Scans ``models/{framework}/{name}/model_manifest.json`` and provides lookup
for available NER models. No database — the filesystem is the registry.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SUPPORTED_FRAMEWORKS = ("spacy", "huggingface", "external", "neuroner")


@dataclass(frozen=True)
class ModelInfo:
    """Metadata for a discovered model."""

    name: str
    framework: str
    path: Path
    labels: list[str]
    description: str = ""
    base_model: str | None = None
    dataset: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    device: str = "cpu"
    created_at: str | None = None
    # v2 fields — all optional; absent on v1 manifests
    schema_version: int | None = None
    parent_model: str | None = None
    tokenizer: str | None = None
    has_crf: bool = False
    training_config: dict[str, Any] | None = None
    training_meta: dict[str, Any] = field(default_factory=dict)
    # Optional per-model raw→canonical label map. Models that already emit
    # canonical PHI labels (e.g. trained clinical checkpoints) leave this empty;
    # models with a foreign label taxonomy (e.g. openai-privacy-filter's
    # ``private_person``/``private_email``/...) declare the canonical projection
    # here so the pipe doesn't depend on every consumer remembering to populate
    # ``entity_map`` in the pipeline JSON.
    default_entity_map: dict[str, str] = field(default_factory=dict)


def _load_manifest(manifest_path: Path) -> ModelInfo:
    """Parse a single model_manifest.json into ModelInfo."""
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    model_dir = manifest_path.parent

    name = raw.get("name")
    if not name:
        raise ValueError(f"model_manifest.json missing 'name': {manifest_path}")

    framework = raw.get("framework")
    if not framework:
        raise ValueError(f"model_manifest.json missing 'framework': {manifest_path}")
    if framework not in SUPPORTED_FRAMEWORKS:
        raise ValueError(
            f"Unknown framework {framework!r} in {manifest_path}. "
            f"Supported: {', '.join(SUPPORTED_FRAMEWORKS)}"
        )

    labels = raw.get("labels")
    if not labels or not isinstance(labels, list):
        raise ValueError(f"model_manifest.json missing or invalid 'labels': {manifest_path}")

    if name != model_dir.name:
        raise ValueError(
            f"Manifest name {name!r} does not match directory name {model_dir.name!r}: {manifest_path}"
        )

    return ModelInfo(
        name=name,
        framework=framework,
        path=model_dir,
        labels=labels,
        description=raw.get("description", ""),
        base_model=raw.get("base_model"),
        dataset=raw.get("dataset"),
        metrics=raw.get("metrics", {}),
        device=raw.get("device", "cpu"),
        created_at=raw.get("created_at"),
        schema_version=raw.get("schema_version"),
        parent_model=raw.get("parent_model"),
        tokenizer=raw.get("tokenizer"),
        has_crf=raw.get("has_crf", False),
        training_config=raw.get("training_config"),
        training_meta=raw.get("training", {}),
        default_entity_map=dict(raw.get("default_entity_map") or {}),
    )


def scan_models(models_dir: Path) -> dict[str, ModelInfo]:
    """Walk models/{framework}/{name}/model_manifest.json and return {name: ModelInfo}."""
    result: dict[str, ModelInfo] = {}
    if not models_dir.is_dir():
        return result

    for framework_dir in sorted(models_dir.iterdir()):
        if not framework_dir.is_dir() or framework_dir.name.startswith("."):
            continue
        for model_dir in sorted(framework_dir.iterdir()):
            if not model_dir.is_dir() or model_dir.name.startswith("."):
                continue
            manifest = model_dir / "model_manifest.json"
            if not manifest.is_file():
                continue
            info = _load_manifest(manifest)
            if info.name in result:
                raise ValueError(
                    f"Duplicate model name {info.name!r}: "
                    f"{result[info.name].path} and {info.path}"
                )
            result[info.name] = info

    return result


def get_model(models_dir: Path, name: str) -> ModelInfo:
    """Look up a model by name. Raises KeyError if not found."""
    models = scan_models(models_dir)
    if name not in models:
        available = ", ".join(sorted(models)) or "(none)"
        raise KeyError(f"Model {name!r} not found. Available: {available}")
    return models[name]


def list_models(
    models_dir: Path, *, framework: str | None = None
) -> list[ModelInfo]:
    """List all available models, optionally filtered by framework."""
    models = scan_models(models_dir)
    items = list(models.values())
    if framework is not None:
        items = [m for m in items if m.framework == framework]
    return sorted(items, key=lambda m: (m.framework, m.name))
