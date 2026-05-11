from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Self

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from clinical_deid.env_file import resolve_env_file_path
from clinical_deid.synthesis.client import OpenAICompatibleChatClient

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    #: Deployment posture. ``production`` causes the app to refuse silent insecure
    #: defaults — e.g. logs a warning at startup if no API keys are configured.
    environment: str = Field(
        default="development",
        description="Deployment posture: ``development`` (default) or ``production``.",
    )
    #: All mutable state lives under ``data/`` so a deployment can mount one volume.
    #: Model weights live under ``models/`` (read-only in production).
    database_url: str = "sqlite:///./data/app.sqlite"
    pipelines_dir: Path = Path("data/pipelines")
    #: Deploy/mode mapping (Playground **Deploy** view and ``PUT /deploy``). Mutable on disk or via API.
    modes_path: Path = Path("data/modes.json")
    evaluations_dir: Path = Path("data/evaluations")
    inference_runs_dir: Path = Path("data/inference_runs")
    models_dir: Path = Path("models")
    #: Registered dataset homes. JSONL-only: each dataset is
    #: ``{corpora_dir}/{name}/dataset.json`` plus ``corpus.jsonl``. BRAT is an ingest/export
    #: format, not a storage layout — see ``exports_dir`` for materialized exports.
    corpora_dir: Path = Path("data/corpora")
    #: Training / BRAT / sharing exports from ``POST /datasets/{name}/export`` land under
    #: ``{exports_dir}/{name}/`` — kept separate from ``corpora_dir`` so the corpora root
    #: stays canonical (JSONL only).
    exports_dir: Path = Path("data/exports")
    dictionaries_dir: Path = Path("data/dictionaries")
    #: Active label space (see :mod:`clinical_deid.labels`). The default
    #: ``clinical_phi`` pack ships HIPAA Safe Harbor identifiers plus clinical
    #: additions; ``generic_pii`` is a minimal general-purpose starting point.
    #: Register custom packs at startup via ``register_label_space(...)``.
    label_space_name: str = Field(
        default="clinical_phi",
        description=(
            "Name of the registered label space used as the canonical entity "
            "schema. Built-ins: 'clinical_phi' (default), 'generic_pii'."
        ),
    )
    #: Active risk profile (see :mod:`clinical_deid.risk`). The default
    #: ``clinical_phi`` profile ships HIPAA Safe Harbor coverage and
    #: clinical-severity risk weights.
    risk_profile_name: str = Field(
        default="clinical_phi",
        description=(
            "Name of the registered risk profile used for risk-weighted recall "
            "and coverage reporting. Built-ins: 'clinical_phi' (default), "
            "'generic_pii'."
        ),
    )
    #: Active surrogate strategy pack (see :mod:`clinical_deid.pipes.surrogate.packs`).
    #: Used by ``output_mode='surrogate'`` when a per-call pack is not supplied.
    surrogate_pack_name: str = Field(
        default="clinical_phi",
        description=(
            "Name of the registered surrogate pack used to map labels to fake-data "
            "strategies. Built-ins: 'clinical_phi' (default), 'generic_pii'."
        ),
    )
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="Allowed CORS origins for the API.",
    )
    #: API keys with admin scope. When empty AND ``inference_api_keys`` is empty, auth is disabled
    #: (unless ``environment="production"``, which then refuses to start unless ``auth_disabled=true``).
    admin_api_keys: list[str] = Field(
        default_factory=list,
        description=(
            "Admin-scope API keys. Accepted as 'Authorization: Bearer <key>' or 'X-API-Key: <key>'. "
            "Admin scope covers all mutation routes and also satisfies inference-scoped routes."
        ),
    )
    #: API keys with inference scope. When empty AND ``admin_api_keys`` is empty, auth is disabled
    #: (subject to the same production-posture guard as ``admin_api_keys``).
    inference_api_keys: list[str] = Field(
        default_factory=list,
        description=(
            "Inference-scope API keys. Accepted as 'Authorization: Bearer <key>' or 'X-API-Key: <key>'. "
            "Inference scope covers /process/* (subject to the deploy allowlist)."
        ),
    )
    #: Explicit opt-in to run with auth disabled in ``environment="production"``. Default ``False``
    #: makes a misconfigured production deploy refuse to start instead of silently exposing admin.
    auth_disabled: bool = Field(
        default=False,
        description=(
            "Allow the API to start with no API keys configured even when "
            "CLINICAL_DEID_ENVIRONMENT=production. Default False: prod refuses to start without keys."
        ),
    )
    #: Reject requests with Content-Length above this (bytes). Defaults to 10 MiB.
    max_body_bytes: int = Field(
        default=10 * 1024 * 1024,
        description=(
            "Upper bound on request body size (bytes). Requests with a larger Content-Length "
            "are rejected with 413 before the route handler runs. "
            "File uploads (dictionaries, list parsers) enforce their own stricter per-file limit."
        ),
    )

    eval_per_document_limit: int = Field(
        default=500,
        description=(
            "Cap on the number of per-document items returned when POST /eval/run is "
            "called with include_per_document=true. Items are sorted worst-F1 first, so "
            "the cap keeps the hardest cases. Responses flag a truncated payload via "
            "metrics.document_level_truncated."
        ),
    )

    #: Explicit opt-in to send raw document text to an external LLM (OpenAI or compatible).
    #: Default ``False`` because the platform's primary use case is PHI; sending PHI off-host
    #: should be a deliberate decision (BAA, on-prem endpoint, synthetic-only data, …).
    #: Gates both the ``llm_ner`` pipe and ``POST /datasets/generate``.
    allow_external_llm: bool = Field(
        default=False,
        description=(
            "Allow LLM features (llm_ner pipe, dataset generate) to call out to the configured "
            "OpenAI-compatible endpoint. Default False; set CLINICAL_DEID_ALLOW_EXTERNAL_LLM=true "
            "to acknowledge that text passed to those features will leave the host."
        ),
    )
    #: For :class:`~clinical_deid.synthesis.client.OpenAICompatibleChatClient`. Loaded from ``.env`` or the environment. Either ``OPENAI_API_KEY`` or ``CLINICAL_DEID_OPENAI_API_KEY`` may be set.
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "CLINICAL_DEID_OPENAI_API_KEY"),
    )
    openai_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_BASE_URL", "CLINICAL_DEID_OPENAI_BASE_URL"),
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("OPENAI_MODEL", "CLINICAL_DEID_OPENAI_MODEL"),
    )
    #: Base URL for the NeuroNER Docker HTTP sidecar (overridable per pipe via ``base_url`` on :class:`~clinical_deid.pipes.neuroner_ner.pipe.NeuroNerConfig`).
    neuroner_http_url: str = Field(
        default="http://127.0.0.1:8765",
        validation_alias=AliasChoices(
            "CLINICAL_DEID_NEURONER_HTTP_URL",
            "NEURONER_HTTP_URL",
        ),
    )

    model_config = SettingsConfigDict(
        env_prefix="CLINICAL_DEID_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def __init__(self, **data: Any) -> None:
        if "_env_file" not in data:
            env_path = resolve_env_file_path()
            if env_path is not None:
                data["_env_file"] = str(env_path)
        super().__init__(**data)

    @model_validator(mode="after")
    def _legacy_processed_dir_env(self) -> Self:
        """``CLINICAL_DEID_PROCESSED_DIR`` was the old name for the corpus data root; still honored."""
        if os.environ.get("CLINICAL_DEID_PROCESSED_DIR") and not os.environ.get(
            "CLINICAL_DEID_CORPORA_DIR"
        ):
            logger.warning(
                "CLINICAL_DEID_PROCESSED_DIR is deprecated; use CLINICAL_DEID_CORPORA_DIR "
                "(single directory for all corpus files and API materialized outputs)."
            )
            self.corpora_dir = Path(os.environ["CLINICAL_DEID_PROCESSED_DIR"])
        return self

    @property
    def sqlite_path(self) -> Path | None:
        if self.database_url.startswith("sqlite:///./"):
            return Path(self.database_url.removeprefix("sqlite:///./"))
        if self.database_url.startswith("sqlite:///"):
            # absolute path: sqlite:////tmp/foo.db has four slashes
            rest = self.database_url.removeprefix("sqlite:///")
            if rest.startswith("/"):
                return Path(rest)
        return None

    def require_external_llm_allowed(self) -> None:
        """Raise unless ``allow_external_llm=True``.

        Called from every code path that sends raw user text to an LLM endpoint
        (``llm_ner`` pipe, ``POST /datasets/generate``). Forces an explicit opt-in
        so PHI doesn't leave the host by accident.
        """
        if not self.allow_external_llm:
            raise ValueError(
                "External LLM calls are disabled. Set CLINICAL_DEID_ALLOW_EXTERNAL_LLM=true "
                "to acknowledge that text passed to llm_ner / dataset generate will be sent "
                f"to the configured endpoint ({self.openai_base_url or 'https://api.openai.com/v1'})."
            )

    def openai_chat_client(self) -> OpenAICompatibleChatClient:
        """Build a chat client from these settings; raises if no API key is configured."""
        self.require_external_llm_allowed()
        if not self.openai_api_key:
            raise ValueError(
                "OpenAI API key is not set. Add OPENAI_API_KEY (or CLINICAL_DEID_OPENAI_API_KEY) "
                "to your environment or a ``.env`` file in the project root (see ``.env.example``)."
            )
        base = self.openai_base_url or "https://api.openai.com/v1"
        return OpenAICompatibleChatClient(
            model=self.openai_model,
            api_key=self.openai_api_key,
            base_url=base,
        )


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return a cached :class:`Settings` singleton (reads ``.env`` only once)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Test helper: clear cached settings so the next call re-reads the environment."""
    global _settings
    _settings = None
