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
clinical-deid setup
```

This creates `data/app.sqlite` (audit log), verifies optional dependencies, and downloads the default spaCy model if needed.

### 4. Start the API server

```bash
clinical-deid serve              # http://localhost:8000
# or equivalently:
clinical-deid-api
uvicorn clinical_deid.api.app:app --reload
```

The API is unauthenticated by default (local dev). See [docs/configuration.md](docs/configuration.md#authentication) to enable API keys.

---

## Frontends

The platform ships two separate SPAs that share the same backend.

| App | Directory | Port | API key needed |
|-----|-----------|------|---------------|
| **Playground UI** (admin/operator) | `frontend/` | 3000 | admin key |
| **Production UI** (inference consumer) | `frontend-production/` | 3001 | inference key |

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

The base install already covers Presidio + HuggingFace inference. For the transformer pipelines you also need a HuggingFace checkpoint under `models/huggingface/mimic-clinicalbert-sentence`.

**Optional large download (not in git)** — A separate **mimic-10k** gold archive (models + 10k-note corpus) can still be used for large-scale work. `clinical-transformer` was developed against that style of data; the sample notes above are small and hand-curated for docs and quick CI-style checks. Extract from the following when you have the file:

> **Google Drive:** <https://drive.google.com/file/d/1eGIWtsfSvdfTJ-iCAj7V4WapZZt00pwk/view?usp=sharing>

### Download and extract

```bash
# Install gdown once (handles Google Drive's download flow)
pip install gdown

# Download the archive
gdown "1eGIWtsfSvdfTJ-iCAj7V4WapZZt00pwk" -O demo-assets.zip

# Extract at the repo root — files go directly into models/ and data/corpora/
unzip demo-assets.zip
```

After extraction the layout will be:

```
models/huggingface/mimic-clinicalbert-sentence/   ← HuggingFace model weights
data/corpora/mimic-10k/corpus.jsonl               ← annotated evaluation corpus
```

The backend discovers both automatically on startup — no registration or config change needed. The model appears in the `huggingface_ner` pipe's model dropdown, and `mimic-10k` appears in the Datasets view.

### About the mimic-10k corpus

MIMIC-III clinical notes are distributed with PHI already redacted — the original identifiers are replaced with bracketed placeholders like `[** Name **]` — but the dataset ships with **no PHI span annotations**. That makes it unusable for training or evaluating a de-identification model directly, because there is nothing to measure against.

To produce a labeled corpus, synthetic PHI was injected back into 10,000 notes at the redacted positions using the platform's own surrogate pipeline: realistic fake names, dates, MRNs, phone numbers, and addresses replace each `[** ... **]` placeholder, and those insertion positions become the ground-truth spans. The result looks like real clinical notes and every PHI span is labeled — suitable for both training and held-out evaluation.

---

## Optional Extras

The base install includes Presidio, HuggingFace inference, and LLM clients. The remaining extras are opt-in for specific workflows.

| Extra | What it adds | When you need it |
|-------|--------------|------------------|
| `.[dev]` | `pytest`, `pytest-cov`, `ruff`, `pandas`, `faker` | Running tests + lint locally |
| `.[scripts]` | `pandas`, `faker` | Analytics and dataset-transform scripts; surrogate output mode |
| `.[train]` | `datasets`, `seqeval`, `accelerate` | HuggingFace fine-tuning (`clinical-deid train run`) |
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

All settings are controlled via environment variables with the `CLINICAL_DEID_` prefix (or a `.env` file at the repo root):

| Variable | Default | Description |
|----------|---------|-------------|
| `CLINICAL_DEID_LABEL_SPACE_NAME` | `clinical_phi` | Active label space pack |
| `CLINICAL_DEID_RISK_PROFILE_NAME` | `clinical_phi` | Active risk profile |
| `CLINICAL_DEID_DATABASE_URL` | `sqlite:///./data/app.sqlite` | Audit DB connection |
| `CLINICAL_DEID_PIPELINES_DIR` | `data/pipelines` | Pipeline JSON storage |
| `CLINICAL_DEID_CORPORA_DIR` | `data/corpora` | Dataset storage |
| `CLINICAL_DEID_MODELS_DIR` | `models` | Model artifact storage |
| `CLINICAL_DEID_MAX_BODY_BYTES` | `10485760` (10 MB) | Max API request body size |

Full reference: [docs/configuration.md](docs/configuration.md).
