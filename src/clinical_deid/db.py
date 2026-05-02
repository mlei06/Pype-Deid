"""Database engine and initialization.

The database stores only the audit trail.  Pipelines, models, datasets,
and eval results live on the filesystem.
"""

from __future__ import annotations

import threading

from sqlalchemy import Engine, event
from sqlmodel import SQLModel, create_engine

from clinical_deid.config import get_settings

_engine: Engine | None = None
_engine_lock = threading.Lock()


def reset_engine() -> None:
    """Test helper: clear cached engine after changing ``CLINICAL_DEID_DATABASE_URL``."""
    global _engine
    with _engine_lock:
        _engine = None


def get_engine() -> Engine:
    global _engine
    with _engine_lock:
        if _engine is not None:
            return _engine
        settings = get_settings()
        p = settings.sqlite_path
        if p is not None:
            p.parent.mkdir(parents=True, exist_ok=True)
        is_sqlite = settings.database_url.startswith("sqlite")
        connect_args = (
            {"check_same_thread": False, "timeout": 30.0} if is_sqlite else {}
        )
        engine = create_engine(
            settings.database_url, echo=False, connect_args=connect_args
        )
        if is_sqlite:
            # WAL allows concurrent readers alongside a writer; busy_timeout
            # makes brief lock contention block instead of failing immediately.
            @event.listens_for(engine, "connect")
            def _set_sqlite_pragmas(dbapi_connection, _):  # type: ignore[no-untyped-def]
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute("PRAGMA journal_mode=WAL")
                    cursor.execute("PRAGMA synchronous=NORMAL")
                    cursor.execute("PRAGMA busy_timeout=30000")
                finally:
                    cursor.close()

        _engine = engine
    return _engine


def init_db() -> None:
    """Create all tables (audit_log) and backfill indexes on existing DBs."""
    from clinical_deid.tables import AuditLogRecord  # noqa: F401
    from sqlalchemy import text as _sql_text

    engine = get_engine()
    SQLModel.metadata.create_all(engine, checkfirst=True)

    # SQLModel.create_all with checkfirst=True won't add new indexes to a
    # pre-existing table (created before the index annotations were added).
    # Backfill idempotently so old deployments pick them up on restart.
    if engine.url.get_backend_name() == "sqlite":
        index_stmts = [
            "CREATE INDEX IF NOT EXISTS ix_audit_log_timestamp ON audit_log (timestamp)",
            "CREATE INDEX IF NOT EXISTS ix_audit_log_command ON audit_log (command)",
            "CREATE INDEX IF NOT EXISTS ix_audit_log_pipeline_name ON audit_log (pipeline_name)",
            "CREATE INDEX IF NOT EXISTS ix_audit_log_source ON audit_log (source)",
        ]
        with engine.begin() as conn:
            for stmt in index_stmts:
                conn.execute(_sql_text(stmt))
