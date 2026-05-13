"""Shared inference helpers used across routers.

Extracted from ``routers/process.py`` so other callers (e.g. the standalone
``/redact`` endpoint, scope-gated inference paths) can import them without
depending on underscored names in a router module.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from pypedeid.api.schemas import (
    OutputMode,
    EntitySpanResponse,
    ProcessResponse,
)
from pypedeid.config import get_settings
from pypedeid.domain import AnnotatedDocument, Document, EntitySpan, tag_replace
from pypedeid.labels import normalize_entity_spans
from pypedeid.pipeline_store import load_pipeline_config
from pypedeid.pipes.base import Pipe
from pypedeid.pipes.combinators import Pipeline
from pypedeid.pipes.registry import load_pipeline
from pypedeid.tables import AuditLogRecord

logger = logging.getLogger(__name__)


def load_pipe_chain(pipeline_name: str) -> tuple[Pipe, dict[str, Any]]:
    """Load a pipeline from the filesystem by name."""
    try:
        config = load_pipeline_config(get_settings().pipelines_dir, pipeline_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        pipe_chain = load_pipeline(config)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"failed to build pipeline: {exc}"
        ) from exc
    return pipe_chain, config


def apply_output_mode(
    original_text: str,
    spans: list[EntitySpanResponse],
    output_mode: OutputMode,
    *,
    surrogate_seed: int | None = None,
    surrogate_consistency: bool = True,
) -> str:
    """Apply the requested output mode to produce the final text."""
    if output_mode == OutputMode.annotated:
        return original_text

    if output_mode == OutputMode.surrogate:
        try:
            from pypedeid.pipes.surrogate.align import surrogate_text_with_spans
        except ImportError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"surrogate mode requires faker: {exc}",
            ) from exc

        phi_spans = [
            EntitySpan(
                start=s.start,
                end=s.end,
                label=s.label,
                confidence=s.confidence,
                source=s.source,
            )
            for s in spans
        ]
        try:
            surrogate_text, _aligned = surrogate_text_with_spans(
                original_text,
                phi_spans,
                seed=surrogate_seed,
                consistency=surrogate_consistency,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return surrogate_text

    phi_spans = [EntitySpan(start=s.start, end=s.end, label=s.label) for s in spans]
    return tag_replace(original_text, phi_spans)


def process_single(
    text: str,
    request_id: str | None,
    pipe_chain: Pipe,
    pipeline_name: str,
    pipeline_config: dict[str, Any],
    *,
    trace: bool = False,
    output_mode: OutputMode = OutputMode.redacted,
    include_surrogate_spans: bool = False,
    surrogate_seed: int | None = None,
    surrogate_consistency: bool = True,
) -> ProcessResponse:
    req_id = request_id or str(uuid4())

    doc = AnnotatedDocument(
        document=Document(id=req_id, text=text),
        spans=[],
    )

    intermediary_trace: list[dict[str, Any]] | None = None
    if isinstance(pipe_chain, Pipeline):
        run_result = pipe_chain.run(doc, trace=trace, timing=True)
        result = run_result.final
        elapsed_ms = run_result.total_elapsed_ms or 0.0
        if trace:
            intermediary_trace = run_result.frames_as_jsonable()
    else:
        t0 = time.perf_counter()
        result = pipe_chain.forward(doc)
        elapsed_ms = (time.perf_counter() - t0) * 1000

    result = result.with_spans(normalize_entity_spans(list(result.spans)))

    span_responses = [
        EntitySpanResponse(
            start=s.start,
            end=s.end,
            label=s.label,
            text=text[s.start : s.end],
            confidence=s.confidence,
            source=s.source,
        )
        for s in result.spans
    ]

    redacted = apply_output_mode(
        text,
        span_responses,
        output_mode,
        surrogate_seed=surrogate_seed,
        surrogate_consistency=surrogate_consistency,
    )

    surrogate_text: str | None = None
    surrogate_spans: list[EntitySpanResponse] | None = None
    if include_surrogate_spans and output_mode == OutputMode.surrogate:
        try:
            from pypedeid.pipes.surrogate.align import surrogate_text_with_spans
        except ImportError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"surrogate mode requires faker: {exc}",
            ) from exc
        phi_spans = [
            EntitySpan(
                start=s.start,
                end=s.end,
                label=s.label,
                confidence=s.confidence,
                source=s.source,
            )
            for s in span_responses
        ]
        try:
            surrogate_text, aligned = surrogate_text_with_spans(
                text,
                phi_spans,
                seed=surrogate_seed,
                consistency=surrogate_consistency,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        surrogate_spans = [
            EntitySpanResponse(
                start=s.start,
                end=s.end,
                label=s.label,
                text=surrogate_text[s.start:s.end],
                confidence=s.confidence,
                source=s.source,
            )
            for s in aligned
        ]

    return ProcessResponse(
        request_id=req_id,
        original_text=text,
        redacted_text=redacted,
        spans=span_responses,
        pipeline_name=pipeline_name,
        processing_time_ms=round(elapsed_ms, 2),
        intermediary_trace=intermediary_trace,
        surrogate_text=surrogate_text,
        surrogate_spans=surrogate_spans,
    )


def entity_counts(responses: list[ProcessResponse]) -> dict[str, int]:
    """Per-label span counts across all responses."""
    counts: Counter[str] = Counter()
    for r in responses:
        for s in r.spans:
            counts[s.label] += 1
    return dict(counts)


def log_audit(
    session: Any,
    pipeline_name: str,
    pipeline_config: dict[str, Any],
    responses: list[ProcessResponse],
    *,
    source: str = "api-admin",
    output_mode: OutputMode = OutputMode.redacted,
    client_id: str = "",
    service_type: str = "inference",
) -> None:
    """Persist a single audit record for one or more processed docs."""
    try:
        import getpass

        total_spans = sum(len(r.spans) for r in responses)
        total_ms = sum(r.processing_time_ms for r in responses)
        record = AuditLogRecord(
            user=getpass.getuser(),
            command="process" if len(responses) == 1 else "process_batch",
            pipeline_name=pipeline_name,
            pipeline_config=pipeline_config,
            doc_count=len(responses),
            span_count=total_spans,
            duration_seconds=total_ms / 1000,
            source=source,
            client_id=client_id,
            output_mode=output_mode.value,
            service_type=service_type,
            metrics={"entity_counts": entity_counts(responses)},
        )
        session.add(record)
    except Exception:
        logger.warning("Failed to write audit log", exc_info=True)
