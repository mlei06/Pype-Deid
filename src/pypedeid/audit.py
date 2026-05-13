"""Unified audit trail for CLI and API.

Writes to the main SQLite database (same as the API uses).  Both
``pypedeid run`` and ``POST /process`` log here.
"""

from __future__ import annotations

import getpass
from typing import Any

from pypedeid.tables import AuditLogRecord

# Common ``command`` values used across CLI and HTTP callers. Kept open: new
# entry points may introduce new commands. Audit UIs must not assume a closed
# allowlist — they should display unknown commands verbatim.
COMMAND_RUN = "run"
COMMAND_BATCH = "batch"
COMMAND_EVAL = "eval"
COMMAND_PROCESS = "process"
COMMAND_PROCESS_BATCH = "process_batch"
COMMAND_DATASET_INGEST = "dataset_ingest"
COMMAND_DATASET_EXPORT_SURROGATE = "dataset_export_surrogate"


def log_run(
    *,
    command: str,
    pipeline_name: str = "",
    pipeline_config: dict[str, Any] | None = None,
    dataset_source: str = "",
    doc_count: int = 0,
    error_count: int = 0,
    span_count: int = 0,
    duration_seconds: float = 0.0,
    metrics: dict[str, Any] | None = None,
    source: str = "cli",
    notes: str = "",
) -> AuditLogRecord:
    """Create and persist an audit record.  Returns the record."""
    from sqlmodel import Session

    from pypedeid.db import get_engine

    record = AuditLogRecord(
        user=getpass.getuser(),
        command=command,
        pipeline_name=pipeline_name,
        pipeline_config=pipeline_config or {},
        dataset_source=dataset_source,
        doc_count=doc_count,
        error_count=error_count,
        span_count=span_count,
        duration_seconds=duration_seconds,
        metrics=metrics or {},
        source=source,
        notes=notes,
    )
    with Session(get_engine()) as session:
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


def list_runs(limit: int = 20, source: str | None = None) -> list[AuditLogRecord]:
    """Return recent audit records (newest first)."""
    from sqlmodel import Session, col, select

    from pypedeid.db import get_engine

    stmt = select(AuditLogRecord)
    if source:
        stmt = stmt.where(AuditLogRecord.source == source)
    stmt = stmt.order_by(col(AuditLogRecord.timestamp).desc()).limit(limit)
    with Session(get_engine()) as session:
        return list(session.exec(stmt).all())


def get_run(record_id: str) -> AuditLogRecord | None:
    """Fetch a single audit record by ID (or prefix match)."""
    from sqlmodel import Session, select

    from pypedeid.db import get_engine

    with Session(get_engine()) as session:
        # Exact match first
        record = session.get(AuditLogRecord, record_id)
        if record:
            return record
        # Prefix match — order by timestamp descending for deterministic results
        stmt = (
            select(AuditLogRecord)
            .where(AuditLogRecord.id.startswith(record_id))  # type: ignore[attr-defined]
            .order_by(AuditLogRecord.timestamp.desc())  # type: ignore[union-attr]
        )
        return session.exec(stmt).first()
