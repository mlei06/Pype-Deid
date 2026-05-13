# PypeDeid — Project Overview

Use this document to understand the full scope of the project before suggesting changes. It covers what exists, what's planned, how the pieces connect, and the key design decisions already made.

---

## What this project does

A **deployable de-identification service** for clinical text. The system is built to run as a self-hosted container (FastAPI + SQLite audit, packaged via the bundled `Dockerfile` / `compose.yaml`) inside the operator's own infrastructure, so PHI and model artifacts never cross the trust boundary. Three complementary threads:

1. **In-cluster training** — Prepare annotated data, export to your trainer (spaCy, HuggingFace, etc.), and train or fine-tune models inside your own environment. Artifacts live under `models/` (see `models/README.md`) and are referenced from pipe configs so detectors stay reproducible.

2. **Pipeline composition** — Configure **pipes** (regex, whitelist, Presidio, LLM, HuggingFace, combinators, redactors) and compose them into named **pipelines** (JSON files in `data/pipelines/`, registry-backed). The API supports creating/updating pipelines, validation, and machine-readable config schemas with `ui_*` hints for building forms.

3. **Service-mode inference** — Expose **HTTP endpoints** so upstream systems send text (or batch items) and receive de-identified output plus **auditable** metadata: `request_id`, spans, timings, pipeline name, and optional **intermediary traces** when the pipeline enables step capture. All operations are logged to a unified SQLite audit trail. Production posture is enforced via explicit gates (`PYPEDEID_AUTH_DISABLED`, `PYPEDEID_ALLOW_EXTERNAL_LLM`) so an unconfigured deployment refuses to start.

4. **Playground UI** — A **React + TypeScript web UI** (Vite, Tailwind CSS) with nine views: **(a)** visual pipeline builder, **(b)** pipeline catalog, **(c)** inference with span highlighting and step trace, **(d)** eval dashboard with metrics/confusion matrix/comparison, **(e)** dataset management (register, compose, transform, generate), **(f)** dictionary management, **(g)** deploy configuration (inference modes, pipeline allowlist), **(h)** audit log viewer with stats, **(i)** production NER workspace.

---

## Design priorities

1. **Minimal setup for new pipes (highest)** — Adding a detector, transformer, or redactor should stay a **small, local change**: Pydantic config + `forward` implementation + **one `register()` call** (and optionally one **catalog** line for install hints / role). Pipes should not require edits to the process router, pipeline loader, or UI beyond what JSON Schema + `ui_*` hints already provide.
2. **Composable pipelines** — JSON-defined sequential and parallel graphs, validation before save.
3. **Observable inference** — Rich process responses, persistent audit trail, eval metrics.
4. **Training + eval loop** — In-environment training artifacts, eval on disk or uploads, compare runs over time.

---

## Current state of the codebase

FastAPI backend with SQLite for audit only, React + TypeScript frontend. Python 3.11+.

### What's built and working

| Component | Details |
|---|---|
| **Domain models** | `Document` (id, text, metadata), `EntitySpan` (start, end, label, confidence, source), `AnnotatedDocument` (document + spans). Universal contract across all services. |
| **Pipe system** | Protocol-based: `Pipe.forward(AnnotatedDocument) -> AnnotatedDocument`. Subtypes: `Detector`, `Preprocessor`, `SpanTransformer`, `Redactor`. |
| **Built-in pipes (catalog)** | Detectors: `regex_ner`, `whitelist`, `presidio_ner`, `llm_ner`, `neuroner_ner`, `huggingface_ner`. Span transforms: `label_mapper` (document-wide remaps), `label_filter`, `resolve_spans`, `blacklist`, `consistency_propagator`. Redaction/surrogate **text** is applied at the API via `output_mode` on `/process` (spans-only pipelines preferred). Legacy redactor modules may exist on disk but are not the primary pattern. |
| **Pipeline composition** | JSON pipelines are a **sequential** list of pipes. Combine multiple detectors by listing them one after another, then merge overlaps with `resolve_spans` (strategies include union, consensus, max-confidence, longest-non-overlapping, exact-dedupe). |
| **Pipe registry** | Maps type names to (config_class, pipe_class) pairs. JSON serialization/deserialization. Adding a new detector = config class + pipe class + one `register()` call. |
| **Pipeline entry points** | **CLI** `--profile`: `fast` / `balanced` / `accurate` (in-memory; default **balanced** if no `--pipeline`). **Shipped** JSON: `clinical-fast`, `presidio`, `clinical-transformer`, `clinical-transformer-presidio` in `data/pipelines/`. **HTTP/Production** mode aliases in `data/modes.json` (e.g. `fast` → `clinical-fast`, **`default_mode`**: `fast`) — not the same strings as all CLI profile names. |
| **CLI** | `run` (stdin/files), `batch` (directory/JSONL), `eval` (gold corpus), `train run/show`, `dict` (list/preview/import/delete), `dataset` (list/register/show/delete/export), `audit list/show`, `setup`, `serve`. Pipeline commands support `--profile`, `--pipeline`, `--config`, `--redactor`. |
| **API** | Single app: pipeline CRUD, process (single + batch + redact + scrub), evaluation, datasets (incl. training export formats), dictionaries, audit (logs/stats + production proxy), deploy (incl. `GET /deploy/health`), models, saved inference snapshots. Optional scoped API keys (see `docs/configuration.md`). |
| **Evaluation** | 4 matching modes (strict, exact boundary, partial overlap, token-level BIO), risk-weighted recall, HIPAA Safe Harbor coverage, per-label breakdown, confusion matrix, worst-document ranking. |
| **Storage** | Filesystem-first: pipelines as JSON, eval results as JSON, models as directories. SQLite only for append-only audit trail. |
| **Dataset ingestion** | JSONL, BRAT (.txt/.ann with splits), ASQ-PHI, MIMIC synthetic notes, PhysioNet i2b2. |
| **Analytics** | Label distribution, span length histogram, docs-by-span-count, overlapping spans, label co-occurrence matrix. |
| **Transforms** | Label remapping, random resize (downsample/upsample), boost by label, train/valid/test split reassignment. |
| **Composition** | Merge, interleave, proportional sampling across multiple corpora. |
| **LLM synthesis** | Few-shot clinical note generation via OpenAI-compatible API. Prompt templates, PHI extraction, span alignment. |
| **Playground UI** | React + TypeScript (Vite, Tailwind). 9 views: pipeline catalog, pipeline builder, inference, eval dashboard, datasets, dictionaries, deploy config, audit log viewer, production NER workspace. |
| **Dataset API + CLI** | REST API: register, browse, compose, transform, LLM generate. CLI: `dataset list/register/show/delete`. |
| **Deploy config** | Inference modes mapped to pipelines and pipeline allowlist — managed via UI and `data/modes.json`. |
| **Tests** | 27+ test files covering API, ingestion, analytics, transforms, synthesis, config, compose, pipeline execution, span resolution, datasets, eval. |

### Training and models

| Capability | Status |
|---|---|
| **Training data export** (CoNLL, spaCy DocBin, Hugging Face JSONL, BRAT) | `pypedeid dataset export` and `POST /datasets/{name}/export` |
| **HF fine-tuning CLI** | `pypedeid train run` (requires `pip install '.[train]'`) |
| **Runtime HF NER** | `huggingface_ner` pipe + artifacts under `models/huggingface/{name}/` |

---

## Architecture

Two separate frontend SPAs share a single FastAPI backend. They differ only in
which API key they ship and therefore which routes the backend allows:

```
  +------------------------------+   +-----------------------------------------+
  | Playground UI  (frontend/)   |   | Production UI  (frontend-production/)    |
  | admin API key                |   | inference API key                        |
  | /create /pipelines           |   | Batch NER workspace — load a dataset,    |
  | /inference /evaluate         |   | review detections, resolve, export.      |
  | /datasets /dictionaries      |   | Access: POST /process/*, GET /deploy/    |
  | /deploy /audit /production   |   | health, audit reads (read-only).         |
  +-------------+----------------+   +---------------------+--------------------+
                |                                          |
                +------------------+-----------------------+
                                   |
                           FastAPI Gateway
                                   |
  +----------+----------+----------+--------+-----------+-----------+
  |          |          |          |        |           |           |
  v          v          v          v        v           v           v
Pipeline   Process   Eval      Dataset  Dictionary  Deploy     Audit
Service    Service   Service   Service  Service     Service    Service

  +----------+----------+
  |          |          |
  v          v          v
Data prep  Training   Model
+ library  (local     Directory
(scripts)  CLI)       (FS registry)
```

---

## Storage architecture

**Filesystem-first, database only for audit.**

| Store | Implementation | Files |
|-------|---------------|-------|
| **Pipelines** | `pipeline_store.py` — `list_pipelines()`, `load_pipeline_config()`, `save_pipeline_config()`, `delete_pipeline()` | `data/pipelines/{name}.json` |
| **Eval results** | `eval_store.py` — `save_eval_result()`, `list_eval_results()`, `load_eval_result()` | `data/evaluations/{pipeline}_{timestamp}.json` |
| **Models** | `models.py` — `scan_models()` reads `model_manifest.json` from `models/{framework}/{name}/` | Filesystem directories |
| **Audit log** | `audit.py` — `log_run()`, `list_runs()`, `get_run()` via SQLModel | `data/app.sqlite`, table `audit_log` |

The `AuditLogRecord` table schema:

| Field | Type | Description |
|-------|------|-------------|
| `id` | str (UUID) | Primary key |
| `timestamp` | datetime | UTC |
| `user` | str | OS username |
| `command` | str | "run", "batch", "eval", "process", "process_batch" |
| `pipeline_name` | str | Pipeline that ran |
| `pipeline_config` | JSON | Full config snapshot |
| `dataset_source` | str | Filesystem path or "" |
| `doc_count` | int | Documents processed |
| `error_count` | int | Errors encountered |
| `span_count` | int | Total spans detected |
| `duration_seconds` | float | Wall-clock time |
| `metrics` | JSON | Eval metrics or span counts |
| `source` | str | e.g. `cli`, `api-admin`, `api-inference` |
| `client_id` | str | Hashed API key id when auth is used |
| `output_mode` | str | `annotated` / `redacted` / `surrogate` when applicable |
| `service_type` | str | e.g. `inference`, `batch`, `scrub`, `redact` |
| `notes` | str | Optional notes |

---

## How the pipe system works

This is the core abstraction. Everything flows through `AnnotatedDocument`.

### The protocol

```python
class Pipe(Protocol):
    def forward(self, doc: AnnotatedDocument) -> AnnotatedDocument: ...

class Detector(Pipe, Protocol):
    @property
    def labels(self) -> set[str]: ...
```

### Adding a new detector (minimal setup)

```python
# 1. Config (Pydantic -- serializable)
class MyConfig(BaseModel):
    some_param: str = "default"

# 2. Pipe class
class MyPipe:
    def __init__(self, config: MyConfig | None = None):
        self._config = config or MyConfig()
    @property
    def labels(self) -> set[str]: ...
    def forward(self, doc: AnnotatedDocument) -> AnnotatedDocument: ...

# 3. Register
register("my_pipe", MyConfig, MyPipe)
```

After registration, it works in pipeline JSON configs, the CRUD API, the process endpoint, evaluation, and CLI — zero other code changes.

### Pipeline composition

Sequential:
```json
{"pipes": [{"type": "regex_ner"}, {"type": "blacklist"}, {"type": "resolve_spans"}]}
```

Multiple detectors then consensus merge (no `parallel` pipe type — use a linear list):
```json
{
  "pipes": [
    {"type": "regex_ner"},
    {"type": "presidio_ner"},
    {"type": "llm_ner", "config": {"model": "gpt-4o-mini"}},
    {"type": "resolve_spans", "config": {"strategy": "consensus", "consensus_threshold": 2}}
  ]
}
```

`resolve_spans` strategies: `union`, `exact_dedupe`, `consensus`, `max_confidence`, `longest_non_overlapping`.

---

## API endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `GET` | `/pipelines/pipe-types` | Pipe catalog, install hints, JSON Schema (+ `ui_*`) for configs |
| `GET` | `/pipelines/ner/builtins` | Bundled regex / whitelist label names |
| `POST` | `/pipelines/whitelist/parse-lists` | Parse uploaded list files for whitelist config |
| `POST` | `/pipelines/blacklist/parse-wordlists` | Merge wordlist uploads for blacklist |
| `POST` | `/pipelines` | Create named pipeline from JSON config |
| `GET` | `/pipelines` | List pipelines |
| `GET` | `/pipelines/{name}` | Pipeline config |
| `PUT` | `/pipelines/{name}` | Update pipeline config |
| `DELETE` | `/pipelines/{name}` | Delete pipeline |
| `POST` | `/pipelines/{name}/validate` | Dry-run validation |
| `GET` | `/dictionaries` | List dictionaries |
| `GET` | `/dictionaries/{kind}/{name}` | Dictionary metadata |
| `GET` | `/dictionaries/{kind}/{name}/preview` | Preview terms |
| `GET` | `/dictionaries/{kind}/{name}/terms` | Full term list (paginated) |
| `POST` | `/dictionaries` | Upload dictionary |
| `DELETE` | `/dictionaries/{kind}/{name}` | Delete dictionary |
| `GET` | `/datasets` | List registered datasets |
| `POST` | `/datasets` | Register dataset from local path |
| `POST` | `/datasets/upload` | Multipart JSONL upload |
| `POST` | `/datasets/import/brat` | Convert BRAT tree on disk → JSONL |
| `GET` | `/datasets/{name}` | Dataset detail + analytics |
| `PUT` | `/datasets/{name}` | Update description/metadata |
| `DELETE` | `/datasets/{name}` | Delete dataset directory under corpora |
| `POST` | `/datasets/{name}/refresh` | Recompute analytics |
| `GET` | `/datasets/{name}/preview` | Preview documents (paginated) |
| `GET` | `/datasets/{name}/documents/{doc_id}` | Full document with spans |
| `POST` | `/datasets/{name}/export` | Export to CoNLL/spaCy/HuggingFace/BRAT |
| `POST` | `/datasets/compose` | Compose multiple datasets |
| `POST` | `/datasets/transform` | Apply transforms to dataset |
| `POST` | `/datasets/generate` | Generate synthetic data via LLM |
| `POST` | `/process/redact` | Redact/surrogate from edited spans |
| `POST` | `/process/scrub` | Zero-config clean using default mode |
| `POST` | `/process/{pipeline_name}` | Run pipeline on text; auditable JSON response |
| `POST` | `/process/{pipeline_name}/batch` | Batch process |
| `POST` | `/eval/run` | Run pipeline against gold dataset |
| `GET` | `/eval/runs` | List eval results |
| `GET` | `/eval/runs/{id}` | Eval result detail |
| `POST` | `/eval/compare` | Compare two eval runs |
| `GET` | `/audit/logs` | Query audit trail (paginated, filtered) |
| `GET` | `/audit/logs/{id}` | Audit log detail |
| `GET` | `/audit/stats` | Aggregate stats |
| `GET` | `/deploy` | Get deploy config (modes + allowlist) |
| `PUT` | `/deploy` | Update deploy config |
| `GET` | `/deploy/health` | Per-mode availability |
| `GET` | `/deploy/pipelines` | List deployable pipeline names |
| `GET` | `/models` | List models from filesystem |
| `GET` | `/models/{framework}/{name}` | Model manifest details |
| `POST` | `/models/refresh` | Re-scan models directory |

---

## Module structure

```
src/pypedeid/
  domain.py                  # Document, EntitySpan, AnnotatedDocument
  tables.py                  # AuditLogRecord (only DB table)
  db.py                      # SQLite engine, init_db()
  config.py                  # Settings (pydantic-settings), .env loading
  audit.py                   # Unified audit: log_run(), list_runs(), get_run()
  pipeline_store.py          # Filesystem pipeline CRUD
  eval_store.py              # Filesystem eval result storage
  models.py                  # Filesystem model registry (scan, get, list)
  profiles.py                # fast/balanced/accurate profile builders
  cli.py                     # Click CLI (run, batch, eval, dict, dataset, audit, setup, serve)
  dataset_store.py           # Filesystem dataset registry (register, list, analytics)
  dictionary_store.py        # Whitelist/blacklist term-list CRUD
  mode_config.py             # Deploy config (data/modes.json) load/save
  export.py                  # Output formatters (text, JSON, JSONL, CSV, Parquet)
  ids.py                     # UUID helpers
  env_file.py                # .env resolution
  pipes/
    base.py                  # Pipe, Detector, Preprocessor, SpanTransformer, Redactor protocols
    registry.py              # Type registry, JSON load/dump, pipe catalog
    ui_schema.py             # field_ui, pipe_config_json_schema (UI hints in JSON Schema)
    span_merge.py            # Merge strategies (union, consensus, max_confidence, etc.)
    trace.py                 # Intermediary trace capture
    detector_label_mapping.py # Shared label mapping utilities
    combinators.py           # Pipeline, ResolveSpans, LabelMapper, LabelFilter
    span_resolver.py         # Overlap resolution (longest, highest_confidence, priority)
    consistency_propagator.py # Document-level span propagation
    llm_ner.py               # LLM-prompted detection
    regex_ner/               # Regex-based PHI detection
    whitelist/               # Phrase/dictionary matching
    blacklist/               # False-positive filtering
    presidio_ner/            # Microsoft Presidio wrapper
    huggingface_ner/         # HF token-classification models under models/huggingface/
    neuroner_ner/            # NeuroNER HTTP client
    presidio_anonymizer/     # Presidio redaction (legacy; not in default pipe catalog)
    surrogate/               # Surrogate replacement (legacy; not in default pipe catalog)
  api/
    app.py                   # FastAPI app, CORS, lifespan, router mounting
    deps.py                  # Dependency injection (DB session for audit)
    schemas.py               # Request/response models
    routers/
      pipelines.py           # Pipeline CRUD, pipe-types, validate, list helpers
      process.py             # Inference (text + batch), audit logging
      evaluation.py          # Eval run/list/compare (filesystem-backed)
      datasets.py            # Dataset register/browse/compose/transform/generate
      dictionaries.py        # Dictionary CRUD (upload, list, preview, delete)
      audit.py               # Audit log query + stats
      deploy.py              # Deploy config (modes, allowlist)
      models.py              # Model listing (filesystem-backed)
  eval/
    spans.py                 # strict_micro_f1, SpanMicroF1
    matching.py              # 4 matching modes (strict, exact boundary, partial, token-level)
    risk.py                  # Risk-weighted recall, HIPAA coverage report
    runner.py                # Batch eval runner with per-label/per-doc results
  analytics/
    stats.py                 # Label distribution, histograms, overlaps, co-occurrence
  ingest/
    jsonl.py, brat.py, asq_phi.py, sources.py, sink.py, brat_write.py
    mimic/                   # Synthetic MIMIC note generation
  transform/
    ops.py                   # Label map, resize, boost
    splits.py                # Train/valid/test reassignment
  compose/
    flatten.py, strategies.py, pipeline.py, load.py
  synthesis/
    client.py, template.py, components.py, parse.py, align.py, presets.py, synthesizer.py
  pipeline/
    job.py                   # Pipeline job execution
```

---

## Key design decisions

1. **Registry-first extensibility** — New pipe types are added with **config model + pipe class + `register()`** (and optional catalog metadata). Process, pipeline load/dump, and `/pipelines/pipe-types` stay generic.
2. **Pipes are pure transformations** — `AnnotatedDocument -> AnnotatedDocument`. No side effects, no awareness of pipeline context.
3. **Serializable configs + UI hints** — Pydantic + JSON Schema; `ui_*` keys for generated forms.
4. **Model directory, not model database** — training is local-only (CLI). The filesystem is the registry. API is read-only.
5. **Filesystem-first storage** — Pipelines, eval results, and models live on the filesystem as JSON/directories. Use git for history. No migrations.
6. **SQLite only for audit** — The database stores only the append-only audit trail (`AuditLogRecord`). Both CLI and API write to the same table.
7. **Multi-mode evaluation** — strict, partial-overlap, token-level, and exact-boundary matching. Per-label breakdowns, risk-weighted recall, label confusion matrix, HIPAA coverage reporting. Same runner for CLI and API.
8. **Two ways to pick a pipeline** — (a) **CLI** `--profile` `fast` / `balanced` / `accurate` (default **balanced** when not using `--pipeline`); (b) **saved** `data/pipelines/{name}.json` plus **deploy** `data/modes.json` aliases for `POST /process/{mode}` (seeded `fast`, `presidio`, `transformer`, `transformer_presidio`; **`default_mode`**: `fast` → `clinical-fast`).
9. **Name-based pipeline routes** — Pipelines are identified by name (e.g., `/pipelines/my-pipeline`), not UUIDs. Simpler, human-readable, filesystem-backed.
10. **One eval implementation, many ingest paths** — local filesystem, API request, or future UI uploads should all normalize to `AnnotatedDocument` iterators before scoring.

---

## Tech stack

- **Backend:** Python 3.11+, FastAPI, Pydantic v2, SQLModel (SQLAlchemy), Uvicorn
- **ML/NLP:** spaCy, HuggingFace Transformers, Microsoft Presidio
- **LLM:** OpenAI-compatible API client
- **Testing:** Pytest, Faker, HTTPx (async test client)
- **Data:** Pandas (scripts), custom JSONL/BRAT parsers
- **Frontend:** React, TypeScript, Vite, Tailwind CSS, TanStack Query
- **Storage:** SQLite (audit only), local filesystem for everything else

---

## The full loop

```
1. Ingest data        -> JSONL, BRAT, ASQ-PHI, MIMIC
2. Prepare data       -> label remap, compose, augment with LLM synthesis
                         UI: /datasets (register, compose, transform, generate)
                         CLI: pypedeid dataset register/list/show
3. Export             -> pypedeid dataset export (CoNLL/spaCy/HuggingFace/BRAT)
4. Train              -> pypedeid train run (outputs under models/huggingface/)
5. Available          -> model directory scanned, appears in GET /models
6. Build pipeline     -> UI: /create (visual builder) or POST /pipelines
7. Evaluate pipeline  -> UI: /evaluate or pypedeid eval or POST /eval/run
8. Try interactively  -> UI: /inference — paste text, see spans + trace
9. Configure deploy   -> UI: /deploy — map modes to pipelines, set allowlist
10. Deploy pipeline   -> POST /process/{pipeline_name} (with audit logging)
11. Monitor           -> UI: /audit or pypedeid audit list or GET /audit/logs
12. Retrain           -> new data or failed cases -> back to step 2
```
