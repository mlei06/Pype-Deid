"""Process endpoint — send text through a named pipeline."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Header, HTTPException

from pypedeid.api.auth import InferenceCaller, require_admin, require_inference
from pypedeid.api.deps import SessionDep
from pypedeid.api.schemas import (
    BatchProcessRequest,
    BatchProcessResponse,
    OutputMode,
    EntitySpanResponse,
    PreviewProcessRequest,
    ProcessRequest,
    ProcessResponse,
    RedactRequest,
    RedactResponse,
    ScrubRequest,
    ScrubResponse,
)
from pypedeid.api.services.inference import (
    apply_output_mode,
    load_pipe_chain,
    log_audit,
    process_single,
)
from pypedeid.pipes.registry import load_pipeline
from pypedeid.domain import EntitySpan
from pypedeid.config import get_settings
from pypedeid.mode_config import load_mode_config
from pypedeid.tables import AuditLogRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/process", tags=["process"])


def _require_pipeline_allowed(caller: InferenceCaller, pipeline_name: str) -> None:
    """Enforce the deploy allowlist on inference-scoped callers.

    Admin-scoped callers bypass. If no allowlist is configured, all pipelines
    are allowed (same as today's behavior).
    """
    if caller.scope == "admin":
        return
    deploy_cfg = load_mode_config(get_settings().modes_path)
    if not deploy_cfg.is_pipeline_allowed(pipeline_name):
        raise HTTPException(
            status_code=403,
            detail=f"pipeline {pipeline_name!r} is not allowed in production",
        )


# ---------------------------------------------------------------------------
# Fixed routes MUST come before parameterized /{pipeline_name} routes
# ---------------------------------------------------------------------------


@router.post("/redact", response_model=RedactResponse)
def redact_document(
    session: SessionDep,
    body: RedactRequest,
    caller: InferenceCaller = require_inference,
    x_client_id: str | None = Header(default=None),
) -> RedactResponse:
    """Apply redaction or surrogate replacement given text and known spans.

    Useful after human review: the user corrects spans in the UI, then
    sends the final set here for export.
    """
    span_responses = [
        EntitySpanResponse(
            start=s.start, end=s.end, label=s.label,
            text=body.text[s.start : s.end],
        )
        for s in body.spans
    ]

    surrogate_text: str | None = None
    surrogate_spans: list[EntitySpanResponse] | None = None

    if body.output_mode == OutputMode.surrogate and body.include_surrogate_spans:
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
            st, aligned = surrogate_text_with_spans(
                body.text,
                phi_spans,
                seed=body.surrogate_seed,
                consistency=body.surrogate_consistency,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        output_text = st
        surrogate_text = st
        surrogate_spans = [
            EntitySpanResponse(
                start=s.start,
                end=s.end,
                label=s.label,
                text=st[s.start : s.end],
                confidence=s.confidence,
                source=s.source,
            )
            for s in aligned
        ]
    else:
        output_text = apply_output_mode(
            body.text, span_responses, body.output_mode,
            surrogate_seed=body.surrogate_seed,
            surrogate_consistency=body.surrogate_consistency,
        )

    try:
        import getpass

        counts: dict[str, int] = {}
        for s in body.spans:
            counts[s.label] = counts.get(s.label, 0) + 1
        record = AuditLogRecord(
            user=getpass.getuser(),
            command="redact",
            pipeline_name="",
            doc_count=1,
            span_count=len(body.spans),
            source="api-inference" if caller.scope == "inference" else "api-admin",
            client_id=caller.id or x_client_id or "",
            output_mode=body.output_mode.value,
            service_type="redact",
            metrics={"entity_counts": counts},
        )
        session.add(record)
    except Exception:
        logger.warning("Failed to write audit log for redact", exc_info=True)

    return RedactResponse(
        output_text=output_text,
        output_mode=body.output_mode,
        span_count=len(body.spans),
        surrogate_text=surrogate_text,
        surrogate_spans=surrogate_spans,
    )


@router.post("/scrub", response_model=ScrubResponse)
def scrub_text(
    session: SessionDep,
    body: ScrubRequest,
    caller: InferenceCaller = require_inference,
    x_client_id: str | None = Header(default=None),
) -> ScrubResponse:
    """Zero-config log cleaning: text in, clean text out.

    Uses the deploy config's ``default_mode`` when no mode/pipeline is
    specified.  Designed for easy integration from other services::

        import httpx
        client = httpx.Client(base_url="http://deid-server:8000")
        clean = client.post("/process/scrub", json={"text": log_line}).json()["text"]
    """
    deploy_cfg = load_mode_config(get_settings().modes_path)

    mode_or_pipeline = body.mode or deploy_cfg.default_mode or "fast"
    pipeline_name = deploy_cfg.resolve(mode_or_pipeline)

    _require_pipeline_allowed(caller, pipeline_name)

    pipe_chain, config = load_pipe_chain(pipeline_name)

    resp = process_single(
        body.text, body.request_id, pipe_chain, pipeline_name, config,
        output_mode=body.output_mode,
    )

    log_audit(
        session, pipeline_name, config, [resp],
        source="api-inference" if caller.scope == "inference" else "api-admin",
        output_mode=body.output_mode,
        client_id=caller.id or x_client_id or "",
        service_type="scrub",
    )

    return ScrubResponse(
        text=resp.redacted_text,
        pipeline_used=pipeline_name,
        output_mode=body.output_mode,
        span_count=len(resp.spans),
        processing_time_ms=resp.processing_time_ms,
    )


@router.post(
    "/preview",
    response_model=ProcessResponse,
    dependencies=[require_admin],
)
def process_preview(
    body: PreviewProcessRequest,
    output_mode: OutputMode = OutputMode.annotated,
) -> ProcessResponse:
    """Run an unsaved pipeline JSON against ad-hoc text with full tracing.

    Built for the playground's authoring test pane: pipeline is built in
    memory, no audit record is emitted, no deploy allowlist applies. Admin
    only.
    """
    try:
        pipe_chain = load_pipeline(body.config)
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"failed to build pipeline: {exc}"
        ) from exc

    return process_single(
        body.text,
        body.request_id,
        pipe_chain,
        "__preview__",
        body.config,
        trace=True,
        output_mode=output_mode,
        include_surrogate_spans=body.include_surrogate_spans,
        surrogate_seed=body.surrogate_seed,
        surrogate_consistency=body.surrogate_consistency,
    )


# ---------------------------------------------------------------------------
# Parameterized pipeline routes
# ---------------------------------------------------------------------------


@router.post("/{pipeline_name}", response_model=ProcessResponse)
def process_text(
    session: SessionDep,
    pipeline_name: str,
    body: ProcessRequest,
    caller: InferenceCaller = require_inference,
    trace: bool = False,
    output_mode: OutputMode = OutputMode.redacted,
    x_client_id: str | None = Header(default=None),
) -> ProcessResponse:
    # Mode alias? Resolve through deploy config so callers can POST /process/fast.
    deploy_cfg = load_mode_config(get_settings().modes_path)
    resolved = deploy_cfg.resolve(pipeline_name)
    _require_pipeline_allowed(caller, resolved)

    pipe_chain, config = load_pipe_chain(resolved)
    resp = process_single(
        body.text, body.request_id, pipe_chain, resolved, config,
        trace=trace, output_mode=output_mode,
        include_surrogate_spans=body.include_surrogate_spans,
        surrogate_seed=body.surrogate_seed,
        surrogate_consistency=body.surrogate_consistency,
    )
    log_audit(
        session, resolved, config, [resp],
        source="api-inference" if caller.scope == "inference" else "api-admin",
        output_mode=output_mode,
        client_id=caller.id or x_client_id or "",
    )
    return resp


@router.post("/{pipeline_name}/batch", response_model=BatchProcessResponse)
def process_batch(
    session: SessionDep,
    pipeline_name: str,
    body: BatchProcessRequest,
    caller: InferenceCaller = require_inference,
    trace: bool = False,
    output_mode: OutputMode = OutputMode.redacted,
    x_client_id: str | None = Header(default=None),
) -> BatchProcessResponse:
    deploy_cfg = load_mode_config(get_settings().modes_path)
    resolved = deploy_cfg.resolve(pipeline_name)
    _require_pipeline_allowed(caller, resolved)

    pipe_chain, config = load_pipe_chain(resolved)

    t0 = time.perf_counter()
    results = [
        process_single(
            item.text, item.request_id, pipe_chain, resolved, config,
            trace=trace, output_mode=output_mode,
            include_surrogate_spans=item.include_surrogate_spans,
            surrogate_seed=item.surrogate_seed,
            surrogate_consistency=item.surrogate_consistency,
        )
        for item in body.items
    ]
    total_ms = (time.perf_counter() - t0) * 1000

    log_audit(
        session, resolved, config, results,
        source="api-inference" if caller.scope == "inference" else "api-admin",
        output_mode=output_mode,
        client_id=caller.id or x_client_id or "",
        service_type="batch",
    )

    return BatchProcessResponse(
        results=results,
        total_processing_time_ms=round(total_ms, 2),
    )
