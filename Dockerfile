# Clinical De-Identification API — production image.
#
# Build:  docker build -t clinical-deid-api .
# Run:    docker run -p 8000:8000 \
#             -v $(pwd)/data:/app/data \
#             -v $(pwd)/models:/app/models:ro \
#             clinical-deid-api
#
# Default extras: ``parquet`` + ``scripts`` (Faker/pandas for API
# ``output_mode=surrogate`` / redact). Presidio, spaCy, transformers, torch,
# and the LLM clients are now in the base install — no extras needed for
# inference. Add the ``train`` extra (datasets/seqeval/accelerate) only when
# you plan to fine-tune via ``clinical-deid train run`` inside the image:
#   --build-arg EXTRAS=parquet,scripts,train

FROM python:3.11-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps — curl for HEALTHCHECK, build-essential in a build stage only.
FROM base AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src

ARG EXTRAS=parquet,scripts
RUN pip install --prefix=/install ".[${EXTRAS}]"

FROM base AS runtime

# Curl for the HEALTHCHECK.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 appuser

COPY --from=builder /install /usr/local
COPY --chown=appuser:appuser src /app/src
COPY --chown=appuser:appuser pyproject.toml /app/pyproject.toml

USER appuser
WORKDIR /app

# Runtime data paths — bind-mount ./data for mutable state and ./models read-only.
#   /app/data/pipelines/       → pipeline JSON definitions
#   /app/data/modes.json       → deploy config (mode aliases, allowlist)
#   /app/data/evaluations/     → eval results
#   /app/data/inference_runs/  → saved batch inference snapshots
#   /app/data/corpora/         → datasets as ``<name>/dataset.json`` + corpus files
#   /app/data/dictionaries/    → whitelist/blacklist term lists
#   /app/data/app.sqlite       → SQLite audit DB
#   /app/models/               → model weights (read-only)
ENV CLINICAL_DEID_PIPELINES_DIR=/app/data/pipelines \
    CLINICAL_DEID_MODES_PATH=/app/data/modes.json \
    CLINICAL_DEID_EVALUATIONS_DIR=/app/data/evaluations \
    CLINICAL_DEID_INFERENCE_RUNS_DIR=/app/data/inference_runs \
    CLINICAL_DEID_CORPORA_DIR=/app/data/corpora \
    CLINICAL_DEID_DICTIONARIES_DIR=/app/data/dictionaries \
    CLINICAL_DEID_MODELS_DIR=/app/models \
    CLINICAL_DEID_DATABASE_URL=sqlite:////app/data/app.sqlite

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# Workers should be tuned to the host. 1 is a safe default for a small
# container; set WEB_CONCURRENCY to override without rebuilding.
# --timeout-graceful-shutdown gives in-flight requests time to finish on SIGTERM
# (e.g. during rolling deploys); orchestrators typically allow ~30s before SIGKILL.
ENV WEB_CONCURRENCY=1 \
    GRACEFUL_SHUTDOWN_SECONDS=30
CMD ["sh", "-c", "uvicorn clinical_deid.api.app:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY} --timeout-graceful-shutdown ${GRACEFUL_SHUTDOWN_SECONDS}"]
