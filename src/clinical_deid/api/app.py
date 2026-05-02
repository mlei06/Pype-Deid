from __future__ import annotations

import logging
import tempfile
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from sqlalchemy import text

from clinical_deid.api.routers import audit, datasets, deploy, dictionaries, evaluation, inference, models, pipelines, process
from clinical_deid.api.schemas import HealthResponse
from clinical_deid.db import get_engine, init_db

logger = logging.getLogger("clinical_deid")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    from clinical_deid.api.auth import auth_enabled
    from clinical_deid.config import get_settings

    if not auth_enabled() and get_settings().environment == "production":
        logger.warning(
            "API auth is DISABLED but CLINICAL_DEID_ENVIRONMENT=production. "
            "Set CLINICAL_DEID_ADMIN_API_KEYS / CLINICAL_DEID_INFERENCE_API_KEYS "
            "or change the environment value before exposing this instance."
        )
    logger.info("database initialised, API ready")
    try:
        yield
    finally:
        # Drain DB connections on SIGTERM so workers exit cleanly during rolling
        # deploys. Uvicorn's --timeout-graceful-shutdown drives the request drain.
        try:
            get_engine().dispose()
            logger.info("database engine disposed; shutdown complete")
        except Exception:
            logger.exception("error disposing database engine on shutdown")


def _check_database() -> bool:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("health check: database probe failed")
        return False


def _check_data_writable(data_dir) -> bool:
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=data_dir, prefix=".health-", delete=True):
            pass
        return True
    except Exception:
        logger.exception("health check: data dir not writable: %s", data_dir)
        return False


def create_app() -> FastAPI:
    """Application factory — defers settings access until called."""
    from clinical_deid.api.auth import auth_enabled, get_api_key_scope_for_health, require_admin
    from clinical_deid.config import get_settings

    # With auth enabled, don't expose the anonymous /docs / /redoc / /openapi.json —
    # we re-mount them below behind an admin-scope dependency so operators can still
    # introspect the schema.
    docs_kwargs: dict[str, str | None] = {}
    if auth_enabled():
        docs_kwargs = {"docs_url": None, "redoc_url": None, "openapi_url": None}

    application = FastAPI(
        title="Clinical De-Identification Playground",
        description=(
            "Platform API: compose and version de-identification pipelines, run inference for upstream "
            "services, and return auditable responses (timing, spans, optional step traces). "
            "Train models locally, drop artifacts under `models/`, and reference them from pipe configs. "
            "Planned: playground UI (try text + evaluate on local paths or uploads) and eval APIs—see docs."
        ),
        lifespan=lifespan,
        **docs_kwargs,
    )

    if auth_enabled():
        _mount_admin_docs(application, require_admin)

    settings = get_settings()

    # Body-size cap — runs before any route dep to bounce oversize payloads at the edge.
    from clinical_deid.api.middleware import MaxBodySizeMiddleware

    application.add_middleware(MaxBodySizeMiddleware, max_bytes=settings.max_body_bytes)

    # CORS — configured via settings (env var CLINICAL_DEID_CORS_ORIGINS or .env).
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key"],
    )

    application.include_router(pipelines.router)
    application.include_router(process.router)
    application.include_router(inference.router)
    application.include_router(audit.router)
    application.include_router(evaluation.router)
    application.include_router(models.router)
    application.include_router(datasets.router)
    application.include_router(dictionaries.router)
    application.include_router(deploy.router)

    @application.get("/health", response_model=HealthResponse)
    def health(
        response: Response,
        api_key_scope: str | None = Depends(get_api_key_scope_for_health),
    ) -> HealthResponse:
        # Resolve data_dir from sqlite_path or fall back to pipelines_dir's parent.
        data_dir = settings.sqlite_path.parent if settings.sqlite_path else settings.pipelines_dir.parent
        checks = {
            "database": _check_database(),
            "data_writable": _check_data_writable(data_dir),
        }
        ok = all(checks.values())
        if not ok:
            response.status_code = 503
        return HealthResponse(
            status="ok" if ok else "degraded",
            label_space_name=settings.label_space_name,
            risk_profile_name=settings.risk_profile_name,
            api_key_scope=api_key_scope,
            checks=checks,
        )

    return application


def _mount_admin_docs(application: FastAPI, require_admin) -> None:
    """Re-mount /docs, /redoc, /openapi.json behind admin-scope auth."""
    openapi_url = "/openapi.json"

    @application.get(openapi_url, include_in_schema=False, dependencies=[require_admin])
    def openapi_schema() -> dict:
        return application.openapi()

    @application.get("/docs", include_in_schema=False, dependencies=[require_admin])
    def swagger_ui() -> object:
        return get_swagger_ui_html(openapi_url=openapi_url, title=f"{application.title} — docs")

    @application.get("/redoc", include_in_schema=False, dependencies=[require_admin])
    def redoc_ui() -> object:
        return get_redoc_html(openapi_url=openapi_url, title=f"{application.title} — redoc")


app = create_app()
