# Evaluation

Span-level evaluation metrics for measuring PHI detection quality. Available as a Python library, via `POST /eval/run`, and via `pypedeid eval`.

## Stored eval runs (`data/evaluations/`)

Server-side and CLI evals persist a JSON file per run under **`data/evaluations/`** (configurable with `PYPEDEID_EVALUATIONS_DIR`). The filename is **`{pipeline_name}_{YYYYMMDD_HHMMSS}.json`** (UTC timestamp from `save_eval_result` in `eval_store.py`). The Playground **Evaluate** view lists these with `GET /eval/runs` and loads detail with `GET /eval/runs/{id}` — so you can open **old runs** in the UI after the fact, whether you started the job from the **Playground**, the **HTTP API**, or **`pypedeid eval`**. The file stores aggregate metrics and metadata; per-document debug payloads (when requested) are **not** written to disk (see API docs).

**Labels:** `evaluate_pipeline` (and the HTTP/CLI entry points) compare **raw** gold and predicted span `label` strings. There is no `LabelSpace` normalization at the eval step — if your gold file uses different names than the pipeline, use a **`label_mapper`** (or per-detector remaps) so output strings match the corpus, or change the gold. Inference responses (`POST /process/*`) may still apply `default_label_space().normalize` to span labels; that is separate from evaluation.

## Matching modes

`compute_metrics(pred_spans, gold_spans, text)` returns four `MatchResult`s in one call:

- **strict** — exact match on `(start, end, label)`. Primary metric.
- **exact_boundary** — same `(start, end)`, label ignored (boundary detection only).
- **partial_overlap** — any character overlap with the same label.
- **token_level** — character-level BIO tags compared per position.

```python
from pypedeid.eval import compute_metrics, EvalMetrics

metrics: EvalMetrics = compute_metrics(pred_spans, gold_spans, text)
print(f"Strict   P={metrics.strict.precision:.3f}  R={metrics.strict.recall:.3f}  F1={metrics.strict.f1:.3f}")
print(f"Partial  F1={metrics.partial_overlap.f1:.3f}")
print(f"Token    F1={metrics.token_level.f1:.3f}")
```

Each `MatchResult` carries `precision`, `recall`, `f1`, `tp`, `fp`, `fn`, and `partial`.

## Evaluating on a corpus

For a full pipeline run across a dataset, use `evaluate_pipeline` — it produces overall metrics, **macro-averaged** P/R/F1 (unweighted mean over labels, so rare labels aren't drowned out by NAME/DATE), per-label breakdown, a label confusion matrix, risk-weighted recall, and per-document results sorted worst-first.

```python
from pypedeid.eval.runner import evaluate_pipeline
from pypedeid.ingest import load_annotated_corpus
from pypedeid.pipes.registry import load_pipeline

docs = load_annotated_corpus(jsonl="data/corpora/sample_notes/corpus.jsonl")
pipeline = load_pipeline({
    "pipes": [
        {"type": "regex_ner", "config": {}},
        {"type": "resolve_spans", "config": {"strategy": "longest_non_overlapping"}},
    ]
})

result = evaluate_pipeline(pipeline, docs)
print(f"Micro F1 = {result.overall.strict.f1:.3f}")
print(f"Macro F1 = {result.macro.strict.f1:.3f}  ({result.macro.strict.label_count} labels)")
print(f"Risk-weighted recall = {result.risk_weighted_recall:.3f}")
for label, lm in sorted(result.per_label.items()):
    print(f"  {label:20s} F1={lm.strict.f1:.3f}  support={lm.support}")
```

## API and CLI

Server-side evaluation is available via `POST /eval/run` and the `pypedeid eval` CLI. Both **write** a result file under `data/evaluations/` (see [Stored eval runs](#stored-eval-runs-dataevaluations) above). The runner supports multiple matching modes (strict, exact boundary, partial overlap, token-level), risk-weighted metrics, run comparison, and per-document breakdowns — see `src/pypedeid/eval/` and the OpenAPI schema when `/docs` is enabled.

**Gold data sources:** use a **registered dataset** (`dataset_name`) or a **`dataset_path` to a `.jsonl` file** on the server (paths must stay within the corpora root — `PYPEDEID_CORPORA_DIR`, default `data/corpora/`). BRAT gold must be converted to JSONL first (Datasets tab: **Convert BRAT → JSONL**, or `pypedeid dataset import-brat`). In Python, `load_annotated_corpus` can still load BRAT or JSONL from any path for ad-hoc scripts.
