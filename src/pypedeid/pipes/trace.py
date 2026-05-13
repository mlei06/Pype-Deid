"""Intermediate pipeline outputs for UI / debugging.

.. warning::

    Trace frames deep-copy the full document including text. When tracing is
    enabled, PHI is duplicated in memory and will appear in serialized output
    from :meth:`PipelineRunResult.frames_as_jsonable`.  Do **not** expose
    trace output to untrusted consumers without access-control review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pypedeid.domain import AnnotatedDocument


def snapshot_document(doc: AnnotatedDocument) -> AnnotatedDocument:
    """Deep copy so later pipe stages cannot mutate a trace frame."""
    return doc.model_copy(deep=True)


@dataclass
class PipelineTraceFrame:
    """One captured stage: document state + metadata for display."""

    path: str
    stage: str
    pipe_type: str
    document: AnnotatedDocument | None = None
    elapsed_ms: float | None = None
    branch_index: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineRunResult:
    """Result of :meth:`Pipeline.run`."""

    final: AnnotatedDocument
    trace: list[PipelineTraceFrame]
    total_elapsed_ms: float | None = None

    def frames_as_jsonable(self) -> list[dict[str, Any]]:
        """Frames with each document as ``model_dump()`` for API responses."""
        out: list[dict[str, Any]] = []
        for f in self.trace:
            d: dict[str, Any] = {
                "path": f.path,
                "stage": f.stage,
                "pipe_type": f.pipe_type,
                "branch_index": f.branch_index,
                "extra": f.extra,
            }
            if f.document is not None:
                d["document"] = f.document.model_dump()
            if f.elapsed_ms is not None:
                d["elapsed_ms"] = f.elapsed_ms
            out.append(d)
        return out
