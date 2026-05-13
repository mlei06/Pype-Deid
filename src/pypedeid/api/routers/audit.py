"""Audit log HTTP API — query processing logs for compliance and debugging."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import col, select

from pypedeid.api.auth import require_admin_or_inference
from pypedeid.api.deps import SessionDep
from pypedeid.tables import AuditLogRecord

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[require_admin_or_inference])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AuditLogSummary(BaseModel):
    id: str
    timestamp: datetime
    user: str
    command: str
    pipeline_name: str
    source: str
    doc_count: int
    span_count: int
    duration_seconds: float


class AuditLogDetail(AuditLogSummary):
    pipeline_config: dict[str, Any]
    dataset_source: str
    error_count: int
    metrics: dict[str, Any]
    notes: str
    client_id: str = ""
    output_mode: str = ""
    service_type: str = ""


class AuditStats(BaseModel):
    total_requests: int
    avg_duration_seconds: float
    total_spans_detected: int
    top_pipelines: list[dict[str, Any]]
    source_breakdown: dict[str, int]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/logs", response_model=list[AuditLogSummary])
def list_audit_logs(
    session: SessionDep,
    pipeline_name: str | None = Query(default=None),
    source: str | None = Query(default=None),
    command: str | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[AuditLogSummary]:
    """List audit logs with optional filters."""
    stmt = select(AuditLogRecord)

    if pipeline_name:
        stmt = stmt.where(AuditLogRecord.pipeline_name == pipeline_name)
    if source:
        stmt = stmt.where(AuditLogRecord.source == source)
    if command:
        stmt = stmt.where(AuditLogRecord.command == command)
    if from_date:
        stmt = stmt.where(col(AuditLogRecord.timestamp) >= from_date)
    if to_date:
        stmt = stmt.where(col(AuditLogRecord.timestamp) <= to_date)

    stmt = stmt.order_by(col(AuditLogRecord.timestamp).desc()).offset(offset).limit(limit)
    records = session.exec(stmt).all()

    return [
        AuditLogSummary(
            id=r.id,
            timestamp=r.timestamp,
            user=r.user,
            command=r.command,
            pipeline_name=r.pipeline_name,
            source=r.source,
            doc_count=r.doc_count,
            span_count=r.span_count,
            duration_seconds=r.duration_seconds,
        )
        for r in records
    ]


@router.get("/logs/{log_id}", response_model=AuditLogDetail)
def get_audit_log(session: SessionDep, log_id: str) -> AuditLogDetail:
    """Get full audit log detail."""
    record = session.get(AuditLogRecord, log_id)
    if record is None:
        raise HTTPException(status_code=404, detail="audit log not found")
    return AuditLogDetail(
        id=record.id,
        timestamp=record.timestamp,
        user=record.user,
        command=record.command,
        pipeline_name=record.pipeline_name,
        source=record.source,
        doc_count=record.doc_count,
        span_count=record.span_count,
        duration_seconds=record.duration_seconds,
        pipeline_config=record.pipeline_config,
        dataset_source=record.dataset_source,
        error_count=record.error_count,
        metrics=record.metrics,
        notes=record.notes,
        client_id=record.client_id,
        output_mode=record.output_mode,
        service_type=record.service_type,
    )


@router.get("/stats", response_model=AuditStats)
def audit_stats(
    session: SessionDep,
    pipeline_name: str | None = Query(default=None),
    source: str | None = Query(default=None),
) -> AuditStats:
    """Aggregate audit stats."""
    stmt = select(AuditLogRecord)
    if pipeline_name:
        stmt = stmt.where(AuditLogRecord.pipeline_name == pipeline_name)
    if source:
        stmt = stmt.where(AuditLogRecord.source == source)

    records = session.exec(stmt).all()

    if not records:
        return AuditStats(
            total_requests=0,
            avg_duration_seconds=0.0,
            total_spans_detected=0,
            top_pipelines=[],
            source_breakdown={},
        )

    total = len(records)
    avg_dur = sum(r.duration_seconds for r in records) / total
    total_spans = sum(r.span_count for r in records)

    # Top pipelines by request count
    pipeline_counts: dict[str, int] = {}
    for r in records:
        pipeline_counts[r.pipeline_name] = pipeline_counts.get(r.pipeline_name, 0) + 1
    top_pipelines = [
        {"pipeline_name": name, "request_count": count}
        for name, count in sorted(pipeline_counts.items(), key=lambda x: -x[1])[:10]
    ]

    # Source breakdown (cli vs api)
    source_counts: dict[str, int] = {}
    for r in records:
        source_counts[r.source] = source_counts.get(r.source, 0) + 1

    return AuditStats(
        total_requests=total,
        avg_duration_seconds=round(avg_dur, 2),
        total_spans_detected=total_spans,
        top_pipelines=top_pipelines,
        source_breakdown=source_counts,
    )
