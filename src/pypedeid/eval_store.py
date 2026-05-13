"""Filesystem-based evaluation result store.

Each eval run produces a JSON file in ``evaluations/`` named
``{pipeline}_{timestamp}.json``.  No database — browse results with ``ls``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SAFE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def _validate_id(result_id: str) -> None:
    """Reject IDs that could escape the target directory."""
    if not _SAFE_ID.match(result_id) or ".." in result_id:
        raise ValueError(
            f"Invalid eval result ID {result_id!r}: must match {_SAFE_ID.pattern} "
            f"and not contain '..'"
        )


@dataclass(frozen=True)
class EvalResultInfo:
    """Summary of a stored eval result file."""

    id: str  # filename stem
    path: Path
    pipeline_name: str
    dataset_source: str
    document_count: int
    strict_f1: float
    risk_weighted_recall: float
    created_at: str


def _ensure_dir(evaluations_dir: Path) -> None:
    evaluations_dir.mkdir(parents=True, exist_ok=True)


def save_eval_result(
    evaluations_dir: Path,
    pipeline_name: str,
    dataset_source: str,
    metrics: dict[str, Any],
    document_count: int,
) -> Path:
    """Write an eval result JSON file.  Returns the path."""
    _ensure_dir(evaluations_dir)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    result_id = f"{pipeline_name}_{ts}"
    path = evaluations_dir / f"{result_id}.json"

    result = {
        "id": result_id,
        "pipeline_name": pipeline_name,
        "dataset_source": dataset_source,
        "document_count": document_count,
        "metrics": metrics,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def list_eval_results(
    evaluations_dir: Path,
    pipeline_name: str | None = None,
) -> list[EvalResultInfo]:
    """List eval result files, newest first."""
    _ensure_dir(evaluations_dir)
    results: list[EvalResultInfo] = []
    for p in evaluations_dir.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        pname = data.get("pipeline_name", "")
        if pipeline_name and pname != pipeline_name:
            continue
        overall = data.get("metrics", {}).get("overall", {})
        results.append(
            EvalResultInfo(
                id=p.stem,
                path=p,
                pipeline_name=pname,
                dataset_source=data.get("dataset_source", ""),
                document_count=data.get("document_count", 0),
                strict_f1=overall.get("strict", {}).get("f1", 0.0),
                risk_weighted_recall=data.get("metrics", {}).get("risk_weighted_recall", 0.0),
                created_at=data.get("created_at", ""),
            )
        )
    results.sort(key=lambda r: r.created_at, reverse=True)
    return results


def load_eval_result(evaluations_dir: Path, result_id: str) -> dict[str, Any]:
    """Load a full eval result by ID (filename stem)."""
    _validate_id(result_id)
    path = evaluations_dir / f"{result_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Eval result {result_id!r} not found in {evaluations_dir}")
    return json.loads(path.read_text(encoding="utf-8"))
