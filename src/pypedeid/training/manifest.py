"""Write model_manifest.json v2 for trained model directories."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_manifest_v2(
    model_dir: Path,
    *,
    name: str,
    base_model: str,
    parent_model_name: str | None,
    tokenizer_source: str,
    labels: list[str],
    bio_labels: list[str],
    training_config: dict[str, Any],
    train_dataset: str,
    train_documents: int,
    eval_dataset: str | None,
    eval_fraction: float | None,
    eval_documents: int,
    seed: int,
    device_used: str,
    total_steps: int,
    train_runtime_sec: float,
    head_reinitialised: bool,
    metrics: dict[str, Any],
    test_dataset: str | None = None,
    test_documents: int = 0,
    test_metrics: dict[str, Any] | None = None,
    segmentation: str = "truncate",
) -> Path:
    """Write model_manifest.json v2 and return the path."""
    manifest: dict[str, Any] = {
        "name": name,
        "framework": "huggingface",
        "labels": labels,
        "schema_version": 2,
        "base_model": base_model,
        "parent_model": parent_model_name,
        "tokenizer": tokenizer_source,
        "has_crf": False,
        "training_config": training_config,
        "training": {
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "train_dataset": train_dataset,
            "train_documents": train_documents,
            "eval_dataset": eval_dataset,
            "eval_fraction": eval_fraction,
            "eval_documents": eval_documents,
            "test_dataset": test_dataset,
            "test_documents": test_documents,
            "seed": seed,
            "device_used": device_used,
            "total_steps": total_steps,
            "train_runtime_sec": round(train_runtime_sec, 2),
            "bio_labels": bio_labels,
            "head_reinitialised": head_reinitialised,
            "segmentation": segmentation,
        },
        "metrics": metrics,
        "test_metrics": test_metrics,
    }
    path = model_dir / "model_manifest.json"
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path
