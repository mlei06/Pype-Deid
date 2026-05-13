# Data Ingestion

This guide covers converting raw clinical datasets into the platform's annotated formats (JSONL and BRAT). Each dataset has a dedicated script under `scripts/` and a corresponding parser module under `src/pypedeid/ingest/`.

**Datasets tab / registry:** the admin **corpora** root keeps **one canonical layout** — `data/corpora/<name>/corpus.jsonl` plus `dataset.json` (analytics cache). If a script below writes **BRAT** under `data/corpora/...`, use **Convert BRAT → JSONL** in the UI or `pypedeid dataset import-brat <brat_dir> --name <name>` to produce that JSONL home. Intermediate BRAT trees can stay on disk until you import; materialized tool exports (BRAT, CoNLL, …) go under `data/exports/` by default (`PYPEDEID_EXPORTS_DIR`).

## Output formats

All scripts produce one or both of:

- **JSONL** — one `AnnotatedDocument` per line (document ID, text, metadata, PHI spans with character offsets)
- **BRAT** — paired `.txt` / `.ann` files, optionally split into `train/`, `valid/`, `test/` subdirectories

## PhysioNet i2b2

Converts PhysioNet de-identification track data (an `id.text` file of clinical notes and an `ann.csv` of entity annotations) into BRAT format with train/valid/test splits.

**Requires:** `pip install -e ".[scripts]"` (pandas)

### Basic usage

```bash
python scripts/process_physionet.py \
  --text data/raw/physionet/id.text \
  --annotations data/raw/physionet/ann.csv \
  --output data/corpora/physionet/brat
```

This writes a flat BRAT directory, then splits it into `train/`, `valid/`, `test/` subdirectories (default ratio 70/15/15).

### With label remapping

PhysioNet uses fine-grained labels (`NAME`, `LOCATION`, `CITY`, etc.). To map them to your own label set, pass a JSON file:

```bash
python scripts/process_physionet.py \
  --text data/raw/physionet/id.text \
  --annotations data/raw/physionet/ann.csv \
  --output data/corpora/physionet/brat \
  --label-map scripts/label_maps/physionet_to_deid_example.json
```

The label map is a simple `{"source_label": "target_label"}` dictionary. An example ships at `scripts/label_maps/physionet_to_deid_example.json`:

```json
{
  "NAME": "PATIENT",
  "LOCATION": "LOCATION_OTHER",
  "CITY": "LOCATION_OTHER",
  "STATE": "LOCATION_OTHER",
  "COUNTRY": "LOCATION_OTHER",
  "ID": "IDNUM",
  "ORGANIZATION": "HOSPITAL",
  "PROFESSION": "DOCTOR",
  "DATE": "DATE",
  "AGE": "AGE",
  "HOSPITAL": "HOSPITAL",
  "PHONE": "PHONE"
}
```

### Customising splits

Split ratios and seed are configurable via `--train`, `--valid`, `--test`, and `--seed` flags.

### What the script does

1. Parses `id.text` into individual note records (double-newline delimited, first line is the record ID).
2. Reads `ann.csv` and groups annotations by record ID.
3. Converts each record to a `.txt` / `.ann` BRAT pair.
4. Optionally remaps entity labels.
5. Splits the flat directory into `train/`, `valid/`, `test/`.

**Parser module:** `pypedeid.ingest.brat`

---

## ASQ-PHI

Converts the ASQ-PHI synthetic clinical queries dataset into JSONL and/or BRAT. The raw file uses a custom block format (`===QUERY===` / `===PHI_TAGS===` delimiters with JSON tag lines).

### Basic usage

```bash
# JSONL output
python scripts/process_asq_phi.py \
  --input data/raw/ASQ-PHI/synthetic_clinical_queries.txt \
  --output-jsonl data/corpora/asq_phi/asq_phi.jsonl

# Flat BRAT directory
python scripts/process_asq_phi.py \
  --input data/raw/ASQ-PHI/synthetic_clinical_queries.txt \
  --output-brat-dir data/corpora/asq_phi/brat

# BRAT corpus with train/valid/test splits
python scripts/process_asq_phi.py \
  --input data/raw/ASQ-PHI/synthetic_clinical_queries.txt \
  --output-brat-corpus data/corpora/asq_phi/brat \
  --brat-seed 42 --brat-train 0.7 --brat-valid 0.15
```

### Options

| Flag | Purpose |
|------|---------|
| `--output-jsonl` | Write JSONL file |
| `--output-brat-dir` | Write flat BRAT directory |
| `--output-brat-corpus` | Write BRAT corpus with split subdirectories |
| `--brat-seed` | Random seed for split assignment |
| `--brat-train`, `--brat-valid` | Split ratios (test = remainder) |
| `--single-line` | Collapse query whitespace to single spaces (offsets match collapsed text) |

### Entity labels

ASQ-PHI uses its own label set (`NAME`, `GEOGRAPHIC_LOCATION`, `DATE`, etc.). Spans are aligned by matching each `value` substring in order (first match forward from the previous span).

**Parser module:** `pypedeid.ingest.asq_phi`

---

## MIMIC NOTEEVENTS

Builds a synthetic BRAT corpus from MIMIC-III/IV `NOTEEVENTS.csv` by replacing `[**...**]` de-identification placeholders with realistic synthetic values using Faker.

**Requires:** `pip install -e ".[scripts]"` (pandas, faker)

### Basic usage

```bash
python scripts/process_mimic_noteevents.py \
  --input data/raw/mimic/NOTEEVENTS.csv \
  --output data/corpora/mimic/brat
```

### Options

| Flag | Default | Purpose |
|------|---------|---------|
| `--max-notes` | unlimited | Limit number of notes processed |
| `--merge-adjacent` | enabled | Merge adjacent PATIENT spans separated by a single space (e.g. "John" + "Smith" → "John Smith") |
| `--no-merge-adjacent` | | Disable adjacent span merging |
| `--train` | 0.7 | Train split ratio |
| `--valid` | 0.15 | Validation split ratio |
| `--test` | 0.15 | Test split ratio |
| `--seed` | 42 | Random seed for splitting |

### How it works

1. Streams `NOTEEVENTS.csv` row by row.
2. Finds all `[**...**]` placeholders with regex.
3. Maps each placeholder to a coarse entity type (DATE, PATIENT, LOCATION, HOSPITAL, AGE, IDNUM, PHONE, DOCTOR) based on the content inside the brackets.
4. Generates realistic replacement text using Faker with multi-locale support (US, UK, CA, CN, JP, KR, IN, EG) and custom providers for dates, hospitals, and universities.
5. Writes `.txt` / `.ann` BRAT pairs.
6. Optionally merges adjacent name spans.
7. Splits into `train/`, `valid/`, `test/`.

**Parser module:** `pypedeid.ingest.mimic`

---

## SREDH ChatGPT

Ingests the SREDH AI-Cup 2023 ChatGPT-generated synthetic PHI examples. Each source file contains a clinical note followed by tab-separated entity annotations.

### Basic usage

```bash
python scripts/ingest_sredh_chatgpt.py \
  --input-dir data/raw/sredh/chatgpt_generate \
  --output-jsonl data/corpora/sredh/sredh.jsonl

# Also produce BRAT output
python scripts/ingest_sredh_chatgpt.py \
  --input-dir data/raw/sredh/chatgpt_generate \
  --output-jsonl data/corpora/sredh/sredh.jsonl \
  --output-brat-dir data/corpora/sredh/brat
```

### How it works

1. Scans the input directory for `.txt` files.
2. For each file, splits the content into the clinical note text and a tab/newline-separated annotation block.
3. Parses annotations into `(label, text)` pairs and locates each entity's character offsets in the note.
4. Writes to JSONL and/or flat BRAT directory.

---

## Dataset analytics

After ingesting any dataset, you can inspect label distributions, span statistics, and overlap analysis:

```bash
# From JSONL
python scripts/dataset_analytics.py --jsonl data/corpora/asq_phi/asq_phi.jsonl

# From BRAT corpus (train/valid/test subdirectories)
python scripts/dataset_analytics.py --brat-corpus data/corpora/physionet/brat

# From a single BRAT directory
python scripts/dataset_analytics.py --brat-dir data/corpora/physionet/brat/train
```

Output includes document count, total spans, label frequency, character/token length statistics, spans-per-document histogram, overlap counts, and label co-occurrence matrix.

### List spans for one label

```bash
python scripts/list_spans_by_label.py \
  --brat-corpus data/corpora/physionet/brat \
  --label DATE

# JSON format with limit
python scripts/list_spans_by_label.py \
  --jsonl data/corpora/asq_phi/asq_phi.jsonl \
  --label PHONE --format json --max 20
```

Default output is TSV with columns: `document_id`, `start`, `end`, `label`, `text`, `split`.

---

## Ingest raw text through a pipeline

Turn a folder of `.txt` files (or a plain `{id, text}` JSONL) into a registered
dataset by running a saved pipeline over it. The result is an annotated
corpus (`corpus.jsonl` + `dataset.json`) under `CORPORA_DIR/<output>`.

```bash
# CLI — dir of .txt files (name must match a file under data/pipelines/<name>.json, not a /process mode alias)
pypedeid dataset ingest-run \
  --input data/corpora/raw_txts \
  --pipeline clinical-fast \
  --output-name raw_txts_clinical_fast_silver

# CLI — one-off file (no registration)
pypedeid dataset ingest-run \
  --input notes.jsonl \
  --pipeline clinical-fast \
  --output-jsonl /tmp/out.jsonl

# API — source_path is resolved under CORPORA_DIR; '..' is rejected
curl -X POST http://localhost:8000/datasets/ingest-from-pipeline \
  -H "content-type: application/json" \
  -d '{
    "source_path": "raw_txts",
    "pipeline_name": "clinical-fast",
    "output_name": "raw_txts_clinical_fast_silver"
  }'
```

JSONL rows may be bare `{id, text}` or a wrapped `{document: {id, text}, spans: []}`;
spans on the input are ignored — detection comes from the pipeline.

---

## Annotated JSONL export

Export any registered dataset as an annotated JSONL file (one
`AnnotatedDocument` per line) that can be re-registered via `POST /datasets`
(`format: "jsonl"`) — a convenient round-trip for backups, review dumps, or
moving a dataset across environments.

```bash
# CLI
pypedeid dataset export i2b2-2014 -o data/exports/i2b2-2014 --format jsonl

# API
curl -X POST http://localhost:8000/datasets/i2b2-2014/export \
  -H "content-type: application/json" \
  -d '{"format": "jsonl"}'
```

The response `path` points at a `train.jsonl` under the configured exports
directory (`PYPEDEID_EXPORTS_DIR`, default `data/exports/<name>/`). Override
the filename with `--filename` / `"filename": "..."`.

### Surrogate-aligned exports

Add `--target-text surrogate` (CLI) or `"target_text": "surrogate"` (API) to
replace each document's text with a surrogate and realign spans into the new
text before export. Supply `--seed` / `"surrogate_seed"` for deterministic
runs. Any dataset containing overlapping spans is rejected with a 422 listing
the offending documents — resolve overlaps first (e.g. via the transform
endpoint).

---

## Programmatic loading

All ingest functionality is available as a Python library:

```python
from pypedeid.ingest import (
    load_annotated_corpus,          # unified loader
    load_annotated_documents_from_jsonl_bytes,
    load_brat_directory,
    load_brat_corpus_with_splits,
    write_annotated_corpus,         # unified writer
)

# Load from any supported source
docs = load_annotated_corpus(brat_corpus="data/corpora/physionet/brat")
docs = load_annotated_corpus(jsonl="data/corpora/asq_phi/asq_phi.jsonl")

# Write to any supported sink
write_annotated_corpus(docs, jsonl="output.jsonl")
write_annotated_corpus(docs, brat_corpus="output/brat")
```

The `load_annotated_corpus()` function accepts exactly one of `jsonl=`, `brat_dir=`, or `brat_corpus=`. BRAT corpus loading automatically sets `metadata["split"]` from the subdirectory name (`train`, `valid`, `test`, `dev`, `deploy`).
