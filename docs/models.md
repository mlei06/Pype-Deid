# Model Registry

The platform uses a **filesystem-based model registry** — no database tables, no upload API. Drop model artifacts into the right directory, add a manifest, and reference the model from pipe configs.

## Directory layout

```
models/
├── spacy/
│   └── deid-ner-v1/
│       ├── model_manifest.json
│       └── model-best/          # spaCy model directory
├── huggingface/
│   └── deid-roberta-i2b2/
│       ├── model_manifest.json
│       ├── config.json          # HF model files
│       ├── pytorch_model.bin
│       └── tokenizer/
└── external/
    └── presidio-default/
        └── model_manifest.json  # metadata-only (model lives elsewhere)
```

## Supported frameworks

| Framework | Use case |
|-----------|---------|
| `spacy` | spaCy NER models (`.forward()` via `spacy.load()`) |
| `huggingface` | HuggingFace Transformers (token classification); use with the `huggingface_ner` pipe |
| `neuroner` | NeuroNER checkpoints when registered for sidecar workflows |
| `external` | Third-party models managed outside this repo (Presidio, cloud APIs) |

## Model manifest

Each model directory must contain a `model_manifest.json`:

```json
{
  "name": "deid-ner-v1",
  "framework": "spacy",
  "labels": ["PATIENT", "DATE", "HOSPITAL", "PHONE", "LOCATION_OTHER"],
  "base_model": "en_core_web_lg",
  "dataset": "physionet-i2b2",
  "metrics": {
    "f1": 0.92,
    "precision": 0.91,
    "recall": 0.93
  },
  "device": "cpu",
  "created_at": "2024-06-15T10:30:00Z"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Must match the directory name |
| `framework` | yes | One of `spacy`, `huggingface`, `neuroner`, `external` |
| `labels` | no | Entity types the model can detect |
| `base_model` | no | Parent model used for fine-tuning |
| `dataset` | no | Training dataset name |
| `metrics` | no | Evaluation metrics (freeform dict) |
| `device` | no | Target device (`cpu`, `cuda`, `mps`) |
| `created_at` | no | ISO 8601 timestamp |

## Discovery

The registry scans `models/{framework}/{name}/model_manifest.json` on each call:

```python
from pathlib import Path

from pypedeid.config import get_settings
from pypedeid.models import list_models, get_model

models_dir = get_settings().models_dir  # or Path("models")

for model in list_models(models_dir):
    print(f"{model.framework}/{model.name} — labels: {model.labels}")

hf_only = list_models(models_dir, framework="huggingface")

info = get_model(models_dir, "deid-roberta-i2b2")
print(info.path)
```

Override the directory with `PYPEDEID_MODELS_DIR` or `Settings.models_dir`.

## Using models in pipes

### `huggingface_ner`

Registered Hugging Face token-classification checkpoints use the **`model`** field (directory name under `models/huggingface/`):

```json
{
  "type": "huggingface_ner",
  "config": {
    "model": "deid-roberta-i2b2"
  }
}
```

See [pipes-and-pipelines.md](pipes-and-pipelines.md) for how models are referenced from pipe configs.

### Presidio with custom models

Presidio can use models from the registry by referencing them in its model string:

```json
{
  "type": "presidio_ner",
  "config": {
    "model": "HuggingFace/obi/deid_roberta_i2b2"
  }
}
```

For local models, point Presidio at the model path directly via the Presidio configuration.

## Training workflow

The registry is the output target for the training loop:

1. **Prepare data** — Use [data ingestion](data-ingestion.md) and [transforms](transforms-and-composition.md) to build a training corpus.
2. **Export** — `pypedeid dataset export NAME -o DIR --format huggingface|conll|spacy` (or use the dataset export API from the Playground).
3. **Train** — `pypedeid train run` (requires `pip install '.[train]'`) writes a full directory under `models/huggingface/{output_name}/` including `model_manifest.json`. You can also train with Hugging Face Trainer externally and copy artifacts in manually.
4. **Refresh** — `GET /models/refresh` or restart the server so `scan_models` picks up new directories.
5. **Use** — Reference the model directory name in `huggingface_ner` as `"model": "<name>"`.

## HTTP API

Models are listed and inspected via read-only routes (no upload or remote training):

```
GET /models                    — List models
GET /models/{framework}/{name} — Manifest-style detail
POST /models/refresh           — Rescan the models directory (admin scope when API keys are enabled; see configuration.md)
```

Training remains local — there is no API for uploading checkpoints or running training jobs.
