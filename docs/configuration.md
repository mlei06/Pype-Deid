# Configuration

All configuration is managed through environment variables. Defaults work out of the box for local development; for self-hosted production deployment, set the `PYPEDEID_*` variables documented below — and the production posture gates `PYPEDEID_AUTH_DISABLED` and `PYPEDEID_ALLOW_EXTERNAL_LLM` (the API refuses to start when `environment=production` and no API keys are configured unless the former is explicitly set; the latter must be opt-in before any LLM pipe or `/datasets/generate` call). See [deployment.md](deployment.md) for the full production checklist.

## Environment variables

### Storage paths

All mutable state defaults to `./data/` (one host volume in production) and model weights default to `./models/` (read-only in production). See [deployment.md](deployment.md).

| Variable | Default | Description |
|----------|---------|-------------|
| `PYPEDEID_DATABASE_URL` | `sqlite:///./data/app.sqlite` | SQLAlchemy database URL (audit log) |
| `PYPEDEID_PIPELINES_DIR` | `data/pipelines` | Named pipeline JSON configs (mutable via UI or on disk) |
| `PYPEDEID_MODES_PATH` | `data/modes.json` | Deploy/mode mapping for Production UI and allowlist (`PUT /deploy` or edit file) |
| `PYPEDEID_EVALUATIONS_DIR` | `data/evaluations` | Evaluation result JSON files |
| `PYPEDEID_INFERENCE_RUNS_DIR` | `data/inference_runs` | Batch inference output directory |
| `PYPEDEID_DICTIONARIES_DIR` | `data/dictionaries` | Whitelist/blacklist term-list files |
| `PYPEDEID_MODELS_DIR` | `models` | Root directory for model registry |
| `PYPEDEID_CORPORA_DIR` | `data/corpora` | Dataset homes: ``<name>/corpus.jsonl`` (canonical) + ``dataset.json`` (cached stats). **JSONL-only**; BRAT is converted in, not stored as the on-disk layout |
| `PYPEDEID_EXPORTS_DIR` | `data/exports` | Default output for `POST /datasets/{name}/export` and for `pypedeid dataset export --format brat` (kept outside `corpora/`) |
| `PYPEDEID_ENV_FILE` | _(auto-detected)_ | Explicit path to `.env` file |

`PYPEDEID_PROCESSED_DIR` is a deprecated alias for `PYPEDEID_CORPORA_DIR` — still honored with a warning.

**Ingest safety:** `POST /datasets/ingest-from-pipeline` requires `source_path`
to resolve under `PYPEDEID_CORPORA_DIR`. Absolute paths and paths
traversing via `..` are rejected with 400; symlinks are resolved before the
boundary check so a symlink inside the root pointing outside will also be
rejected.

### Domain packs (label space + risk profile)

The platform ships with a clinical de-identification pack as the default, but the label schema and risk/coverage reporting are pluggable. Built-ins: `clinical_phi` (default) and `generic_pii`. Register custom packs at startup via `pypedeid.labels.register_label_space(...)` and `pypedeid.risk.register_risk_profile(...)`.

| Variable | Default | Description |
|----------|---------|-------------|
| `PYPEDEID_LABEL_SPACE_NAME` | `clinical_phi` | Canonical entity labels + alias table. `clinical_phi` covers HIPAA Safe Harbor plus clinical additions; `generic_pii` is a minimal universal-PII pack. |
| `PYPEDEID_RISK_PROFILE_NAME` | `clinical_phi` | Risk weights + coverage identifiers for `POST /eval/run` and `pypedeid eval` (default when the request/CLI does not override). `clinical_phi` uses HIPAA's 18 identifiers with clinical severity weights; `generic_pii` uses six categorical identifiers (names, contact, location, id, temporal, network) with uniform weights. |

**`generic_pii` and pipes:** `PYPEDEID_LABEL_SPACE_NAME` and `PYPEDEID_RISK_PROFILE_NAME` do **not** automatically change `regex_ner` / `surrogate` behavior. Those pipes still use `RegexNerConfig.pattern_pack` and `SurrogateConfig.strategy_pack` (defaults: `clinical_phi`). For a consistent non-clinical stack, set those to `generic_pii` in each pipeline (or register custom pattern/surrogate packs) alongside the two env vars above.

**Label normalization:** `POST /process/*` responses apply `default_label_space().normalize` to span labels (alias table + fallback). **Evaluation** (`POST /eval/run`, `evaluate_pipeline`, CLI `eval`) compares **raw** gold and predicted label strings; align the corpus and pipeline (e.g. a final `label_mapper`) if names differ. Internal pipeline `label_mapping` remaps are preserved until the inference boundary.

Regex pattern packs (`clinical_phi`, `generic_pii`) and surrogate strategy packs (`clinical_phi`, `generic_pii`) are the built-ins selectable per-pipe via the `pattern_pack` / `strategy_pack` fields on `RegexNerConfig` / `SurrogateConfig`.

### HTTP / auth

| Variable | Default | Description |
|----------|---------|-------------|
| `PYPEDEID_CORS_ORIGINS` | `["http://localhost:3000", "http://127.0.0.1:3000"]` | Allowed CORS origins (JSON array) |
| `PYPEDEID_ADMIN_API_KEYS` | `[]` | Admin-scope API keys (JSON array) |
| `PYPEDEID_INFERENCE_API_KEYS` | `[]` | Inference-scope API keys (JSON array) |
| `PYPEDEID_MAX_BODY_BYTES` | `10485760` | Reject requests with `Content-Length` above this (10 MiB) |
| `PYPEDEID_EVAL_PER_DOCUMENT_LIMIT` | `500` | Cap on `metrics.document_level` items when `POST /eval/run` is called with `include_per_document[_spans]` (overflow flagged as `document_level_truncated`). |

List-valued variables must be JSON arrays, e.g. `PYPEDEID_CORS_ORIGINS='["https://app.example.com"]'`.

### External services

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | _(none)_ | API key for LLM synthesis |
| `PYPEDEID_OPENAI_API_KEY` | _(none)_ | Alternative name for the API key |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible API base URL |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model name for LLM synthesis |
| `PYPEDEID_NEURONER_HTTP_URL` | `http://127.0.0.1:8765` | Base URL for the NeuroNER Docker sidecar |

### Runtime tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `WEB_CONCURRENCY` | `1` | Uvicorn worker count (honored by the container `CMD`, not read by the app). With the default SQLite audit DB, values above `1` can cause lock contention — see [Deployment — Production checklist](deployment.md#production-checklist). |

## Authentication

The API has two scopes:

- **`admin`** — full access: pipeline CRUD, dictionaries, deploy config (`GET`/`PUT` `/deploy`, `GET` `/deploy/pipelines`), datasets, evaluation, models, and all `/process/*` routes. Admin keys also satisfy `inference`-scoped checks.
- **`inference`** — least privilege for integrators and the Production UI:
  - `POST /process/*` (including `/process/redact`, `/process/scrub`), subject to the deploy allowlist in `data/modes.json` (admins bypass the allowlist).
  - `POST /pipelines/pipe-types/{name}/labels` (label-space compute; no filesystem writes).
  - `GET /deploy/health` (mode list + availability for the mode selector).
  - `GET /audit/logs`, `GET /audit/logs/{id}`, `GET /audit/stats` (read-only audit queries).

All other routes require an **admin** key when auth is enabled.

Keys are accepted in either header:

```
Authorization: Bearer <key>
X-API-Key: <key>
```

Auth is **disabled when both key lists are empty** — this keeps local dev friction-free. In that mode, OpenAPI docs are served at `/docs` and `/redoc`. When any key is configured, `/docs`, `/redoc`, and `/openapi.json` are removed from the app.

Example production config:

```bash
export PYPEDEID_ADMIN_API_KEYS='["ops-team-key-1","ops-team-key-2"]'
export PYPEDEID_INFERENCE_API_KEYS='["upstream-service-key"]'
```

The audit log records a hashed client id (first 12 chars of `sha256(key)`) — raw keys are never persisted.

## .env file

Copy `.env.example` to `.env` and fill in values:

```bash
cp .env.example .env
```

The `.env` file is loaded automatically by `pydantic-settings`. The file is gitignored.

### .env resolution order

1. `PYPEDEID_ENV_FILE` environment variable (if set and the file exists)
2. Walk up from the current working directory looking for `.env`
3. `.env` next to the nearest `pyproject.toml` ancestor
4. No `.env` file (rely on environment variables only)

## Settings object

All settings are managed by a Pydantic `Settings` class:

```python
from pypedeid.config import get_settings, reset_settings

settings = get_settings()  # singleton, cached
print(settings.database_url)
print(settings.openai_api_key)
```

`reset_settings()` clears the cache (useful in tests).

## Database

The default database is SQLite at `./data/app.sqlite`. The `data/` directory is created by the server on first run.

```bash
pypedeid-api
```

To use a different path:

```bash
export PYPEDEID_DATABASE_URL="sqlite:////tmp/my-deid.sqlite"
```

Tables are auto-created on startup via `init_db()`:

| Table | Purpose |
|-------|---------|
| `audit_log` | Append-only audit trail for all CLI and API operations |

## Pipeline cache

Built pipe chains are cached in memory (LRU, max 32 entries, keyed by config hash). This avoids rebuilding the pipe chain on every request. The cache is thread-safe and cleared on server restart.

```python
from pypedeid.db import clear_pipeline_cache
clear_pipeline_cache()  # manually clear if needed
```

## Logging

Structured logging is configured in `__main__.py`:

```
2024-06-15 10:30:00 INFO     pypedeid  database initialised, API ready
```

Format: `%(asctime)s %(levelname)-8s %(name)s  %(message)s`

The `pypedeid` logger namespace is used throughout the application. Uvicorn adds its own access logging.

## CORS

CORS middleware allows requests from origins in `PYPEDEID_CORS_ORIGINS` (default: `http://localhost:3000`, `http://127.0.0.1:3000`). Override via environment variable or `.env` file.

## Request body limits

`MaxBodySizeMiddleware` rejects any request whose `Content-Length` exceeds `PYPEDEID_MAX_BODY_BYTES` (default 10 MiB) with a 413 response before the route runs. Chunked uploads (no `Content-Length` header) pass through; per-endpoint upload handlers (dictionaries, list parsers) apply their own stricter caps. Heavier limits like rate limiting and IP allowlisting are expected at the reverse proxy / load balancer layer, not in the app.

## Deploy configuration

Production deploy settings are stored in `data/modes.json`. This file is managed via the `/deploy` API endpoints and the Deploy tab in the UI. It maps inference mode names to pipelines and defines an optional pipeline allowlist applied to inference-scoped `/process/*` calls.

**Seeded** `modes` → `pipeline` (and `default_mode`) ship with the repo: `fast` → `clinical-fast` (**default**), `presidio` → `presidio`, `transformer` → `clinical-transformer`, `transformer_presidio` → `clinical-transformer-presidio`. That is **separate** from the CLI’s `--profile` `fast` / `balanced` / `accurate` (see `src/pypedeid/profiles.py`).

In Docker Compose, mount `./data` **writable** if operators use `PUT /deploy` from the Playground; a read-only mount blocks saving deploy changes.

## Pipelines vs API output mode

Pipeline definitions should contain **detectors and span transforms** only (e.g. `resolve_spans`). **Redacted** and **surrogate** text are produced by the API using `output_mode` on `POST /process/...` and `POST /process/redact`, not by adding a surrogate redactor step to the pipeline catalog. Surrogate mode needs Faker (`pip install '.[scripts]'`, or include `scripts` in the Docker image `EXTRAS`).

## Project structure

High-level layout (see also [docs/README.md](README.md)):

```
src/pypedeid/
├── api/                  # FastAPI app, routers, schemas, auth, middleware
├── pipes/                # Pipe implementations + registry (see pipes-and-pipelines.md)
├── training/             # HF fine-tuning (CLI: pypedeid train run)
├── ingest/               # Dataset loaders
├── synthesis/            # LLM note generation
├── transform/            # Dataset transforms
├── compose/              # Multi-corpus merging
├── eval/                 # Evaluation metrics + runner
├── domain.py             # Document, EntitySpan, AnnotatedDocument
├── config.py             # Settings
├── db.py                 # SQLite + pipeline cache
├── models.py             # Filesystem model registry scanner
├── tables.py             # audit_log
└── ...
```

Specific pipe packages (`regex_ner/`, `huggingface_ner/`, `presidio_ner/`, …) live under `pipes/`; the authoritative list is the catalog in `pipes/registry.py`.
