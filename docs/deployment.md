# Deployment (single API)

One FastAPI application serves the Playground, automation, and the Production UI. There is no separate `clinical-deid-production` binary.

For a step-by-step Docker bring-up (build, volumes, env vars, frontends), see [docker-quickstart.md](docker-quickstart.md).

**Dedicated production Compose:** [compose.prod.yaml](../compose.prod.yaml) is a **pull-only** file (no `build:`) so you can deploy a registry image with `CLINICAL_DEID_DOCKER_IMAGE`, default `WEB_CONCURRENCY=1`, and host overrides for data/model paths. Local iteration stays on [compose.yaml](../compose.yaml) (`docker compose up --build`).

## Production checklist

- **Secrets:** Set `CLINICAL_DEID_ADMIN_API_KEYS` and `CLINICAL_DEID_INFERENCE_API_KEYS` as JSON arrays (see [Configuration — Authentication](configuration.md#authentication)). Never commit real keys. With root `compose.yaml`, copy [`.env.example`](../.env.example) to `.env` and define keys there — the Compose file does not hard-code empty key lists, so your `.env` values are not overridden.
- **CORS:** `CLINICAL_DEID_CORS_ORIGINS` must list **every** browser origin that will call the API (scheme + host + port), including the Playground and Production UI. Values in the Compose `environment` block override the same variables from `.env`; adjust one or the other so they stay in sync.
- **SQLite and workers:** The default audit store is SQLite (`CLINICAL_DEID_DATABASE_URL`). Each Uvicorn worker is a separate process; concurrent audit writes can produce intermittent **database is locked** errors when `WEB_CONCURRENCY` > 1. Prefer **`WEB_CONCURRENCY=1`** for SQLite-only deployments. For several workers and heavy concurrent audit traffic, point `CLINICAL_DEID_DATABASE_URL` at a client–server database and add the matching SQLAlchemy driver to your image.
- **Compose `env_file`:** Optional `.env` loading uses the `path` / `required: false` form (Docker Compose **v2.24+**). On older Compose, remove the `env_file` block from `compose.yaml` or keep a (possibly empty) `.env` file if your version requires it.
- **Load balancer:** Point HTTP health checks at `GET /health` (returns 200 when the app is up). Terminate TLS and apply rate limits at the proxy.
- **SPAs:** Build each frontend with `VITE_API_BASE_URL` and `VITE_API_KEY` set for the target API (variables are fixed at **build** time). Restrict Production UI callers with **inference** keys; reserve **admin** keys for operators.

## Topology

- **API:** `clinical-deid-api` → `uvicorn clinical_deid.api.app:app` (see root `Dockerfile` and `compose.yaml`).
- **Playground UI** (`frontend/`) and **Production UI** (`frontend-production/`) are static SPAs. They call the API using `VITE_API_BASE_URL` and optional `VITE_API_KEY` (see each app’s `.env.example`).
- **Mutable config after deploy:** Pipeline definitions (`CLINICAL_DEID_PIPELINES_DIR`, default `data/pipelines`) and deploy/mode mapping (`CLINICAL_DEID_MODES_PATH`, default `data/modes.json`) are **meant to change in production** without rebuilding the image. Operators can use the full **admin** Playground UI (pipeline builder, **Deploy** view) or **edit the JSON files on the instance** (bind-mount or volume). The API re-reads `modes.json` on each request that needs it; pipeline JSON is read from disk per request when loading a pipeline. The **tracked** seed maps mode aliases to shipped pipelines (e.g. `fast` → `clinical-fast`, **`default_mode`**: `fast`); that is **not** the same as the CLI’s `--profile` `balanced` / `accurate` — see [Configuration — Deploy configuration](configuration.md#deploy-configuration) and the main [README](../README.md#evaluation).
- **Two volumes** — everything mutable lives under `./data` (pipelines, modes, evaluations, inference runs, corpora, exports, dictionaries, SQLite audit log); model weights live under `./models` and are read-only at runtime. This is the full mount story — see `compose.yaml`:
    - `./data:/app/data` (read-write)
    - `./models:/app/models:ro`
- **NeuroNER:** Optional HTTP sidecar (`neuroner-cspmc/sidecar/`); set `CLINICAL_DEID_NEURONER_HTTP_URL`.

## Modes are the client contract — not pipelines

Clients call `POST /process/<mode>` (e.g. `POST /process/fast`). The mode name is the only thing client code is coupled to. Behind it, you control two things independently:

1. **Which pipeline a mode points at** — repoint `fast` from `clinical-fast` to `clinical-llm` in `data/modes.json` (or via the **Deploy** view).
2. **What that pipeline does** — edit `data/pipelines/<name>.json` (or via the Playground **Create** view) to add, remove, or reorder pipes.

**Both changes are safe to make without updating client code.** Client requests keep the same shape (`POST /process/<mode>` with `{text: ...}`) and the response keeps the same shape (`{spans: [{start, end, label, ...}], ...}`). The label set may change — that's expected. Each shipped pipeline declares its `output_label_space` field; the seven default pipelines all share the same canonical 8-label space (`AGE, DATE, EMAIL, ID, LOCATION, NAME, ORGANIZATION, PHONE`), but a custom pipeline can declare any label set the operator wants.

What's *not* part of the contract — and may shift when you change the underlying pipeline:

- Which substrings get marked (regex-only finds different spans than an LLM).
- Per-span `source` field (`"regex_ner"` vs `"llm_ner"` vs `"presidio_ner"`, …).
- Per-span `confidence` field (populated by HF/LLM, `null` for regex/whitelist).
- Latency, determinism, and per-call cost (a `fast` mode backed by an LLM pipeline costs money and takes seconds).
- Runtime dependencies (swapping to an LLM-backed pipeline requires `OPENAI_API_KEY`; swapping to a HuggingFace pipeline requires the model under `models/huggingface/`).

So the contract is: **mode name + response schema**. Treat mode names as a versioned interface — if you want a category change (e.g. introduce LLM-backed inference), ship a new mode (`llm`, `ensemble`, …) rather than repointing an existing one. The 7 shipped modes follow this convention: `fast` is always regex-only, `transformer` always uses HuggingFace, `llm` always calls an LLM, etc.

## Authentication

When `CLINICAL_DEID_ADMIN_API_KEYS` and `CLINICAL_DEID_INFERENCE_API_KEYS` are both empty, auth is **off** (local dev). When either list is non-empty, clients must send `Authorization: Bearer <key>` or `X-API-Key: <key>`.

Scopes are documented in [Configuration — Authentication](configuration.md#authentication). Inference keys are limited to `/process/*`, label-space compute, `GET /deploy/health`, and audit reads; admin keys have full access.

OpenAPI (`/docs`, `/redoc`, `/openapi.json`) is **disabled** for anonymous clients when auth is enabled.

## Hardening

- **`CLINICAL_DEID_MAX_BODY_BYTES`** — rejects oversized `Content-Length` with `413` (see [Configuration](configuration.md#request-body-limits)).
- **Rate limits and TLS** — use your reverse proxy or load balancer (recommended), not only the app.

## Smoke test

After deploy, verify `/health` returns `200`, run `POST /process/fast` (or `POST /process/clinical-fast`) with sample text, and check `GET /audit/logs` shows the request.
