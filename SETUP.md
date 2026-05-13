# Setup Guide

Step-by-step installation for the NER pipeline platform (backend + frontend).

## Requirements

| Dependency | Minimum version |
|-----------|----------------|
| Python | 3.11+ |
| Node.js | 20.19+ or 22.12+ |
| npm | 9+ |

## Backend

### 1. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate          # Linux / macOS
.venv\Scripts\activate             # Windows (cmd/PowerShell)
```

### 2. Install the package

```bash
pip install -e .
python -m spacy download en_core_web_sm
```

The base install includes everything needed for `regex_ner`, `whitelist`, `blacklist`, `presidio_ner` (all model families: spaCy / HuggingFace / stanza / flair), `huggingface_ner` (inference), and `llm_ner`. The spaCy model download is required for any Presidio-backed pipe (including HuggingFace ones — Presidio uses spaCy as its NLP engine even when the NER head is HF).

For tests + lint tooling, add `[dev]`:

```bash
pip install -e ".[dev]"
```

### 3. Initialize the database and verify dependencies

```bash
pypedeid setup
```

This creates `data/app.sqlite` (audit log), verifies optional dependencies, and downloads the default spaCy model if needed.

### 4. Start the API server

```bash
pypedeid serve              # http://localhost:8000
# or equivalently:
pypedeid-api
uvicorn pypedeid.api.app:app --reload
```

The API is unauthenticated by default (local dev). See [docs/configuration.md](docs/configuration.md#authentication) to enable API keys.

---

## Frontends

The platform ships two separate SPAs that share the same backend.

| App | Directory | Port | API key needed |
|-----|-----------|------|---------------|
| **Playground UI** (admin/operator) | `frontend/` | 3000 | admin key |
| **Production UI** (inference consumer) | `frontend-production/` | 3001 | inference key |

Both apps consume code from `frontend-shared/` via the `@shared/*` path alias; install its (tiny) type-only dependencies once before building:

```bash
cd frontend-shared && npm install && cd ..
```

### Playground UI

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```

The dev server proxies `/api/*` to `localhost:8000`. Open `http://localhost:3000`. This is the authoring, evaluation, and deploy-configuration surface — use it with an admin API key (or no key in local dev with auth disabled).

### Production UI

```bash
cd frontend-production
npm install
npm run dev        # http://localhost:3001
```

The inference-scoped consumer UI. Can run pipelines and review audit logs; cannot create pipelines or modify configuration. Use with an inference API key.

### Environment variables (optional)

Create `.env.local` in whichever frontend directory you're running if the API is not at `localhost:8000` or if auth is enabled:

```
VITE_API_BASE_URL=http://my-server:8000
VITE_API_KEY=your-key-here
```

---

## Demo Assets (what ships in git)

**Pipelines and modes** — the repo **tracks** these JSON files under `data/pipelines/`: `clinical-fast`, `presidio`, `clinical-transformer`, `clinical-transformer-presidio`, `clinical-llm`, `clinical-llm-presidio`, and `clinical-ensemble` (name = file stem). `data/modes.json` seeds seven inference **modes** that point at those pipelines (`default_mode` is `fast` → `clinical-fast`).

**Gold corpora — `data/corpora/sample_notes/` and `data/corpora/sample_notes_surrogated/`** — 15 clinical-text notes with span annotations each, produced in the **Production UI (consumer)**: review/export to JSONL, then registered as a dataset. `sample_notes` carries the original PHI; `sample_notes_surrogated` is the same notes with synthesized surrogates (Faker-backed) replacing every span. Both are the default teaching / regression corpora referenced from the main [README](README.md#evaluation).

The base install covers Presidio + HuggingFace inference. The shipped transformer pipelines (`clinical-transformer`, `clinical-transformer-presidio`, `clinical-ensemble`) load **`openai-privacy-filter`** as the main HF detector; `mimic-clinicalbert-sentence` is also bundled as an alternative clinical-tuned checkpoint. Neither model is in git — download both as a single archive:

> **Google Drive:** <REPLACE_WITH_GDRIVE_LINK>

### Download and extract

```bash
# Install gdown once (handles Google Drive's download flow)
pip install gdown

# Download the archive (replace FILE_ID with the actual ID from the link above)
gdown "FILE_ID" -O huggingface-models.zip

# Extract at the repo root — files go directly under models/huggingface/
unzip huggingface-models.zip -d models/huggingface/
```

After extraction the layout will be:

```
models/huggingface/openai-privacy-filter/         ← OpenAI Privacy Filter (default HF model)
models/huggingface/mimic-clinicalbert-sentence/   ← Bio_ClinicalBERT fine-tuned on synthetic MIMIC notes
```

Each directory ships with a `model_manifest.json` so the backend discovers both automatically on startup — no registration or config change needed. They appear in the `huggingface_ner` pipe's model dropdown.

### About the bundled models

**`openai-privacy-filter`** — OpenAI's bidirectional token classifier (1.5B params, 50M active) over an 8-category privacy taxonomy: `private_person`, `private_email`, `private_phone`, `private_address`, `private_date`, `private_url`, `account_number`, `secret`. 128k-token context window allows full-document inference in one pass. Apache 2.0. The shipped pipelines map its raw labels onto the project's canonical PHI label space via `entity_map`.

**`mimic-clinicalbert-sentence`** — Bio_ClinicalBERT fine-tuned on MIMIC-based synthetic de-id notes. Emits canonical PHI labels (`NAME`, `DATE`, `AGE`, `ID`, `LOCATION`, `ORGANIZATION`, `PHONE`, `HOSPITAL`) directly — no entity_map needed. Trained at sentence granularity; use with `segmentation: auto` so inference matches training context. Smaller and faster than the OpenAI model; useful for clinical-domain comparison or as a swap-in alternative.

---

## Optional Extras

The base install includes Presidio, HuggingFace inference, and LLM clients. The remaining extras are opt-in for specific workflows.

| Extra | What it adds | When you need it |
|-------|--------------|------------------|
| `.[dev]` | `pytest`, `pytest-cov`, `ruff`, `pandas`, `faker` | Running tests + lint locally |
| `.[scripts]` | `pandas`, `faker` | Analytics and dataset-transform scripts; surrogate output mode |
| `.[train]` | `datasets`, `seqeval`, `accelerate` | HuggingFace fine-tuning (`pypedeid train run`) |
| `.[parquet]` | `pyarrow` | Parquet export format |
| `.[all]` | `dev` + `train` + `parquet` | Full toolchain |

Back-compat stubs `[presidio]`, `[ner]`, `[llm]` still resolve (they're no-ops now — their dependencies moved into the base install), so older install commands keep working.

```bash
pip install -e ".[all]"        # full toolchain incl. tests, training, parquet
pip install -e ".[train]"      # base install + fine-tuning extras
```

**spaCy language data is still required** for Presidio-backed pipes — `python -m spacy download en_core_web_sm` covers the default; install matching wheels for `en_core_web_md` / `lg` / `trf` if you switch the `presidio_ner` model. HuggingFace Presidio models (Stanford / OBI / etc.) still pair with `en_core_web_sm` as the spaCy engine.

---

## Docker (optional)

```bash
docker compose up
```

See [docs/docker-quickstart.md](docs/docker-quickstart.md) and [docs/deployment.md](docs/deployment.md) for full container setup, including mounting `./data` and `./models` volumes.

---

## Configuration

All settings are controlled via environment variables with the `PYPEDEID_` prefix (or a `.env` file at the repo root):

| Variable | Default | Description |
|----------|---------|-------------|
| `PYPEDEID_LABEL_SPACE_NAME` | `clinical_phi` | Active label space pack |
| `PYPEDEID_RISK_PROFILE_NAME` | `clinical_phi` | Active risk profile |
| `PYPEDEID_DATABASE_URL` | `sqlite:///./data/app.sqlite` | Audit DB connection |
| `PYPEDEID_PIPELINES_DIR` | `data/pipelines` | Pipeline JSON storage |
| `PYPEDEID_CORPORA_DIR` | `data/corpora` | Dataset storage |
| `PYPEDEID_MODELS_DIR` | `models` | Model artifact storage |
| `PYPEDEID_MAX_BODY_BYTES` | `10485760` (10 MB) | Max API request body size |

Full reference: [docs/configuration.md](docs/configuration.md).
