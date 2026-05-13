# Dataset Transforms and Composition

Tools for reshaping, filtering, and merging annotated corpora before training or evaluation.

## Transforms

The transform pipeline applies operations in a fixed order:

```
label filter → label remap → target document count → boost by label → resplit
```

Each step is optional, but at least one output (`--output-jsonl` or `--output-brat-corpus`) is required.

### CLI usage

```bash
python scripts/transform_dataset.py \
  --brat-corpus data/corpora/physionet/brat \
  --label-map scripts/label_maps/physionet_to_deid_example.json \
  --target-documents 500 --seed 42 \
  --output-jsonl data/corpora/physionet_500.jsonl
```

### Input sources

Exactly one source is required:

| Flag | Format |
|------|--------|
| `--jsonl` | JSONL file |
| `--brat-dir` | Single BRAT directory |
| `--brat-corpus` | BRAT corpus with `train/valid/test/` subdirectories |

### Transform operations

#### Label filtering

Drop or keep specific labels:

```bash
# Keep only these labels
python scripts/transform_dataset.py \
  --brat-corpus data/corpora/physionet/brat \
  --keep-labels PATIENT DATE PHONE \
  --output-jsonl filtered.jsonl

# Drop specific labels
python scripts/transform_dataset.py \
  --brat-corpus data/corpora/physionet/brat \
  --drop-labels AGE IDNUM \
  --output-jsonl filtered.jsonl
```

`--keep-labels` and `--drop-labels` are mutually exclusive.

#### Label remapping

Rename entity labels using a JSON mapping file:

```bash
python scripts/transform_dataset.py \
  --brat-corpus data/corpora/physionet/brat \
  --label-map scripts/label_maps/physionet_to_deid_example.json \
  --output-jsonl remapped.jsonl
```

The mapping file is `{"old_label": "new_label"}`. Labels not present in the map are kept as-is. To drop a label via the map, set it to `null`.

#### Document resampling

Resize the corpus to a target document count:

```bash
# Downsample to 500 documents
python scripts/transform_dataset.py \
  --jsonl big_corpus.jsonl \
  --target-documents 500 --seed 42 \
  --output-jsonl sampled.jsonl

# Upsample (duplicates documents with new IDs)
python scripts/transform_dataset.py \
  --jsonl small_corpus.jsonl \
  --target-documents 2000 --seed 42 \
  --output-jsonl upsampled.jsonl
```

#### Boost by label

Duplicate documents containing a specific label to increase its representation:

```bash
python scripts/transform_dataset.py \
  --jsonl corpus.jsonl \
  --boost-label PHONE --boost-factor 3 \
  --output-jsonl boosted.jsonl
```

This duplicates every document that contains at least one `PHONE` span, tripling those documents in the output.

#### Re-split

Reassign train/valid/test splits:

```bash
python scripts/transform_dataset.py \
  --brat-corpus data/corpora/physionet/brat \
  --resplit "train=0.7,valid=0.15,test=0.1,deploy=0.05" --seed 42 \
  --output-jsonl resplit.jsonl
```

Weights are normalized to 1. The `deploy` split is an optional held-out bucket. Document order is preserved within each split.

### Output options

| Flag | Format |
|------|--------|
| `--output-jsonl` | Write JSONL file |
| `--output-brat-corpus` | Write BRAT corpus with split subdirectories |

### Programmatic API

```python
from pypedeid.transform import (
    run_transform_pipeline,
    filter_labels,
    apply_label_mapping,
    random_resize,
    boost_docs_with_label,
    reassign_splits,
    strip_split_metadata,
)

# Individual operations
docs = filter_labels(docs, keep={"PATIENT", "DATE", "PHONE"})
docs = apply_label_mapping(docs, {"NAME": "PATIENT", "CITY": "LOCATION"})
docs = random_resize(docs, target=500, seed=42)
docs = boost_docs_with_label(docs, label="PHONE", factor=3)
docs = reassign_splits(docs, weights={"train": 0.7, "valid": 0.15, "test": 0.15}, seed=42)
```

---

## Composition

Merge multiple annotated corpora into a single dataset using different strategies.

### CLI usage

```bash
python scripts/compose_datasets.py \
  --sources "brat-corpus:data/corpora/physionet/brat" "jsonl:data/corpora/asq_phi/asq_phi.jsonl" \
  --strategy merge \
  --output-jsonl data/corpora/combined.jsonl
```

### Source format

Sources are specified as `kind:path` strings:

| Kind | Path points to |
|------|---------------|
| `jsonl` | A JSONL file |
| `brat-dir` | A flat BRAT directory |
| `brat-corpus` | A BRAT corpus with split subdirectories |

### Strategies

#### `merge` (default)

Concatenates all sources in order. Simple and deterministic.

```bash
python scripts/compose_datasets.py \
  --sources "brat-corpus:data/corpora/physionet/brat" "jsonl:data/corpora/asq_phi/asq_phi.jsonl" \
  --strategy merge \
  --output-jsonl combined.jsonl
```

#### `interleave`

Round-robin across sources. Documents alternate between sources in order.

```bash
python scripts/compose_datasets.py \
  --sources "jsonl:corpus_a.jsonl" "jsonl:corpus_b.jsonl" "jsonl:corpus_c.jsonl" \
  --strategy interleave \
  --output-jsonl interleaved.jsonl
```

#### `proportional`

Weighted sampling without replacement. Each source contributes proportionally to its weight.

```bash
python scripts/compose_datasets.py \
  --sources "jsonl:large_corpus.jsonl" "jsonl:small_corpus.jsonl" \
  --strategy proportional \
  --weights 0.8 0.2 \
  --total 1000 \
  --output-jsonl proportional.jsonl
```

If a source is smaller than its allocated share, it contributes all its documents and the remainder is redistributed to other sources.

### Options

| Flag | Purpose |
|------|---------|
| `--strategy` | `merge`, `interleave`, or `proportional` |
| `--weights` | Per-source weights (for `proportional`; defaults to equal) |
| `--total` | Target total documents (for `proportional`) |
| `--shuffle` | Shuffle final output |
| `--seed` | Random seed for shuffling and sampling |
| `--namespace-ids` | Prefix document IDs with source index to avoid collisions |
| `--provenance` | Track source index and original ID in document metadata |
| `--output-jsonl` | Write JSONL output |
| `--output-brat-corpus` | Write BRAT corpus output |

### Provenance tracking

When `--provenance` is enabled, each document's metadata includes:

```json
{
  "source_index": 0,
  "original_id": "note_1234"
}
```

This lets you trace which source corpus a document came from.

### ID namespacing

When `--namespace-ids` is enabled, document IDs are prefixed with the source index:

```
src0_note_1234
src1_query_001
```

This prevents ID collisions when merging corpora that might share document IDs.

### Programmatic API

```python
from pypedeid.compose import (
    compose_corpora,
    compose_merge,
    compose_interleave,
    compose_proportional,
    load_one_source,
)

# High-level: load + compose in one call
docs = compose_corpora(
    source_specs=["brat-corpus:data/corpora/physionet/brat", "jsonl:asq_phi.jsonl"],
    strategy="proportional",
    weights=[0.7, 0.3],
    total=1000,
    seed=42,
    namespace_ids=True,
    provenance=True,
)

# Low-level: load sources yourself
corpus_a = load_one_source("brat-corpus:data/corpora/physionet/brat")
corpus_b = load_one_source("jsonl:data/corpora/asq_phi/asq_phi.jsonl")
merged = compose_merge([corpus_a, corpus_b])
```
