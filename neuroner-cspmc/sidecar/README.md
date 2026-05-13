# NeuroNER HTTP sidecar

Inference and evaluation use **FastAPI** (uvicorn) in this container — the `neuroner_ner` pipe has no subprocess or venv paths in pipeline configs. Interactive API docs: **`GET /docs`** (OpenAPI).

**Docker runs only the NeuroNER + TensorFlow 1.x runtime.** Your **trained checkpoints** and **GloVe word embeddings** stay on the **host** under this repo and are **bind-mounted** into the container at runtime (`models/neuroner/`, `data/word_vectors/`, `data/neuroner_deploy/`). You are not copying models into the image for inference; change files on disk and restart the container (or rely on `:ro` mounts) as usual.

Training still uses the local NeuroNER venv: `./scripts/neuroner_train.sh` and `./scripts/setup_neuroner.sh`.

## Run

From the **repository root**:

```bash
docker compose -f neuroner-cspmc/sidecar/compose.yaml up -d --build
```

- **`NEURONER_MODELS_ROOT`** — path inside the container to the mounted `models/neuroner/` parent (default `/models/neuroner`).
- **`NEURONER_DEFAULT_MODEL`** — subdirectory name to load at startup (so `/health` can go green without a request). The Playground pipeline **`model`** field must match a folder name under that root; requests send `model` in `POST /v1/predict` and `GET /v1/labels?model=…` so the sidecar can **switch checkpoints** without editing compose.

Legacy: **`NEURONER_MODEL_FOLDER`** (full path to one model dir) still works; it sets the parent as `NEURONER_MODELS_ROOT` and the basename as the default model name.

## Host app

Point the API at the sidecar (default):

```bash
export PYPEDEID_NEURONER_HTTP_URL=http://127.0.0.1:8765
```

Or set `base_url` on the pipe config. Override the port in `compose.yaml` if needed.

## API (sidecar)

| Method | Path | |
|--------|------|---|
| GET | `/health` | 200 when a model is loaded; 503 while loading or if startup load failed |
| GET | `/docs` | Swagger UI (OpenAPI) |
| GET | `/v1/labels` | Query: `model=<subdir>` **or** `model_folder=/absolute/path` (must resolve under `NEURONER_MODELS_ROOT`). Response includes `labels`, `model`, `model_folder`. |
| POST | `/v1/predict` | JSON body: `text`, and either `model` (subdirectory name) **or** `model_folder` (absolute path in the container). Omit both to use `NEURONER_DEFAULT_MODEL`. Response includes `entities`, `model`, `model_folder`. |

The main app pipe usually sends **`model`** only; set optional **`model_folder`** in the pipeline config to pass a full container path (e.g. `/models/neuroner/my_export`).

Each entity includes optional **`confidence`** (0–1): softmax probability of the predicted label at each token, averaged over tokens overlapping the span. The main `neuroner_ner` pipe passes this through to **`EntitySpan.confidence`** without filtering spans.
