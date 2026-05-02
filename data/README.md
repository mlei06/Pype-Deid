# Data Directory

All **mutable runtime state** for the API lives here — a deployment bind-mounts
this single directory (`./data:/app/data`) plus a read-only `./models:/app/models`
for weights. See [docs/deployment.md](../docs/deployment.md).

Most contents are git-ignored except `.gitkeep` placeholders, the seed
`pipelines/*.json` + `modes.json`, and two small **tracked** teaching
corpora — `corpora/sample_notes/` (15 annotated production-export notes)
and `corpora/sample_notes_surrogated/` (same notes with Faker-backed
surrogates replacing every PHI span).

```
data/
  pipelines/            Named pipeline JSON configs  (CLINICAL_DEID_PIPELINES_DIR)
                        — seed files are tracked; operator edits via Playground
                          admin UI or on disk
  modes.json            Deploy config: mode aliases, allowlist, production URL
                        (CLINICAL_DEID_MODES_PATH; mutable via PUT /deploy)
  evaluations/          Eval result JSON            (CLINICAL_DEID_EVALUATIONS_DIR)
  inference_runs/       Saved batch inference runs  (CLINICAL_DEID_INFERENCE_RUNS_DIR)
  app.sqlite            Audit log (SQLite)          (CLINICAL_DEID_DATABASE_URL)
  corpora/              Dataset homes (JSONL-only)  (CLINICAL_DEID_CORPORA_DIR)
                        — each dataset is ``<name>/corpus.jsonl`` plus optional
                          ``dataset.json`` (cached analytics). Drop a folder with
                          only ``corpus.jsonl`` and the API will create the manifest
                          on first list/refresh. BRAT on disk is not a stored layout
                          here; convert with ``POST /datasets/import/brat`` or
                          ``clinical-deid dataset import-brat``.
  exports/              Materialized exports        (CLINICAL_DEID_EXPORTS_DIR)
                        — default target for ``POST /datasets/{name}/export``
                          (BRAT, CoNLL, etc.), kept outside ``corpora/`` so the
                          corpus root stays canonical JSONL-only.
  dictionaries/         Whitelist / blacklist term lists (CLINICAL_DEID_DICTIONARIES_DIR)
  raw/                  Unprocessed source files before ingestion
```

| Directory / file | Purpose | Typical commands |
|------------------|---------|-----------------|
| `pipelines/` | Pipeline configs | Playground builder; `POST`/`PUT`/`DELETE /pipelines` |
| `modes.json` | Deploy mapping — mode **aliases** to pipeline names (`default_mode` seeded `fast` → `clinical-fast`; also `presidio`, `transformer`, `transformer_presidio`, `llm`, `llm_presidio`, `ensemble`) | Playground Deploy view; `GET`/`PUT /deploy` |
| `evaluations/` | One JSON file per eval run (Playground, API, or **CLI**); the Evaluate view lists `*.json` for history. | `clinical-deid eval`, `POST /eval/run`, `GET /eval/runs` |
| `inference_runs/` | Batch inference snapshots | `clinical-deid batch`, `POST /process/*` |
| `app.sqlite` | Audit log | Written by `log_run()` on every run |
| `corpora/` | Canonical **JSONL** datasets | `clinical-deid dataset register` (JSONL), `import-brat`, `POST /datasets/*` — **tracked** examples: `sample_notes` and `sample_notes_surrogated` (15 docs each) |
| `corpora/sample_notes/` | `corpus.jsonl` + `dataset.json` — annotated production-export notes | Default teaching corpus for Evaluate / CLI |
| `corpora/sample_notes_surrogated/` | Same notes with synthesized PHI surrogates | Non-PHI demo + surrogate-mode inspection |
| `exports/` | Exports (BRAT, training formats) | `POST /datasets/{name}/export`, `clinical-deid dataset export` |
| `dictionaries/` | Whitelist / blacklist term lists | `clinical-deid dict import`, `POST /dictionaries` |
| `raw/` | Drop source files before ingestion | `scripts/process_*.py` |
