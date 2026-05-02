# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project summary

A local-first **named-entity recognition platform** — compose detection pipelines from modular pipes, evaluate against gold-standard corpora, serve inference via HTTP API, and maintain an audit trail.

The default configuration ships a **clinical de-identification pack** (HIPAA Safe Harbor label space, pattern library, surrogate strategies, and risk profile) so the platform works out of the box for PHI detection. The clinical domain is a *pack*, not a baked-in assumption: swap the label space, regex patterns, surrogate strategies, and risk/coverage profile to target any NER task. Built-in alternative: the minimal ``generic_pii`` pack. Custom packs register at startup.

## Quick start

```bash
# Backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"                     # base (presidio + HF + LLM) + tests/lint
python -m spacy download en_core_web_sm     # required for Presidio pipes
clinical-deid setup          # verify deps, init DB, smoke test
clinical-deid serve           # start API on localhost:8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                  # Vite dev server on localhost:3000

# Tests & linting
pytest                        # all tests
pytest tests/test_api.py      # single file
pytest -k "test_process"      # by name pattern
ruff check src/               # lint Python
cd frontend && npm run lint   # lint frontend
```

The base install includes Presidio, HuggingFace inference, and LLM clients. Opt-in extras: `.[dev]` (tests/lint), `.[train]` (fine-tuning: datasets/seqeval/accelerate), `.[scripts]` (pandas/faker for analytics + surrogate mode), `.[parquet]` (pyarrow), `.[all]` (everything). Legacy `.[presidio]`, `.[ner]`, `.[llm]` are kept as no-op back-compat stubs.

Node.js 20.19+ or 22.12+ required for the frontend (Vite 8).

## Architecture

### Storage pattern: filesystem-first, audit in SQLite

All mutable state lives under `data/` and all model weights live under `models/` — a deployment mounts `./data` read-write and `./models` read-only (see `compose.yaml`).

| What | Storage | Location |
|------|---------|----------|
| Pipelines | JSON files | `data/pipelines/{name}.json` (mutable via UI or on disk). **Shipped examples:** `clinical-fast`, `presidio`, `clinical-transformer`, `clinical-transformer-presidio`, `clinical-llm`, `clinical-llm-presidio`, `clinical-ensemble` (tracked JSON). |
| Eval results | JSON files | `data/evaluations/{pipeline}_{timestamp}.json` (Playground **Evaluate**, `POST /eval/run`, and **`clinical-deid eval`** — all browsable in the UI via `GET /eval/runs`) |
| Inference runs | JSON files | `data/inference_runs/{pipeline}_{timestamp}.json` |
| Models | Directories | `models/{framework}/{name}/` |
| Datasets | JSONL under corpora | `data/corpora/{name}/corpus.jsonl` + `dataset.json` (cached analytics). BRAT is ingest/export only — not stored as the canonical corpus layout |
| Dataset exports | Filesystem under `data/exports` | `data/exports/{name}/` for materialized BRAT / training exports from `POST /datasets/{name}/export` (`CLINICAL_DEID_EXPORTS_DIR`) |
| Dictionaries | Term-list files | `data/dictionaries/whitelist/` and `data/dictionaries/blacklist/` (each a flat pool of files; assign names to NER labels in the whitelist pipe) |
| Deploy config | JSON file | `data/modes.json` (`CLINICAL_DEID_MODES_PATH`; mutable via UI or on disk) |
| Audit log | SQLite (SQLModel) | `data/app.sqlite` — `audit_log` table |

No migrations. Pipelines use git for history. The database stores only the append-only audit trail (`AuditLogRecord` in `tables.py`).

### Core abstraction: Pipes and AnnotatedDocument

Everything flows through `AnnotatedDocument` (document + spans). All pipes implement:

```python
class Pipe(Protocol):
    def forward(self, doc: AnnotatedDocument) -> AnnotatedDocument: ...
```

Subtypes: `Detector` (produces spans), `SpanTransformer` (modifies spans), `Redactor` (replaces text), `Preprocessor` (transforms text before detection).

### Pluggable label space

The canonical entity-label schema is a **LabelSpace** (`clinical_deid.labels.LabelSpace`) — a named, frozen bundle of labels + aliases + fallback. The platform ships two built-in packs:

- **`clinical_phi`** (default) — HIPAA Safe Harbor identifiers plus clinical additions (~40 labels).
- **`generic_pii`** — minimal general-purpose PII (NAME, EMAIL, PHONE, ADDRESS, DATE, ID, LOCATION, ORGANIZATION, URL, IP_ADDRESS, OTHER).

Select the active pack via `CLINICAL_DEID_LABEL_SPACE_NAME` (or `Settings.label_space_name`). Register custom packs at startup with `register_label_space(LabelSpace(...))` — pipes then use `get_label_space(name).normalize(raw)` to canonicalize detector output.

Use the label-space API (`get_label_space`, `default_label_space`, `CLINICAL_PHI.normalize`, …) and plain `str` labels — not a special enum. Detectors map internal tags via per-pipe `remap` / `label_mapping` and the active `LabelSpace` normalizes at **inference** (`POST /process/*`) only. **Evaluation** uses raw gold vs raw predicted label strings; align the corpus and pipeline (e.g. a final `label_mapper`) if names differ.

The core span type is `EntitySpan` in `domain.py` (``start``, ``end``, ``label``, optional ``confidence`` / ``source``).

### Pluggable risk profile

Coverage reporting and risk-weighted recall are driven by a **RiskProfile** (`clinical_deid.risk.RiskProfile`) — a named bundle of per-label risk weights plus a coverage scheme (ordered `CoverageIdentifier` list + label→identifier map). Built-in profiles:

- **`clinical_phi`** (default) — HIPAA Safe Harbor's 18 identifiers with clinical-severity weights. Identifier #17 (full-face photographs) is marked non-required (always `n/a` in text).
- **`generic_pii`** — six categorical identifiers (names, contact, location, id, temporal, network) with uniform weights.

Select via `CLINICAL_DEID_RISK_PROFILE_NAME` / `Settings.risk_profile_name`. When `evaluate_pipeline(...)` is called without `risk_profile=`, it uses `default_risk_profile()` from `clinical_deid.risk` (those settings). `POST /eval/run` accepts optional `risk_profile_name` in the JSON body; `clinical-deid eval` accepts optional `--risk-profile` — each overrides the env default for that run. Persisted eval JSON includes `metrics.risk_profile_name` for the profile used. `eval/risk.py` keeps its module-level API (`risk_weighted_recall`, `hipaa_coverage_report`, `DEFAULT_RISK_WEIGHTS`, `HIPAA_IDENTIFIER_NAMES`, `LABEL_TO_HIPAA`) as a thin shim, still derived from the built-in `clinical_phi` profile for backward compatibility.

### Pluggable regex pattern + surrogate packs

- **RegexPatternPack** (`clinical_deid.pipes.regex_ner.packs`) — named `label → regex` bundles. Built-ins: `clinical_phi` (default, 22 labels) and `generic_pii` (universal subset: EMAIL, PHONE, URL, IP_ADDRESS, DATE, SSN). Set via `RegexNerConfig.pattern_pack`.
- **SurrogatePack** (`clinical_deid.pipes.surrogate.packs`) — named `label → strategy` maps over the Faker-backed generators. Built-ins: `clinical_phi` and `generic_pii`. Set via `SurrogateConfig.strategy_pack`.

Custom packs register via `register_pattern_pack(...)` / `register_surrogate_pack(...)` at startup. `BUILTIN_REGEX_PATTERNS` and `SURROGATE_STRATEGIES` stay as back-compat aliases pointing at the clinical pack.

### Redaction as an output mode (not a pipe)

Pipelines should only predict spans. Redaction (tag replacement) and surrogate (fake data) are applied at the API layer via `output_mode` parameter (`annotated`, `redacted`, `surrogate`). Legacy redactor pipes (surrogate, presidio_anonymizer) still work in pipelines for backward compat, but the preferred pattern is `output_mode` on process endpoints. The `/process/redact` endpoint accepts text + user-corrected spans for post-editing export. The `/process/scrub` endpoint provides zero-config log cleaning.

### Pipe registry

Pipes are registered by name via the catalog. After registration, the pipe works in pipeline JSON configs, the API, CLI, and evaluation — zero other code changes.

Adding a new pipe — checklist (the contract test in `tests/test_registry_contract.py` enforces this):

1. **Pydantic config class** in your pipe module.
2. **Pipe class** with `forward(doc) -> AnnotatedDocument`.
3. **`PipeCatalogEntry`** appended to `_CATALOG` in `registry.py` with the dotted import paths.
4. **`default_base_labels_fn`** — only for detectors; returns the label space when no config is supplied.
5. **`label_source`** — one of `"none"` (transformers/redactors), `"compute"` (POST /labels per config), `"bundle"` (one GET, switch models client-side), or `"both"`.
6. **`label_space_bundle_fn` + `bundle_key_semantics`** — required when `label_source` is `"bundle"`/`"both"`. The fn returns `{labels_by_model, default_entity_map, default_model}`. Semantics is `"ner_raw"` (raw NER tags, e.g. NeuroNER) or `"presidio_entity"` (Presidio entity names).
7. **`dynamic_options_fns`** (optional) — `{source_token: "module:fn"}` for any config field that declares `ui_options_source`. The fn returns `list[str]`.
8. **`dependencies_fn`** (optional) — `(config) -> list[str]`. Each tag (e.g. `"model:foo"`) marks a missing runtime dep so deploy health can flag broken modes.
9. **`check_ready`** (optional) — `() -> (ok, details)` for runtime-only deps not visible to Python imports (venvs, downloaded models, embeddings).

### Pipeline composition

Pipelines are JSON documents with sequential steps — detectors chained into span transformers:

```json
{
  "pipes": [
    {"type": "regex_ner"},
    {"type": "presidio_ner"},
    {"type": "blacklist"},
    {"type": "resolve_spans", "config": {"strategy": "longest_non_overlapping"}}
  ]
}
```

### Frontend architecture

React 19 + TypeScript + Vite 8 + Tailwind CSS v4. Key libraries:
- **@xyflow/react** — drag-and-drop pipeline builder canvas
- **@tanstack/react-query** — all API data fetching (queries + mutations)
- **zustand** — client-side state (pipeline editor store)
- **@rjsf/core** — auto-generated config forms from pipe JSON Schema
- **react-router-dom v7** — SPA routing across 9 Playground views
- **recharts** — eval dashboard charts

The Vite dev server (port 3000) proxies `/api/*` to `localhost:8000` with path rewrite (strips `/api` prefix). Frontend code calls `/api/pipelines`, which hits `localhost:8000/pipelines`.

### CLI profiles, shipped pipelines, and deploy modes

**CLI `--profile`** (in `profiles.py`, for `run` / `batch` / `eval` when you are **not** using `--pipeline`):

- **fast** — regex + whitelist + blacklist + resolve (~10 ms, no ML)
- **balanced** — adds presidio NER (falls back to fast if not installed) — **default** when neither `--pipeline` nor `--config` is set
- **accurate** — adds consistency propagation + confidence-based span resolution

**Shipped saved pipelines** (JSON under `data/pipelines/`, stem = name): `clinical-fast`, `presidio`, `clinical-transformer`, `clinical-transformer-presidio`. Use `--pipeline <name>` or the Playground catalog.

**Deploy mode aliases** (`data/modes.json`) map a short name to a saved pipeline for `POST /process/<mode>`, `/process/scrub`, and Production. Seeded: `fast` → `clinical-fast` (**`default_mode`**), `presidio` → `presidio`, `transformer` → `clinical-transformer`, `transformer_presidio` → `clinical-transformer-presidio`. These names are **not** the same as CLI `--profile` `balanced` / `accurate` (no built-in `balanced` mode in `modes.json`).

## Key directories

```
frontend/                # Vite + React + TypeScript playground UI
  src/components/
    create/              # Visual pipeline builder (linear rail + config panel)
    inference/           # Text input, span highlighting, trace timeline
    evaluate/            # Eval dashboard, metrics, confusion matrix, comparison
    datasets/            # Discover/import JSONL, BRAT→JSONL, compose, transform, generate, export, refresh
    dictionaries/        # Dictionary upload / browse / manage
    deploy/              # Deploy config: inference modes, pipeline allowlist
    audit/               # Audit log viewer with stats, filters
    layout/              # Shell layout
    shared/              # Reusable components (SpanHighlighter, LabelBadge, etc.)

src/clinical_deid/
  domain.py              # Document, EntitySpan, AnnotatedDocument
  pipes/                 # All pipe implementations + registry + combinators
    registry.py          # Central registry, JSON load/dump, pipe catalog
    base.py              # Pipe protocol definitions
    combinators.py       # Pipeline, ResolveSpans, LabelMapper, LabelFilter
    span_merge.py        # Shared span merge / resolution strategies
    trace.py             # Pipeline tracing (PipelineRunResult, PipelineTraceFrame)
    ui_schema.py         # UI schema hints for frontend config forms
    detector_label_mapping.py  # Configurable label mapping for detectors
    regex_ner/           # Regex-based detection
    whitelist/           # Dictionary/phrase matching
    blacklist/           # False-positive filtering
    presidio_ner/        # Presidio wrapper (optional)
    presidio_anonymizer/ # Presidio redaction (optional)
    neuroner_ner/        # NeuroNER LSTM-CRF (Docker HTTP sidecar)
    huggingface_ner/     # Load trained Hugging Face token-classification models from models/huggingface/
    llm_ner.py           # LLM-prompted detection (optional)
    consistency_propagator.py  # Document-level span propagation
    surrogate/           # Realistic fake data replacement (optional)
  api/
    app.py               # FastAPI application
    routers/             # pipelines, process, evaluation, audit, models, dictionaries, datasets, deploy
    schemas.py           # Pydantic request/response models
  eval/
    matching.py          # 4 matching modes (strict, exact boundary, partial, token-level)
    risk.py              # Risk-weighted recall, HIPAA coverage
    runner.py            # Batch evaluation with per-label/per-doc results
  ingest/                # JSONL, BRAT, ASQ-PHI, MIMIC loaders
  cli.py                 # Click CLI: run, batch, eval, audit, dict, dataset, setup, serve
  dataset_store.py       # JSONL-only corpora; discover/list, import JSONL/BRAT, refresh analytics
  mode_config.py         # Deploy config (data/modes.json) load/save
  config.py              # Pydantic settings (env vars, .env file)
  tables.py              # AuditLogRecord (only DB table)
  db.py                  # SQLite engine
  audit.py               # Unified audit: log_run(), list_runs(), get_run()
  pipeline_store.py      # Filesystem pipeline CRUD
  eval_store.py          # Filesystem eval result storage
  profiles.py            # fast/balanced/accurate profile builders
  export.py              # Output formatters (text, JSON, JSONL, CSV, Parquet)
  training_export.py     # Training data export (CoNLL, spaCy DocBin, HuggingFace JSONL)
```

## API routes

All pipeline routes use **name-based** paths (not UUIDs):

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness |
| `GET` | `/pipelines/pipe-types` | Pipe catalog with JSON Schema |
| `POST` | `/pipelines/pipe-types/{name}/labels` | Compute label space for a detector (any `label_source`) |
| `GET` | `/pipelines/pipe-types/{name}/label-space-bundle` | Per-model label bundle for detectors with `label_source: bundle` |
| `GET` | `/pipelines/ner/builtins` | Bundled regex / whitelist label names |
| `POST` | `/pipelines/whitelist/parse-lists` | Parse uploaded list files for whitelist config |
| `POST` | `/pipelines/blacklist/parse-wordlists` | Merge uploads into blacklist terms |
| `POST` | `/pipelines` | Create pipeline |
| `GET` | `/pipelines` | List pipelines |
| `GET` | `/pipelines/{name}` | Get pipeline config |
| `PUT` | `/pipelines/{name}` | Update pipeline config |
| `DELETE` | `/pipelines/{name}` | Delete pipeline |
| `POST` | `/pipelines/{name}/validate` | Validate config |
| `GET` | `/dictionaries` | List uploaded dictionaries |
| `GET` | `/dictionaries/{kind}/{name}` | Dictionary metadata |
| `GET` | `/dictionaries/{kind}/{name}/preview` | Preview first N terms |
| `GET` | `/dictionaries/{kind}/{name}/terms` | Full term list |
| `POST` | `/dictionaries` | Upload a dictionary |
| `DELETE` | `/dictionaries/{kind}/{name}` | Delete a dictionary |
| `POST` | `/process/redact` | Redact/surrogate given text + spans |
| `POST` | `/process/scrub` | Zero-config log cleaning (text in, clean text out) |
| `POST` | `/process/{pipeline_name}?output_mode=` | Run pipeline on text (annotated/redacted/surrogate) |
| `POST` | `/process/{pipeline_name}/batch` | Batch process |
| `POST` | `/eval/run` | Run evaluation (`dataset_path` must be `.jsonl`; BRAT gold → import as JSONL first) |
| `GET` | `/eval/runs` | List eval results |
| `GET` | `/eval/runs/{id}` | Eval result detail |
| `POST` | `/eval/compare` | Compare two runs |
| `GET` | `/datasets` | List datasets (JSONL homes under corpora; lazy `dataset.json`) |
| `POST` | `/datasets` | Import JSONL copy into `corpora/{name}/` (alias: `POST /datasets/import/jsonl`) |
| `POST` | `/datasets/import/brat` | Convert BRAT tree on disk → JSONL dataset home |
| `GET` | `/datasets/import-sources` | JSONL import candidates under corpora root |
| `GET` | `/datasets/import-sources/brat` | BRAT trees available for conversion |
| `POST` | `/datasets/refresh-all` | Recompute analytics for every discovered dataset |
| `POST` | `/datasets/ingest-from-pipeline` | Run a saved pipeline over raw text under `CORPORA_DIR` and register the result |
| `GET` | `/datasets/{name}` | Dataset detail + analytics |
| `PUT` | `/datasets/{name}` | Update description/metadata |
| `DELETE` | `/datasets/{name}` | Delete dataset directory |
| `POST` | `/datasets/{name}/refresh` | Recompute analytics from `corpus.jsonl` |
| `GET` | `/datasets/{name}/preview` | Preview documents (paginated) |
| `GET` | `/datasets/{name}/documents/{doc_id}` | Full document with spans |
| `POST` | `/datasets/compose` | Compose multiple datasets |
| `POST` | `/datasets/transform` | Apply transforms to dataset |
| `POST` | `/datasets/generate` | Generate synthetic data via LLM |
| `POST` | `/datasets/{name}/export` | Export to `conll`/`spacy`/`huggingface`/`jsonl` (annotated) or `brat` under `exports_dir/{name}/` |
| `GET` | `/audit/logs` | Query audit trail |
| `GET` | `/audit/logs/{id}` | Audit detail |
| `GET` | `/audit/stats` | Aggregate stats |
| `GET` | `/deploy` | Get deploy config (modes + allowlist) |
| `PUT` | `/deploy` | Update deploy config |
| `GET` | `/deploy/pipelines` | List deployable pipeline names |
| `GET` | `/models` | List models |
| `GET` | `/models/{framework}/{name}` | Model manifest details |
| `POST` | `/models/refresh` | Re-scan models directory |

## CLI commands

```
clinical-deid run [FILES]           # De-identify text from stdin or files
clinical-deid batch INPUT -o OUT    # Batch process directory or JSONL
clinical-deid eval --corpus FILE.jsonl  # Gold JSONL only; convert BRAT via dataset import-brat first
clinical-deid dict list             # List dictionaries
clinical-deid dict preview KIND NAME  # Preview dictionary terms
clinical-deid dict import FILE --kind KIND --name NAME  # Import dictionary
clinical-deid dict delete KIND NAME # Delete dictionary
clinical-deid dataset list          # List datasets (discovered JSONL homes)
clinical-deid dataset register PATH --name NAME  # Import a JSONL file into corpora
clinical-deid dataset import-brat DIR --name NAME  # BRAT (flat or split) → JSONL under corpora
clinical-deid dataset ingest-run --input PATH --pipeline NAME --output-name OUT  # Run pipeline over raw text → JSONL dataset
clinical-deid dataset refresh NAME  # Recompute stats from corpus.jsonl
clinical-deid dataset refresh-all
clinical-deid dataset show NAME     # Dataset details + analytics
clinical-deid dataset delete NAME   # Delete dataset directory
clinical-deid dataset export NAME -o DIR  # conll/spacy/huggingface/jsonl; --format brat defaults to data/exports/…
clinical-deid audit list            # List audit records
clinical-deid audit show ID         # Show audit detail
clinical-deid setup                 # Verify deps, init DB
clinical-deid serve                 # Start API server
```

Pipeline commands (`run`, `batch`, `eval`) support `--profile` (fast / balanced / accurate), `--pipeline` (saved pipeline name such as `clinical-fast` — **overrides** `--profile`), `--config` (custom JSON file), and `--redactor` (tag/surrogate).

## Evaluation

Four matching modes: strict (exact start+end+label), exact boundary (ignore label), partial overlap (same label, any overlap), token-level (per-character BIO tags).

Also computes: risk-weighted recall (HIPAA severity weights), per-label breakdown, label confusion matrix, HIPAA Safe Harbor coverage report (18 identifiers), worst-document ranking.

## Current status

The full pipe system (11 cataloged types), CLI, FastAPI, Playground UI (9 views), and Production UI (`frontend-production/`) are built and functional. Key capabilities: pipeline composition, multi-mode evaluation with HIPAA coverage, training data export, `clinical-deid train run` for HF fine-tuning (`[train]` extra), NeuroNER HTTP sidecar integration, LLM synthesis, optional API key auth, Docker image, and unified audit trail.

## What's not built yet

- **Rich production file ingest** — drag-and-drop corpus upload to Production UI (batch today is API-driven / copy-paste workflows; extend as needed).

## Conventions

- Python 3.11+, Pydantic v2, FastAPI, SQLModel
- Config via env vars with `CLINICAL_DEID_` prefix or `.env` file
- Optional deps use `try/except ImportError` in `_register_builtins()`
- Tests use `tmp_path` fixtures for isolated filesystem state
- Entry points: `clinical-deid` (CLI), `clinical-deid-api` (HTTP server). Production: see [docs/deployment.md](docs/deployment.md) (single image, scoped keys).

## Testing

The `client` fixture in `conftest.py` sets up isolated temp dirs for pipelines, evaluations, and SQLite. Tests don't touch the real filesystem.
