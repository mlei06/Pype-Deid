"""Filesystem-backed saved inference runs (snapshots of process responses)."""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SAFE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def _validate_id(run_id: str) -> None:
    if not _SAFE_ID.match(run_id) or ".." in run_id:
        raise ValueError(
            f"Invalid inference run ID {run_id!r}: must match {_SAFE_ID.pattern} "
            "and not contain '..'"
        )


def _slug_pipeline(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", name.strip())[:80]
    return s or "pipeline"


@dataclass(frozen=True)
class InferenceRunInfo:
    """Summary row for listing saved inference runs."""

    id: str
    path: Path
    pipeline_name: str
    saved_at: str
    text_preview: str
    span_count: int


def _ensure_dir(inference_runs_dir: Path) -> None:
    inference_runs_dir.mkdir(parents=True, exist_ok=True)


def save_inference_run(
    inference_runs_dir: Path,
    payload: dict[str, Any],
) -> Path:
    """Write a snapshot JSON. *payload* should match a process response shape."""
    _ensure_dir(inference_runs_dir)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    pipeline = _slug_pipeline(str(payload.get("pipeline_name", "unknown")))
    # Random suffix prevents collisions when multiple runs land in the same second.
    run_id = f"{pipeline}_{ts}_{secrets.token_hex(3)}"
    path = inference_runs_dir / f"{run_id}.json"

    record = {
        "id": run_id,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    path.write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def list_inference_runs(inference_runs_dir: Path) -> list[InferenceRunInfo]:
    """List saved runs, newest first."""
    _ensure_dir(inference_runs_dir)
    out: list[InferenceRunInfo] = []
    for p in inference_runs_dir.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        text = data.get("original_text") or ""
        preview = text.replace("\n", " ")[:120]
        if len(text) > 120:
            preview += "…"
        spans = data.get("spans") or []
        span_count = len(spans) if isinstance(spans, list) else 0
        out.append(
            InferenceRunInfo(
                id=p.stem,
                path=p,
                pipeline_name=data.get("pipeline_name", ""),
                saved_at=data.get("saved_at") or data.get("created_at", ""),
                text_preview=preview,
                span_count=span_count,
            )
        )
    out.sort(key=lambda r: r.saved_at, reverse=True)
    return out


def load_inference_run(inference_runs_dir: Path, run_id: str) -> dict[str, Any]:
    """Load full snapshot by ID (filename stem)."""
    _validate_id(run_id)
    path = inference_runs_dir / f"{run_id}.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"Inference run {run_id!r} not found in {inference_runs_dir}"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def delete_inference_run(inference_runs_dir: Path, run_id: str) -> None:
    """Delete a saved run file."""
    _validate_id(run_id)
    path = inference_runs_dir / f"{run_id}.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"Inference run {run_id!r} not found in {inference_runs_dir}"
        )
    path.unlink()
