"""Database tables — audit log only.

Pipelines, datasets, models, and eval results live on the filesystem.
The database stores the append-only audit trail.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import Column
from sqlalchemy.dialects.sqlite import JSON
from sqlmodel import Field, SQLModel


class AuditLogRecord(SQLModel, table=True):
    """Unified audit log entry for CLI and API operations."""

    __tablename__ = "audit_log"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    # Indexed: timestamp drives every list view (ORDER BY DESC) and is the most
    # common filter; source/command/pipeline_name are the other API filters.
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        index=True,
    )
    user: str = ""
    command: str = Field(default="", index=True)  # "run", "batch", "eval", ...
    pipeline_name: str = Field(default="", index=True)
    pipeline_config: dict[str, Any] = Field(sa_column=Column(JSON), default_factory=dict)
    dataset_source: str = ""  # filesystem path or "" for ad-hoc text
    doc_count: int = 0
    error_count: int = 0
    span_count: int = 0
    duration_seconds: float = 0.0
    metrics: dict[str, Any] = Field(sa_column=Column(JSON), default_factory=dict)
    source: str = Field(default="cli", index=True)  # "cli", "api-admin", "api-inference"
    client_id: str = ""  # identifying the calling service (X-Client-ID header)
    output_mode: str = ""  # "annotated", "redacted", "surrogate"
    service_type: str = ""  # "inference", "scrub", "batch", "redact", "assist"
    notes: str = ""
