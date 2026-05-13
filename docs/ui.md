# Frontend Applications

The platform ships two separate React + TypeScript SPAs that both call the same FastAPI backend. They are distinguished by **which API key they present**, which controls which backend routes they can reach.

| App | Directory | Default port | API scope | Who uses it |
|-----|-----------|-------------|-----------|-------------|
| **Playground UI** | `frontend/` | 3000 | admin | Pipeline authors, operators, researchers |
| **Production UI** | `frontend-production/` | 3001 | inference | Reviewers / consumers running batch NER |

Both are Vite + React 19 + TypeScript + Tailwind CSS + TanStack Query.

---

## Playground UI (`frontend/`)

Wraps every authoring workflow. All features call the same Python library code and HTTP endpoints that the CLI uses — no duplicate logic.

### Running

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000 (proxies /api → localhost:8000)
```

Set `VITE_API_KEY` to an **admin** key in `frontend/.env.local` when the backend has auth enabled.

## Views

### Pipelines catalog (`/pipelines`)

Read-only catalog of **saved** pipelines (files under `data/pipelines/`).

- Filterable list by name; detail panel shows **description** (`config.description`), a **composition** table (each step’s `type` and a short config hint), and the **final output label space** (symbolic labels after remaps / `label_mapper` / filters).
- Labels come from cached `output_label_space` in the JSON when the pipeline was last saved via the API, or use **Compute / refresh** to call `POST /pipelines/{name}/validate` and display the result without saving.
- Header includes the server **label space** name from `GET /health` (`label_space_name`) — the pack used for `POST /process` span-label normalization (distinct from per-pipeline output labels).

**API endpoints used:** `GET /pipelines`, `POST /pipelines/{name}/validate`, `GET /health`.

### Pipeline Builder (`/create`)

Visual editor for composing and versioning de-identification pipelines.

- Browse the pipe catalog with install status, descriptions, and role tags (detector, span transformer, redactor).
- Drag pipes into a sequential layout with a merge strategy selector for span resolution.
- Each pipe renders a dynamic config form generated from its JSON Schema + `ui_*` hints — no per-pipe frontend code needed.
- Upload term files for whitelist/blacklist pipes inline.
- Validate the config before saving.
- Save as a named pipeline with description.

**API endpoints used:** `GET /pipelines/pipe-types`, `POST /pipelines`, `PUT /pipelines/{name}`, `POST /pipelines/{name}/validate`, `POST /pipelines/whitelist/parse-lists`, `POST /pipelines/blacklist/parse-wordlists`.

### Inference (`/inference`)

Paste-and-try interface for running pipelines on ad-hoc text.

- Pick a saved pipeline from a dropdown.
- Paste or type clinical text into an input area.
- Submit and see results: original text with detected spans highlighted and colour-coded by label, redacted text, and a span table with start, end, label, confidence, and source.
- Toggle intermediary trace view to inspect the document state after each pipeline step.
- Processing time displayed for latency awareness.

**API endpoints used:** `GET /pipelines`, `POST /process/{pipeline_name}`.

### Evaluate (`/evaluate`)

Dashboard for measuring pipeline quality against gold-standard annotated data.

- Select a pipeline and a gold corpus (registered dataset name, or a **`.jsonl` path** on the API host for ad-hoc files).
- Optional **document splits** filter (comma-separated, matches `metadata.split`).
- **Eval mode** toggle — run on the full (split-filtered) corpus or a **random sample** of *N* documents, with a fixed seed (reproducible) or a fresh seed per run (returned as `sample_seed_used`).
- When sampling, an optional **Save sample as dataset** checkbox materializes the sampled docs as a new registered JSONL dataset (provenance captured in its `dataset.json`).
- **Per-document inspection** toggles return (but do not persist) per-doc scores — optionally with gold/pred spans — so the dashboard can show a sortable worst-docs table and a gold-vs-pred highlight view. Persisted eval JSON stays free of raw document text; re-load from history re-runs without per-doc data.
- **Run history** — every completed `POST /eval/run` (including from this view) is saved to **`data/evaluations/{pipeline}_{timestamp}.json`**. The run picker lists these files (newest first) so you can **re-open** past evals. **`pypedeid eval` writes the same kind of file**, so CLI runs appear in the list too.
- Run evaluation and view: precision, recall, F1 across all matching modes (strict, partial, token-level, exact boundary).
- Per-label breakdown table with sortable columns.
- Confusion matrix showing label misclassification patterns.
- Compare two evaluation runs with delta columns.
- Risk-weighted recall and HIPAA coverage report.
- Worst-performing documents list.

**API endpoints used:** `POST /eval/run`, `GET /eval/runs`, `GET /eval/runs/{id}`, `POST /eval/compare`.

### Datasets (`/datasets`)

Full dataset lifecycle management. Canonical storage under `data/corpora/` is **JSONL only** (`corpus.jsonl` + optional `dataset.json` for cached stats).

- **Import JSONL** — copy a `.jsonl` file into a new dataset home under the corpora root.
- **Convert BRAT → JSONL** — load a BRAT tree (flat or split) and write only `corpus.jsonl` + manifest (exports for external tools go to `data/exports/`).
- **Browse** discovered datasets with document count, span count, and label distribution; **refresh** stats from disk per row or all at once.
- **Preview** documents with text snippets and span summaries.
- **Compose** multiple datasets (merge, interleave, proportional sampling).
- **Transform** datasets (drop/keep labels, label mapping, resize, boost rare labels, re-split).
- **Generate** synthetic clinical notes via LLM.
- **Analytics** — label distribution, span statistics, cached and refreshable.

**API endpoints used:** `GET/POST /datasets`, `POST /datasets/import/brat`, `POST /datasets/refresh-all`, `GET /datasets/{name}`, `POST /datasets/{name}/refresh`, `POST /datasets/compose`, `POST /datasets/transform`, `POST /datasets/generate`, `GET /datasets/{name}/preview`, `POST /datasets/{name}/export`.

### Dictionaries (`/dictionaries`)

Upload and manage whitelist and blacklist term lists.

- List all dictionaries filtered by kind and label.
- Upload new term files (txt, csv, json).
- Preview terms and metadata.
- Delete dictionaries.

Dictionaries are referenced by name in whitelist/blacklist pipe configs.

**API endpoints used:** `GET /dictionaries`, `POST /dictionaries`, `DELETE /dictionaries/{kind}/{name}`.

### Deploy (`/deploy`)

Configure inference-scoped access to `/process/*`.

- **Inference modes** — map short **mode** keys to a saved pipeline `name` (seeded: `fast` → `clinical-fast`, `presidio` → `presidio`, `transformer` → `clinical-transformer`, `transformer_presidio` → `clinical-transformer-presidio`). Clients call `POST /process/<mode>` and the API resolves the alias. This is **not** the same as CLI `--profile` `balanced` / `accurate` (those are in-memory only unless you add matching entries to `modes.json`).
- **Default mode** — used by `/process/scrub` when no mode is specified.
- **Pipeline allowlist** — when enabled, inference-scoped callers may only invoke checked pipelines; admin-scoped callers bypass the allowlist.

Configuration is stored in `data/modes.json` (override via `PYPEDEID_MODES_PATH`).

**API endpoints used:** `GET /deploy`, `PUT /deploy`, `GET /deploy/pipelines`.

### Audit (`/audit`)

Browse and monitor the audit trail.

- **Stats dashboard** — total requests, average duration, total spans detected, source breakdown.
- **Top pipelines** bar chart.
- **Log table** — paginated, filterable by pipeline name and source (`api-admin`, `api-inference`, `cli`).
- **Detail panel** — click a row to see full metadata: pipeline config, metrics, timing, dataset source.

**API endpoints used:** `GET /audit/logs`, `GET /audit/logs/{id}`, `GET /audit/stats`.

---

## Production UI (`frontend-production/`)

A purpose-built SPA for reviewers and consumers who need to run batch NER over a corpus, inspect and resolve detections, and export results. It uses an **inference-scoped API key** — it cannot create pipelines, modify dictionaries, or touch evaluation runs.

### Running

```bash
cd frontend-production
npm install
npm run dev          # http://localhost:3001
```

Set `VITE_API_KEY` to an **inference** key in `frontend-production/.env.local` when the backend has auth enabled. Also set `VITE_API_BASE_URL` if the API is not on `localhost:8000`.

### What the Production UI can do (inference scope)

| Route | Description |
|-------|-------------|
| `POST /process/*` | Run any allowed pipeline (subject to deploy allowlist in `data/modes.json`) |
| `GET /deploy/health` | Fetch available modes + per-mode availability for the mode selector |
| `GET /audit/logs`, `GET /audit/logs/{id}`, `GET /audit/stats` | Read-only audit trail |

Everything else (pipeline CRUD, datasets, eval, dictionaries, deploy config writes) requires an admin key and is only accessible through the Playground UI.

### Key affordances

- **Virtualized file list** — when a dataset's file list exceeds 200 items, the left-hand queue uses `@tanstack/react-virtual` for smooth scrolling; below that threshold a simple list renders.
- **Keyboard shortcuts** (fire only when workbench has focus and no input is active):
  - `↑` / `↓` — previous / next file
  - `J` / `K` — next / previous **unresolved** file
  - `N` — next file whose detection errored
  - `R` — toggle resolved on the current file
  - `?` — open the cheat-sheet modal
- **Surrogate preview** — in `Preview: surrogate` mode the reviewer pane shows what the surrogate text will look like before export. When the dataset's export type is `surrogate_annotated`, detection requests the API with `include_surrogate_spans=true`; the response's aligned spans are cached per file and emitted verbatim by the export bar.

---

## Tech stack

- **React 19** with TypeScript
- **Vite** for build and dev server
- **Tailwind CSS** for styling
- **TanStack Query** (React Query) for data fetching and cache management
- **Lucide React** for icons
- **clsx** for conditional class names

## Frontend structure

```
frontend/src/
  api/              # API client functions (typed fetch wrappers)
    client.ts       # Base fetch with error handling
    pipelines.ts    # Pipeline CRUD
    datasets.ts     # Dataset CRUD + compose/transform/generate
    audit.ts        # Audit log queries
    deploy.ts       # Deploy config
    types.ts        # Shared TypeScript types
  components/
    create/         # Pipeline builder (linear rail, pipe cards, config panel)
    inference/      # Text input, span highlighting, trace viewer
    evaluate/       # Eval dashboard, metrics tables, confusion matrix
    datasets/       # Register, list, detail, compose, transform, generate forms
    dictionaries/   # Upload, browse, manage term lists
    deploy/         # Mode editor, allowlist
    audit/          # Log table, stats cards, detail panel
    layout/         # Shell (sidebar nav, content area)
    shared/         # Reusable components (SpanHighlighter, LabelBadge, etc.)
  hooks/            # TanStack Query hooks (useDatasets, useAudit, useDeploy, etc.)
  App.tsx           # Routes
```
