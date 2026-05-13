# PypeDeid

## What It Does

A **local-first NER pipeline platform**: compose modular detectors (regex, Presidio, HuggingFace, LLM) into named pipelines, evaluate against gold corpora with multi-mode metrics, generate and manage training datasets, and serve auditable inference via HTTP API.

Ships with a **clinical de-identification pack** (HIPAA Safe Harbor label space, regex patterns, surrogate strategies, risk/coverage profile) as the default configuration — so it works out of the box for PHI detection. The clinical domain is a *pack*, not a baked-in assumption. Swap the label space, pattern pack, surrogate pack, and risk profile to target any NER task. A minimal `generic_pii` pack ships alongside; custom packs register at startup.

**Key capabilities:**

- **Playground UI** ([`frontend/`](./frontend/)) — admin-oriented web app: **visual pipeline builder**, **single-document** inference with span editing and trace, **evaluation** (metrics, confusion matrix, run comparison), **dataset** registry and transforms, **dictionaries**, **Deploy** (modes / allowlist), and **audit** viewer. Dev server: `http://localhost:3000` (see [Web UIs](#web-uis-playground-vs-production-app) below and [docs/ui.md](docs/ui.md)).
- **Production UI** ([`frontend-production/`](./frontend-production/)) — inference-scoped app for **batch** work over a corpus: local dataset library, per-file review, redacted/surrogate **export**; uses deploy **modes** from `data/modes.json`. Dev server: `http://localhost:3001`. Same API as the Playground, narrower key. Details: [Web UIs](#web-uis-playground-vs-production-app), [docs/ui.md](docs/ui.md).
- 11 pipe types: `regex_ner`, `whitelist`, `blacklist`, `presidio_ner`, `huggingface_ner`, `neuroner_ner`, `llm_ner`, `label_mapper`, `label_filter`, `resolve_spans`, `consistency_propagator`
- **Shipped example pipelines** (under `data/pipelines/`, name = filename stem): `clinical-fast`, `presidio`, `clinical-transformer`, `clinical-transformer-presidio`, `clinical-llm`, `clinical-llm-presidio`, `clinical-ensemble` — plus seed **inference modes** in `data/modes.json` (`fast` → `clinical-fast` by default)
- Evaluation: 4 matching modes (strict, partial, token-level, boundary), macro + micro averages, per-label breakdown, risk-weighted recall, HIPAA Safe Harbor coverage report, confusion matrix
- **Tracked teaching corpora** under `data/corpora/`: `sample_notes` (15 annotated production-export notes) and `sample_notes_surrogated` (same notes with synthesized PHI surrogates)
- Dataset tools: JSONL/BRAT import, compose, transform, LLM synthesis, export to CoNLL/spaCy/HuggingFace/BRAT
- **CLI and HTTP API** — same features as the UIs for scripting and automation (see [CLI](#cli) and [docs/api.md](docs/api.md))
- HuggingFace fine-tuning pipeline (`pypedeid train run`)
- Full audit trail (SQLite) on every inference call

## Quick Start

```bash
# Backend
python -m venv .venv && source .venv/bin/activate
pip install -e .                            # all NER pipes (presidio, HF, LLM) included
python -m spacy download en_core_web_sm     # required for Presidio pipes
pypedeid setup          # verify deps, init DB
pypedeid serve           # API on http://localhost:8000

# Frontends (separate terminals; need Node 20.19+ or 22.12+)
cd frontend && npm install && npm run dev                 # Playground — http://localhost:3000
# optional: cd frontend-production && npm install && npm run dev   # batch reviewer — http://localhost:3001
```

Open the **Playground** at `http://localhost:3000` → **Create** to compose a pipeline, **Inference** to test it, or **Evaluate** / **Datasets** as needed. The **Production** app (port 3001) is for inference-key batch review. See [Web UIs](#web-uis-playground-vs-production-app) and [SETUP.md](SETUP.md) for install options and optional extras.

## Video Links
Demo+Technical Walkthrough
https://youtu.be/iKYWic1IqJQ

## Evaluation

### CLI profiles vs saved pipelines vs deploy modes

Three concepts overlap in name but are stored differently:

1. **CLI `--profile`** (`src/pypedeid/profiles.py`) — in-memory configs **`fast`**, **`balanced`**, **`accurate`** (regex-only → +Presidio → +consistency/resolve). Default for `pypedeid run|batch|eval` is **`balanced`** when you don’t pass `--pipeline` or `--config`.
2. **Saved pipeline JSON** (`data/pipelines/<name>.json`) — the repo ships **`clinical-fast`**, **`presidio`**, **`clinical-transformer`**, **`clinical-transformer-presidio`**, **`clinical-llm`**, **`clinical-llm-presidio`**, and **`clinical-ensemble`** (name = file stem). Use **`--pipeline <name>`** or pick them in the Playground.
3. **Deploy mode aliases** (`data/modes.json`) — map a short **mode** string to a saved pipeline for **`POST /process/<mode>`** and the Production UIs. Seeded defaults:

| Mode alias | Resolves to pipeline | Notes |
|------------|----------------------|--------|
| `fast` | `clinical-fast` | Also **`default_mode`** for `/process/scrub` |
| `presidio` | `presidio` | Presidio + regex stack |
| `transformer` | `clinical-transformer` | Needs HF weights under `models/huggingface/` |
| `transformer_presidio` | `clinical-transformer-presidio` | HF + Presidio + spaCy deps |
| `llm` | `clinical-llm` | Regex/whitelist/blacklist + LLM (gpt-4o-mini); needs `OPENAI_API_KEY` |
| `llm_presidio` | `clinical-llm-presidio` | Adds Presidio (spaCy small) under the LLM stack; CPU-only |
| `ensemble` | `clinical-ensemble` | Regex + Presidio + HF + LLM, longest-non-overlapping resolve. Highest recall, slow + expensive. |

**CLI profile** quick reference (when using `--profile`, not `--pipeline`):

| Profile | Pipes | Latency (rough) |
|---------|-------|-----------------|
| **fast** | regex_ner + whitelist + blacklist + resolve_spans | ~10 ms |
| **balanced** | + presidio_ner (falls back to fast if Presidio missing) | ~200 ms |
| **accurate** | + consistency_propagator + confidence-based resolution | ~300 ms |

Four evaluation modes supported: **strict** (exact span + label), **exact boundary** (ignore label), **partial overlap** (any span overlap, same label), **token-level** (per-character BIO). Metrics computed: precision, recall, F1, risk-weighted recall (HIPAA severity weights), per-label breakdown, label confusion matrix, HIPAA Safe Harbor identifier coverage (18 identifiers), worst-document ranking.

```bash
# Evaluate a saved pipeline against a gold JSONL corpus
pypedeid eval --corpus data/corpora/sample_notes/corpus.jsonl --pipeline clinical-fast

# Or use a CLI profile (default profile is balanced)
pypedeid eval --corpus data/corpora/sample_notes/corpus.jsonl --profile fast
```

**Tracked teaching corpora** (under `data/corpora/`):

- **`sample_notes`** — 15 production-export clinical notes with span gold labels in `corpus.jsonl` (plus cached stats in `dataset.json`). 331 spans across the canonical 8-label space. Use this for evaluation.
- **`sample_notes_surrogated`** — same 15 notes with every PHI span replaced by Faker-backed surrogates. Useful for inspecting the surrogate output mode and as a non-PHI demo corpus.

Both ship in git so Evaluate and the CLI work out of the box.

**Where eval results are stored:** Every run from **Playground → Evaluate** or **`POST /eval/run`**, and every **`pypedeid eval`**, writes a JSON file under **`data/evaluations/`** (default; override with `PYPEDEID_EVALUATIONS_DIR`). Files are named **`{pipeline_name}_{YYYYMMDD_HHMMSS}.json`** (UTC). The **Evaluate** view lists and opens past runs from that folder via `GET /eval/runs` — so CLI and UI runs share the same history.

> The same eval can be run from **Playground → Evaluate** or the CLI; HTTP details are in [docs/api.md](docs/api.md).

**HuggingFace model weights (required for transformer/ensemble pipelines):** The shipped `clinical-transformer*` and `clinical-ensemble` pipelines rely on **`openai-privacy-filter`** (default) and **`mimic-clinicalbert-sentence`** under `models/huggingface/`. Neither is in git — download both as a single archive from Google Drive following [SETUP.md](SETUP.md#demo-assets-what-ships-in-git). The `clinical-fast`, `presidio`, and `clinical-llm*` pipelines do not need them.

---

**End-to-end flow:** train or import data → save models under [`models/`](./models/README.md) → compose pipelines in `data/pipelines/` (Playground, CLI, or API) → run inference and evaluation → optional SQLite **audit** on every process call. Pack selection (label space, risk profile, etc.) is env-driven; see [docs/configuration.md](docs/configuration.md) (`PYPEDEID_LABEL_SPACE_NAME`, …).

**Developer note:** new pipes are a Pydantic config + `forward` + `register()`. **Documentation index:** [docs/README.md](docs/README.md), [docs/ui.md](docs/ui.md) (both web apps), [PROJECT_OVERVIEW.md](./PROJECT_OVERVIEW.md), [docs/deployment.md](docs/deployment.md), [docs/api.md](docs/api.md).

### Repository layout

All mutable runtime state lives under `data/`; model weights live under `models/`. A deployment mounts those two directories — see [docs/deployment.md](docs/deployment.md) and [data/README.md](./data/README.md).

| Path | Purpose |
|------|---------|
| `frontend/` | Playground UI (Vite + React + TypeScript) |
| `frontend-production/` | Production UI (inference-scoped batch reviewer) |
| `data/pipelines/` | Named pipeline configs (JSON files, git-versioned) |
| `data/modes.json` | Deploy configuration (inference modes, pipeline allowlist) |
| `data/evaluations/` | Eval result JSON files |
| `data/inference_runs/` | Saved batch inference snapshots |
| `data/corpora/<name>/` | Registered datasets (`dataset.json` + imported corpus files) |
| `data/dictionaries/` | Whitelist & blacklist term-list files |
| [`data/raw/`](./data/raw) | Optional local inbox for source files |
| `data/app.sqlite` | SQLite database (audit log only) |
| `models/` | Trained model artifacts (see [`models/README.md`](./models/README.md)) |

## Security notice

**Optional API keys** (`PYPEDEID_ADMIN_API_KEYS` / `PYPEDEID_INFERENCE_API_KEYS`): when both lists are empty, the API is open (typical local dev). For any shared or production host, set keys, TLS at the reverse proxy, and rate limits. See [docs/configuration.md](docs/configuration.md#authentication) and [docs/deployment.md](docs/deployment.md).

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .                            # core + presidio + HF + LLM
python -m spacy download en_core_web_sm     # required for Presidio
pypedeid setup          # verify deps, init DB
```

The base install covers all inference pipes. Opt-in extras: `[dev]` (tests + lint), `[train]` (HuggingFace fine-tuning), `[parquet]` (Parquet export), `[scripts]` (analytics + surrogate output), `[all]` (everything). The legacy `[presidio]`, `[ner]`, `[llm]` extras still resolve as no-ops for back-compat.

**spaCy language data is not pulled automatically.** `en_core_web_sm` is the default for `presidio_ner` (including HuggingFace Presidio models, which still pair with spaCy as the NLP engine). For larger models add `python -m spacy download en_core_web_md` / `lg` / `trf` and switch the `presidio_ner` `model` field.

`pip` is the canonical install path; `uv.lock` is committed for reproducible builds when using `uv sync` / `uv pip install -e .`, but is not required.

## Web UIs: Playground vs Production app

The repo ships **two** React (Vite + TypeScript) apps over the same HTTP API. They differ by **API key scope**: the **Playground** uses an **admin** key (full configuration); the **Production** app uses an **inference** key (process + read-only support surfaces). *Naming note:* the Playground has a **“Production”** page for deploy-mode batch review; the separate **Production UI** app is the inference-scoped batch reviewer below.

```bash
cd frontend && npm install && npm run dev              # Playground — http://localhost:3000
cd frontend-production && npm install && npm run dev   # Production UI — http://localhost:3001
```

Set `VITE_API_BASE_URL` and `VITE_API_KEY` in each app’s `frontend` / `frontend-production` `.env.local` as needed. Dev servers proxy `/api` to `localhost:8000` by default. Large dataset uploads need a high enough `PYPEDEID_MAX_BODY_BYTES` on the API (otherwise **413**).

### Playground — `frontend/` (admin)

For authors, evaluators, and operators who manage pipelines, corpora, and deploy config.

| View | Route | What you can do there |
|------|--------|------------------------|
| **Create** | `/create` | **Visual pipeline builder** (XYFlow canvas), per-pipe settings from **JSON Schema** forms, save pipelines to the server. |
| **Pipelines** | `/pipelines` | **List and inspect** saved pipelines: description, ordered pipe list, **output label space**, compute/refresh server-side labels, raw JSON, **rename** and **delete**. |
| **Inference** | `/inference` | **Single-document** run: pick a **saved pipeline**, **output mode** (annotated / redacted / surrogate), run on typed or uploaded text, **highlight** spans, optional per-pipe **trace** timeline, **hand-edit** spans and resolve overlap conflicts, **save/load** inference snapshots, **export** results. |
| **Production** | `/production` | **Deploy-mode** assisted workflow: choose an inference **mode** (maps to a pipeline via `modes.json`), set **reviewer** id, queue **documents**, **batch** run pending items, per-doc **review** and **export**; uses **deploy health** for mode availability. |
| **Evaluate** | `/evaluate` | Pick pipeline + **registered dataset**, start an eval run, view **strict** (and related) **metrics**, per-label table, **confusion matrix**, optional **redaction** / risk views, **compare** two runs. |
| **Datasets** | `/datasets` | **Register** server-side paths, **preview** documents, **compose** / **transform** / **LLM generate**, training **export**; **upload** JSONL when configured. |
| **Dictionaries** | `/dictionaries` | Upload and manage **whitelist** and **blacklist** term lists used by pipes. |
| **Deploy** | `/deploy` | Edit **inference modes** and **pipeline allowlist** (who `POST /process/{mode}` may hit when scoped). |
| **Audit** | `/audit` | Search and open **local** audit log records; optional **production** log proxy for operators. |

### Production UI — `frontend-production/` (inference)

For day-to-day reviewers and batch consumers **without** admin credentials. Datasets in this app are **browser-local** (IndexedDB) unless you add server features separately.

| Area | Route | What you can do there |
|------|--------|------------------------|
| **Library** | `/library` | Create, rename, duplicate, and delete **local** datasets; open the workspace or **export** flow; filter by completion. |
| **Workspace** | `/datasets/:id/files` | **File list** for the active dataset, **document reviewer** (highlights, edits), **batch detection** using a **deploy mode**, keyboard shortcuts, run progress. |
| **Export** | `/datasets/:id/export` | Download results (**redacted**, **annotated**, or **surrogate + annotated**). |
| **Audit** | `/audit` | Read-only audit trail (as allowed for the inference key). |

**Not available** with a typical inference key: create/edit **named pipelines** on the server, **register** server **datasets**, change **deploy** or **dictionaries** — use the Playground (admin) for those.

## CLI

The CLI exposes the same backend as the UIs: pipelines, process, eval, datasets, dictionaries, and audit. Full route reference: [docs/api.md](docs/api.md).

```bash
# De-identify text
echo "Patient John Smith DOB 01/15/1980" | pypedeid run
pypedeid run --profile fast notes.txt
pypedeid run --pipeline clinical-fast notes.txt
pypedeid run --redactor surrogate notes.txt

# Batch process
pypedeid batch notes_dir/ -o output/ --format jsonl
pypedeid batch corpus.jsonl -o output/ --pipeline clinical-fast

# Evaluate against gold standard
pypedeid eval --corpus data.jsonl --profile balanced
pypedeid eval --corpus data.jsonl --pipeline clinical-fast

# Dictionary management
pypedeid dict list
pypedeid dict preview whitelist hospitals --label HOSPITAL
pypedeid dict import terms.txt --kind whitelist --name hospitals --label HOSPITAL
pypedeid dict delete whitelist hospitals

# Dataset management
pypedeid dataset list
pypedeid dataset register data/corpus.jsonl --name i2b2-2014
pypedeid dataset import-brat data/brat/ --name physionet
pypedeid dataset show i2b2-2014
pypedeid dataset delete i2b2-2014

# Audit trail
pypedeid audit list
pypedeid audit show <record-id>

# Server
pypedeid serve --port 8000 --reload
```

Pipeline commands (`run`, `batch`, `eval`) support `--profile` (fast / balanced / accurate), `--pipeline` (saved pipeline JSON name such as `clinical-fast`), `--config` (custom JSON file), and `--redactor` (tag/surrogate). **`--pipeline` wins** over `--profile` when both are set.

## Run the API

```bash
pypedeid serve
# or: pypedeid-api
# or: uvicorn pypedeid.api.app:app --reload
```

Default SQLite database: `./data/app.sqlite` (audit log only). Override with `PYPEDEID_DATABASE_URL`.

### HTTP API

**Full reference:** [docs/api.md](docs/api.md) (all routes, request bodies, and auth). **Interactive OpenAPI** (`/docs`, `/openapi.json`) is available when API keys are disabled. The API covers: health, pipeline CRUD and validation, per-pipe config helpers, `POST /process/{pipeline|mode}` and batch, eval runs and comparison, dataset registry and transforms, dictionaries, deploy config, audit, and model registry.

## Example pipeline config

Pipelines are JSON documents — sequential steps with detectors feeding into span transformers:

```json
{
  "pipes": [
    {"type": "regex_ner"},
    {"type": "whitelist"},
    {"type": "presidio_ner"},
    {"type": "blacklist"},
    {"type": "resolve_spans", "config": {"strategy": "longest_non_overlapping"}}
  ]
}
```

Save as `data/pipelines/my-pipeline.json` or create from **Playground → Create**.

## Example JSONL line (training / evaluation)

```json
{
  "document": {"id": "note-001", "text": "Patient John Smith DOB 01/15/1980"},
  "spans": [
    {"start": 8, "end": 18, "label": "PATIENT"},
    {"start": 23, "end": 33, "label": "DATE"}
  ]
}
```

