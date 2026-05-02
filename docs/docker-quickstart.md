# Docker quick start

Stand up the backend API in Docker and point a frontend at it. For the broader
production layout (topology, hardening, scopes), see
[deployment.md](deployment.md).

## TL;DR with Compose

```bash
# From the repo root
docker compose up --build        # builds + starts on :8000
curl http://localhost:8000/health
docker compose logs -f api
docker compose down
```

`compose.yaml` wires volumes, env vars, and the healthcheck. It also attaches
an optional root `.env` (if present) so API keys and other secrets are not
overridden by empty defaults — see [deployment.md](deployment.md#production-checklist).

**CORS:** the sample Compose file lists both SPAs (`:3000` and `:3001`, localhost
and `127.0.0.1`). If you only set CORS in `.env`, remember that variables
explicitly listed under `environment:` in `compose.yaml` take precedence for
those keys.

## 1. Build the backend image

The `Dockerfile` at the repo root is the single production image
(`clinical-deid-api`). Extras are selected at build time via the `EXTRAS`
build arg.

```bash
# Default extras: parquet + scripts (Faker/pandas for surrogate output).
# Presidio, spaCy, transformers/torch, and the LLM clients are now in the
# base install — no extras needed for inference. Add `train` only if you
# plan to run `clinical-deid train run` (datasets/seqeval/accelerate).
docker build -t clinical-deid-api .

# Add `train` for HuggingFace fine-tuning inside the container.
docker build -t clinical-deid-api \
    --build-arg EXTRAS=parquet,scripts,train .
```

See `pyproject.toml` for the full extras list.

## 2. Required environment variables

The container ships with working defaults for every path (see the `ENV` block
in `Dockerfile`). The settings you actually need to think about:

| Variable | When to set | Notes |
|----------|-------------|-------|
| `CLINICAL_DEID_CORS_ORIGINS` | Any browser SPA hits the API | JSON array. In-app default (no env) is `localhost:3000` and `127.0.0.1:3000` only; root `compose.yaml` also lists `:3001` for both SPAs. Add every real origin you use. |
| `CLINICAL_DEID_ADMIN_API_KEYS` | Any shared/production host | JSON array. Full access (pipeline edits, deploy config, audit). |
| `CLINICAL_DEID_INFERENCE_API_KEYS` | Production UI / inference callers | JSON array. Limited to `/process/*`, label-space compute, `GET /deploy/health`, audit reads. |
| `CLINICAL_DEID_MAX_BODY_BYTES` | Batch / large-document workloads | Default `10485760` (10 MiB). Requests above this return `413`. |
| `CLINICAL_DEID_NEURONER_HTTP_URL` | A pipeline uses `neuroner_ner` | URL of the optional sidecar (e.g. `http://neuroner:8765`). |
| `WEB_CONCURRENCY` | Tune for host | Uvicorn workers. Default `1` in the image, `2` in `compose.yaml`. With the default **SQLite** audit DB, `1` avoids most concurrent-write lock errors; see [deployment.md](deployment.md#production-checklist). |
| `OPENAI_API_KEY` | `llm_ner` pipe or LLM dataset synthesis | Or `CLINICAL_DEID_OPENAI_API_KEY`. `OPENAI_BASE_URL` / `OPENAI_MODEL` for non-default endpoints. |

Auth is **off** only when both key lists are empty or unset. When either is
non-empty, clients must send `Authorization: Bearer <key>` or
`X-API-Key: <key>`, and OpenAPI (`/docs`, `/redoc`, `/openapi.json`) is hidden
from anonymous callers. Full scope matrix: [configuration.md](configuration.md#authentication).

The [root `.env.example`](../.env.example) is the authoritative list — every
knob the backend reads.

## 3. Mount the right volumes

Two volumes — everything mutable under `./data`, model weights under `./models`
read-only. The in-image paths match the defaults from `Dockerfile`, so the
mounts are just:

| Host | Container | Mode | Contents |
|------|-----------|------|----------|
| `./data` | `/app/data` | `rw` | `pipelines/`, `modes.json`, `evaluations/`, `inference_runs/`, `corpora/`, `exports/`, `dictionaries/`, `app.sqlite` |
| `./models` | `/app/models` | `ro` | Model weights under `{framework}/{name}/` |

`./data` **must** be writable — the API writes the SQLite audit log, saves eval
results, and persists pipeline/deploy edits made in the Playground UI.
`./models` is read-only at runtime; add new checkpoints on disk and hit
`POST /models/refresh` (or restart) to pick them up.

## 4. Plain `docker run` (without Compose)

```bash
docker run --rm -p 8000:8000 \
    -v "$(pwd)/data:/app/data" \
    -v "$(pwd)/models:/app/models:ro" \
    -e CLINICAL_DEID_CORS_ORIGINS='["http://localhost:3000","http://localhost:3001"]' \
    -e CLINICAL_DEID_ADMIN_API_KEYS='["change-me-admin"]' \
    -e CLINICAL_DEID_INFERENCE_API_KEYS='["change-me-inference"]' \
    -e WEB_CONCURRENCY=2 \
    clinical-deid-api
```

Verify:

```bash
curl -fsS http://localhost:8000/health
# With auth enabled:
curl -fsS -H "X-API-Key: change-me-admin" http://localhost:8000/pipelines
```

## 5. Optional: NeuroNER sidecar

Only needed if a deployed pipeline uses the `neuroner_ner` pipe. The sidecar
image (`neuroner-cspmc/sidecar/Dockerfile`) is commented out in `compose.yaml`
— uncomment that block and set `CLINICAL_DEID_NEURONER_HTTP_URL` on the API
service. End-to-end build/deploy steps: [neuroner-setup.md](neuroner-setup.md).

## 6. Point a frontend at the API

Both SPAs (`frontend/` = Playground admin, `frontend-production/` = inference
UI) read the same two Vite env vars at build or dev time. Copy
`frontend/.env.example` → `frontend/.env.local` (same for `frontend-production/`)
and set:

```env
VITE_API_BASE_URL=http://localhost:8000      # or https://api.your-host
VITE_API_KEY=                                # admin key for Playground, inference key for production UI
```

- Leave `VITE_API_BASE_URL` **unset** only when using `npm run dev` locally — the
  Vite dev server proxies `/api/*` to `http://localhost:8000`. Any other setup
  (plain `vite preview`, a built bundle, a remote API) needs the full URL.
- `VITE_API_KEY` is sent as `X-API-Key` on every request. Omit when the API
  has auth disabled.
- Whatever origin the SPA serves from must be in the backend's
  `CLINICAL_DEID_CORS_ORIGINS` — this is the most common first-boot 4xx.

Dev:

```bash
cd frontend && npm install && npm run dev          # http://localhost:3000
cd frontend-production && npm install && npm run dev   # http://localhost:3001
```

Production build:

```bash
cd frontend && npm run build            # static files in dist/
# Serve dist/ behind any static host; ensure the SPA origin is in CORS_ORIGINS.
```

Set `VITE_API_BASE_URL` (and `VITE_API_KEY` if the API uses auth) **before**
`npm run build` — Vite inlines `import.meta.env` at compile time, so changing
`.env` after the build has no effect on the bundle.

## 7. Post-deploy sanity check

After the first bring-up, verify `/health` returns `200`, confirm auth scopes work by hitting a protected endpoint with your API key, run a real `/process` call, and check `/audit/logs` shows the request.
