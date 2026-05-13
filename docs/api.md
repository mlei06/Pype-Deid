# HTTP API reference

The FastAPI app is `pypedeid.api.app:app`.

```bash
pypedeid-api
# or: uvicorn pypedeid.api.app:app --reload --host 127.0.0.1 --port 8000
```

Default base URL: `http://127.0.0.1:8000`.

## Security and documentation

- **Optional API keys** — When `PYPEDEID_ADMIN_API_KEYS` and `PYPEDEID_INFERENCE_API_KEYS` are both empty, the API accepts unauthenticated requests (local dev). When either list is set, send `Authorization: Bearer <key>` or `X-API-Key: <key>`. Scopes and route policy: [Configuration — Authentication](configuration.md#authentication).
- **OpenAPI** — `/docs`, `/redoc`, and `/openapi.json` are available when auth is **off**; they are **removed** when auth is **on** (no anonymous schema).
- **CORS** — `PYPEDEID_CORS_ORIGINS` (JSON array). Defaults allow local Playground origins.
- **Body size** — Requests with `Content-Length` above `PYPEDEID_MAX_BODY_BYTES` receive `413` before handlers run. Chunked requests without `Content-Length` are not capped by this middleware.

Do not expose the service to the public internet without TLS, auth, and rate limiting at the edge.

---

## Health

### `GET /health`

Liveness. Always unauthenticated.

**Response:** `status`, `label_space_name` (active `PYPEDEID_LABEL_SPACE_NAME` — used for `POST /process` span label normalization), `risk_profile_name` (default for eval risk-weighted metrics when not overridden), and optional `api_key_scope` (`"admin"` \| `"inference"` \| `null`). When auth is enabled, send the same `X-API-Key` the browser uses; the field reflects that key’s scope so SPAs can enable admin-only actions (e.g. dataset register). When auth is disabled, `api_key_scope` is `"admin"`. Example: `{"status":"ok","label_space_name":"clinical_phi","risk_profile_name":"clinical_phi","api_key_scope":"admin"}`.

---

## Pipelines

Base path: `/pipelines`. Pipelines are **named JSON files** on disk (`data/pipelines/{name}.json`), not versioned rows in a database.

When auth is on, **admin** keys are required for all routes below except **`POST /pipelines/pipe-types/{name}/labels`**, which accepts **admin or inference** keys (label-space compute only).

### `GET /pipelines/pipe-types`

Pipe catalog: install status, roles, JSON Schema (+ `ui_*` hints).

### `GET /pipelines/pipe-types/{name}/label-space-bundle`

Per-detector label bundle (bundle-mode detectors: Presidio, NeuroNER, Hugging Face, etc.).

### `POST /pipelines/pipe-types/{name}/labels`

Compute label list for a detector given optional JSON config body.

### `POST /pipelines/prefix-label-space`

Symbolic **upstream** label set for a pipe at a given `step_index` in `config.pipes` (used by the pipeline builder to suggest `label_mapper` keys). Request body: `{ "config": { "pipes": [...] }, "step_index": <int> }`. Returns `{ "labels": [...], "error": null | str }` on non-fatal load failures.

### `GET /pipelines/ner/builtins`

Built-in regex labels and whitelist dictionary labels.

### `POST /pipelines/whitelist/parse-lists` / `POST /pipelines/blacklist/parse-wordlists`

Multipart helpers for the pipeline builder (admin).

### `POST /pipelines`

Create pipeline (writes `data/pipelines/{name}.json`).

### `GET /pipelines`

List all pipelines (name + full config).

### `GET /pipelines/{pipeline_name}`

Load one pipeline config.

### `PUT /pipelines/{pipeline_name}` / `DELETE /pipelines/{pipeline_name}`

Update or delete pipeline file.

### `POST /pipelines/{pipeline_name}/validate`

Validates a pipeline and returns `output_label_space` when the graph loads. Body: optional `config` (full pipeline JSON). **Omit `config` or send `{}` / `null`** to load the **saved** pipeline file from `data/pipelines/{name}.json` — this matches the Playground “Compute / refresh” action.

---

## Process (inference)

Base path: `/process`. **`inference`-scoped** keys may call these routes; **`admin`** keys always can. For **`inference`** callers, the resolved pipeline name must appear on the deploy **allowlist** in `data/modes.json` when `allowed_pipelines` is set; **admin** bypasses the allowlist.

`{pipeline_name}` may be a **saved pipeline name** (JSON stem, e.g. `clinical-fast`) or a **mode alias** from `data/modes.json` (seeded: `fast`, `presidio`, `transformer`, `transformer_presidio`). The deploy **`default_mode`** (seeded: `fast`) is used by `/process/scrub` when the client does not override the mode.

Query parameters on run endpoints include:

- `output_mode` — `annotated` | `redacted` | `surrogate` (default `redacted`). Pipelines produce **spans**; redaction/surrogate text is applied in the API from those spans (surrogate needs Faker / `[scripts]` extra).
- `trace` — `true` to include intermediary trace frames when the pipeline supports it.

### `POST /process/redact`

Apply redaction or surrogate given **final** spans (e.g. after human edit). Body: `text`, `spans`, `output_mode`, optional surrogate seed flags.

### `POST /process/scrub`

Zero-config cleaning: uses `default_mode` from deploy config (or body override) to pick a pipeline, then runs with `output_mode`.

### `POST /process/{pipeline_name}`

Run one document through the pipeline.

**Optional surrogate alignment:** set `include_surrogate_spans: true` together
with `?output_mode=surrogate` to receive a parallel `surrogate_text` and
`surrogate_spans` list whose character offsets point into the surrogate text.
`surrogate_seed` enables deterministic replacement.

### `POST /process/{pipeline_name}/batch`

Batch variant; body lists `items` with `text` and optional `request_id`.

---

## Inference snapshots (admin)

Base path: `/inference`. Saved runs under `data/inference_runs/` — list, get, save, delete (admin only when auth is on).

---

## Evaluation (admin)

Base path: `/eval` — `POST /eval/run`, list/detail/compare runs (admin when auth is on).

Each `POST /eval/run` **persists** a JSON file under `PYPEDEID_EVALUATIONS_DIR` (default `data/evaluations/`) as `{pipeline_name}_{timestamp}.json`. `GET /eval/runs` reads that directory (the Playground **Evaluate** run history). **`pypedeid eval` uses the same store**, so CLI-created files show up in the list too.

### `POST /eval/run`

Core body: `pipeline_name` + one of `dataset_name` / `dataset_path`, optional `dataset_splits`, `risk_profile_name`.

Optional **sampling** (`eval_mode == "sample"`):

| Field | Type | Notes |
|-------|------|-------|
| `eval_mode` | `"full" \| "sample"` | Defaults to `"full"`. |
| `sample_size` | `int` | Required when `sample`; `1 <= sample_size <= len(documents_after_split)` (422 otherwise). |
| `sample_seed` | `int \| null` | Integer → deterministic (stable sort by `document.id`, then `Random(seed).sample`). `null`/omitted → server draws via `secrets.randbits(64)` and echoes it. |

When sampled, the saved eval JSON and `GET /eval/runs/{id}` include `metrics.sample = { eval_mode, sample_size, sample_seed_used, sample_of_total }`. Sampling runs **after** the optional split filter; `sample_of_total` is the split-filtered size.

**Save the sample as a registered dataset** (requires `eval_mode == "sample"`):

```json
{"save_sample_as": {"dataset_name": "train_valid_sample_500", "description": "Optional"}}
```

On success, the new dataset is materialized under `PYPEDEID_CORPORA_DIR/<name>/` with `metadata.provenance` recording `derived_from` (parent dataset name or path), `sample_seed`, `sample_size`, `sample_of_total`, `source_eval_pipeline`, and `source_splits`. The response's `metrics.sample.saved_dataset_name` echoes the new name. Collisions with an existing dataset return **409**; using `save_sample_as` with `eval_mode == "full"` returns **422**.

**Per-document inspection** (response-only — never persisted to the eval JSON):

| Field | Type | Notes |
|-------|------|-------|
| `include_per_document` | `bool` | Default `false`. Adds `metrics.document_level` to the HTTP response with one item per document (`document_id`, full `metrics`, `risk_weighted_recall`, `false_positive_count`, `false_negative_count`), sorted worst strict-F1 first. |
| `include_per_document_spans` | `bool` | Default `false`. Implies `include_per_document`; each item additionally carries `text`, `gold_spans`, `pred_spans`, `false_positives`, `false_negatives` — useful for side-by-side review in the UI, but the payload includes raw document text (admin only). |

The payload is capped at `Settings.eval_per_document_limit` (default **500**, env var `PYPEDEID_EVAL_PER_DOCUMENT_LIMIT`); overflow is flagged via `metrics.document_level_truncated`. Fetching a run via `GET /eval/runs/{id}` will **not** return per-document data — re-run with the flag to inspect again.

---

## Datasets (admin)

Base path: `/datasets` — register, browse, compose, transform, generate, export (see inline routes in OpenAPI or source).

### `POST /datasets/upload`

Multipart form (`Content-Type: multipart/form-data` — do **not** set `Content-Type: application/json` on the same request; let the client set the multipart boundary). **Admin** only.

| Field | Required | Description |
|--------|----------|-------------|
| `name` | yes | New dataset name (same rules as `POST /datasets` — safe identifier, no `..`). |
| `file` | yes | JSONL file. |
| `description` | no | Plain string, stored in the dataset manifest. |
| `metadata` | no | JSON **object** as a string (e.g. `{"k":"v"}`) — invalid JSON or non-object → 422. |
| `line_format` | no | `annotated_jsonl` (default) — one Pydantic `AnnotatedDocument` per line. `production_v1` — each line is a Production UI export line (`schema_version: 1`); the server normalizes to `AnnotatedDocument` before import. |

Returns **201** and the same **DatasetDetail** as `POST /datasets`. Rejects with **409** if the name exists, **422** for invalid corpus or name, **413** if the request exceeds `PYPEDEID_MAX_BODY_BYTES` (and `Content-Length` is set — see [configuration](configuration.md)). Large JSONL in the browser may require raising that cap on the API.

### `POST /datasets/preview-labels`

Body: `{"path": "relative/or/absolute/under/corpora/corpus.jsonl"}`. Resolves a gold JSONL the same way as `POST /eval/run` with `dataset_path` (must stay under `PYPEDEID_CORPORA_DIR`); returns sorted unique span label strings, `document_count`, and `resolved_path`. Used by the Evaluate UI in “Path on server” mode (no full dataset registration required for the label alignment panel).

### `POST /datasets/ingest-from-pipeline`

Run a saved pipeline over raw inputs under `CORPORA_DIR` and register the
annotated output as a new dataset.

```json
{
  "source_path": "raw_txts",
  "pipeline_name": "clinical-fast",
  "output_name": "raw_txts_clinical_fast_silver"
}
```

- `source_path` is resolved **relative to `CORPORA_DIR`** (absolute paths must
  still resolve under it); `..` escapes are rejected with 400.
- `pipeline_name` must be a **saved** pipeline file stem (not a `modes.json` mode alias; use e.g. `clinical-fast` — see `GET /pipelines`).
- `output_name` must not already exist.

### `POST /datasets/{name}/export`

Export formats: `conll`, `spacy`, `huggingface`, `jsonl` (annotated), or `brat`.
The `jsonl` form writes an annotated JSONL that can be re-registered via
`POST /datasets` (`format: "jsonl"`).

Pass `"target_text": "surrogate"` (plus an optional `"surrogate_seed"`) to
project every document through surrogate alignment before writing — both text
and spans reflect the replacement. Overlapping spans are rejected with 422.

---

## Dictionaries (admin)

Base path: `/dictionaries` — list, preview, terms, upload, delete.

---

## Models (admin)

Base path: `/models` — list, detail, `POST /models/refresh` to rescan `models/`.

---

## Deploy

Base path: `/deploy`.

- `GET /deploy` — Full deploy config (modes, allowlist). **Admin.**
- `PUT /deploy` — Write `data/modes.json`. **Admin.**
- `GET /deploy/health` — Per-mode availability (missing deps, missing pipeline file). **Admin or inference.**
- `GET /deploy/pipelines` — Saved pipeline names for dropdowns. **Admin.**

---

## Audit

Base path: `/audit`. **Admin or inference** for log reads.

- `GET /audit/logs`, `GET /audit/logs/{id}`, `GET /audit/stats`

Records carry a `source` field distinguishing callers: `api-admin` (admin-scoped HTTP), `api-inference` (inference-scoped HTTP), or `cli`.

---

## Request limits

| Limit | Typical value | Notes |
|-------|----------------|------|
| Text length | 500,000 characters | `ProcessRequest` / batch items (`schemas.py`) |
| Batch size | 100 items | `MAX_BATCH_SIZE` in `schemas.py` |
| Dictionary / list upload | 2 MB per file | Pipeline helper uploads |
| HTTP body | `PYPEDEID_MAX_BODY_BYTES` (default 10 MiB) | Middleware `Content-Length` check |
| Ingest documents | `max_documents` (default 10,000, max 1,000,000) | `IngestFromPipelineRequest` cap for `/datasets/ingest-from-pipeline` |

---

## Database

SQLite (default `./data/app.sqlite`) holds **only** the append-only **`audit_log`** table. Pipelines, eval results, and models live on the filesystem. Override with `PYPEDEID_DATABASE_URL`.
