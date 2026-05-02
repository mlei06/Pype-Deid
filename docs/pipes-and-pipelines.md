# Pipes and Pipelines

The pipe system is the core abstraction for PHI detection and span-level post-processing. Pipelines registered in JSON are expected to **produce spans** on an `AnnotatedDocument`. Replacing text with tags, masks, or surrogates is usually done at the API layer via `output_mode` on `/process/...` (see [api.md](api.md)); the `Redactor` protocol still exists for legacy integrations but is not represented in the default pipe catalog.

## Core concepts

### AnnotatedDocument

The universal data type flowing through every pipe:

```python
@dataclass
class Document:
    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class EntitySpan:
    start: int          # character offset (inclusive)
    end: int            # character offset (exclusive)
    label: str          # entity type, e.g. "PATIENT", "DATE"
    confidence: float | None = None
    source: str | None = None       # which pipe produced this span

@dataclass
class AnnotatedDocument:
    document: Document
    spans: list[EntitySpan]
```

### Pipe protocol

Every pipe implements:

```python
class Pipe(Protocol):
    def forward(self, doc: AnnotatedDocument) -> AnnotatedDocument: ...
```

Input document in, annotated document out. Pipes are pure transformations — they don't mutate the input.

### Pipe roles

Pipes are grouped by what they do:

| Role | Protocol | What it does |
|------|----------|-------------|
| **Detector** | `Detector` | Adds spans to the document (PHI detection) |
| **SpanTransformer** | `SpanTransformer` | Modifies, filters, or merges existing spans |
| **Redactor** | `Redactor` | Transforms the document text (replaces PHI with placeholders) |
| **Preprocessor** | `Preprocessor` | Modifies text before detection (e.g. normalisation) |

Detectors additionally expose a `labels` property listing the entity types they can detect.

## Built-in pipes

### Detectors

#### `regex_ner` — Regex pattern matching

Detects PHI using compiled regex patterns. Ships with built-in patterns for common entity types.

```json
{"type": "regex_ner", "config": {}}
```

**Built-in labels:** `DATE`, `PHONE`, `EMAIL`, `ID`, `MRN`, `POSTAL_CODE_CA`, `OHIP`, `SIN`, `SSN`

To use only specific labels:

```json
{"type": "regex_ner", "config": {"labels": ["DATE", "PHONE", "EMAIL"]}}
```

Custom patterns per label:

```json
{
  "type": "regex_ner",
  "config": {
    "per_label": {
      "CUSTOM_ID": {
        "patterns": ["\\bCID-\\d{6}\\b"]
      }
    }
  }
}
```

Supports label mapping to rename output labels:

```json
{
  "type": "regex_ner",
  "config": {
    "label_mapping": {"MRN": "IDNUM", "SIN": "IDNUM"}
  }
}
```

#### `whitelist` — Dictionary/phrase matching

Matches exact phrases from term lists. Ships with bundled lists for common entity types.

```json
{"type": "whitelist", "config": {}}
```

Custom terms per label:

```json
{
  "type": "whitelist",
  "config": {
    "per_label": {
      "HOSPITAL": {
        "terms": ["Mass General", "MGH", "Brigham and Women's"]
      }
    }
  }
}
```

Terms are matched with flexible whitespace (multiple spaces, tabs, newlines all match). The UI supports uploading `.txt` files (one term per line) via the `/pipelines/whitelist/parse-lists` endpoint.

#### `presidio_ner` — Microsoft Presidio

Wraps the Presidio Analyzer for NER-based detection.

**Requires:** included in the base install (`pip install -e .`).

```json
{
  "type": "presidio_ner",
  "config": {
    "model": "spacy/en_core_web_lg",
    "entity_map": {
      "PERSON": "PATIENT",
      "DATE_TIME": "DATE",
      "LOCATION": "LOCATION_OTHER"
    }
  }
}
```

| Config field | Purpose |
|-------------|---------|
| `model` | Presidio model string (e.g. `spacy/en_core_web_lg`, `huggingface/obi/deid_roberta_i2b2`) |
| `entity_map` | Map Presidio entity types to your label space (see `PresidioNerConfig` for `entities` filter and other fields) |

**SpaCy data packages and load-time behavior:** the base install pulls Python packages (`presidio-analyzer[transformers]`, `spacy`, `transformers`, `torch`) but **not** spaCy *language data*. The pipe constructs the Presidio analyzer when the pipeline **loads**; if the spaCy package for your `model` is missing, startup fails with a spaCy / Presidio error (there is **no** automatic downgrade to a smaller model or to the **fast** profile). Install the data that matches `config.model`, e.g. `python -m spacy download en_core_web_lg` for the default spaCy model. For **HuggingFace** Presidio models (`huggingface/…`), this project still uses **`en_core_web_sm`** as the paired spaCy engine in Presidio's configuration — install it even though NER comes from the HF checkpoint. The CLI **balanced** profile only falls back to **fast** when the Presidio *package* is not importable, not when a spaCy model is missing.

#### `huggingface_ner` — Hugging Face token classification

Loads checkpoints from `models/huggingface/{name}/` (see [models/README.md](../models/README.md)).

**Requires:** included in the base install (`transformers` and `torch` ship with `pip install -e .`). Add `[train]` only if you also plan to fine-tune via `clinical-deid train run`.

```json
{"type": "huggingface_ner", "config": {"model": "my-deid-model"}}
```

#### `llm_ner` — LLM-prompted detection

**Requires:** included in the base install (`httpx` and `openai` ship with `pip install -e .`). Configure an OpenAI-compatible API key in settings (`OPENAI_API_KEY` or `CLINICAL_DEID_OPENAI_API_KEY`).

#### `neuroner_ner` — NeuroNER (HTTP sidecar)

**Requires:** NeuroNER service reachable at the configured URL (see [neuroner-setup.md](neuroner-setup.md)).

### Span transformers

#### `blacklist` — False positive filter

Removes detected spans that match benign vocabulary (common words, medical terms that look like names, etc.).

```json
{
  "type": "blacklist",
  "config": {
    "mode": "any_token",
    "terms": ["Dr", "Mr", "Mrs", "mg", "mL"]
  }
}
```

**Match modes:**

| Mode | Behaviour |
|------|-----------|
| `any_token` | Remove span if any whitespace-delimited token matches a term |
| `whole_span` | Remove span only if the entire text (whitespace-normalized) matches a term |
| `substring` | Remove span if any term appears as a substring |
| `overlap_document` | Remove spans overlapping blacklist regions (literal terms + regex patterns) in the full document text |

Ships with a bundled `notes_common.txt` blacklist. Per-label filtering is also supported:

```json
{
  "type": "blacklist",
  "config": {
    "mode": "any_token",
    "terms": ["Dr", "Mr"],
    "labels": ["PATIENT"]
  }
}
```

#### `resolve_spans` — Span deduplication and overlap resolution

Merges or filters overlapping spans produced by detectors.

```json
{"type": "resolve_spans", "config": {"strategy": "longest_non_overlapping"}}
```

**Strategies:**

| Strategy | Behaviour |
|----------|-----------|
| `union` | Keep all spans (no dedup) |
| `exact_dedupe` | Drop spans with identical start, end, and label |
| `consensus` | Keep spans agreed upon by multiple groups |
| `max_confidence` | Greedy selection by highest confidence score |
| `longest_non_overlapping` | Greedy selection by span length |

#### `label_mapper` — Remap all span labels on the document

Applies to **every span** in `doc.spans` at that stage (not only the previous pipe). Use a **final** `label_mapper` after `resolve_spans` to map multiple detectors onto one gold vocabulary (e.g. eval). Per-detector `label_mapping` / `remap` only affects that detector’s new spans; use the pipeline `label_mapper` when you need one cross-cutting map.

```json
{"type": "label_mapper", "config": {"mapping": {"NAME": "PATIENT"}, "drop_unmapped": false}}
```

#### `label_filter` — Keep or drop labels

Exactly one of `keep` or `drop` must be set:

```json
{"type": "label_filter", "config": {"keep": ["PATIENT", "DATE"]}}
```

#### `consistency_propagator` — Propagate high-confidence spans

Copies span text to all other occurrences in the document (useful after strong detectors). See `ConsistencyPropagatorConfig` in code for `min_confidence`, `labels`, etc.

### Redacted / surrogate text

There is no `presidio_anonymizer` (or similar) entry in the **pipe catalog**. Use `POST /process/{pipeline}` with `output_mode=redacted` or `output_mode=surrogate`, or `POST /process/redact` with client-supplied spans.

### Built-in combinators

The JSON `Pipeline` wrapper and merge helpers live in `combinators.py`. Registered catalog types include `label_mapper`, `label_filter`, and `resolve_spans`; the `Pipeline` class is used when loading nested pipeline specs in code.

| Symbol | Purpose |
|--------|---------|
| `Pipeline` | Sequential execution of a list of pipes |
| `LabelMapper` | Same behaviour as the `label_mapper` pipe |
| `LabelFilter` | Same behaviour as the `label_filter` pipe |
| `ResolveSpans` | Same behaviour as the `resolve_spans` pipe |

## Pipeline configuration

A pipeline is a JSON document that defines a sequence of pipes:

### Sequential pipeline

```json
{
  "pipes": [
    {"type": "regex_ner", "config": {}},
    {"type": "whitelist", "config": {}},
    {"type": "resolve_spans", "config": {"strategy": "longest_non_overlapping"}}
  ]
}
```

Pipes execute in order. Each pipe receives the output of the previous one.

### Chaining multiple detectors

There is no `parallel` pipe type in pipeline JSON. Run detectors **in sequence** (each adds spans), then merge with `resolve_spans`:

```json
{
  "pipes": [
    {"type": "regex_ner", "config": {}},
    {"type": "presidio_ner", "config": {"model": "spacy/en_core_web_lg"}},
    {"type": "resolve_spans", "config": {"strategy": "max_confidence"}}
  ]
}
```

**Merge strategies** for `resolve_spans`: `union`, `exact_dedupe`, `consensus`, `max_confidence`, `longest_non_overlapping`.

### Intermediary tracing

Tracing is a runtime option, not part of the pipeline config. Pass `?trace=true` as a query parameter on the process endpoint to capture the document state after every pipeline step:

```
POST /process/clinical-fast?trace=true
```

You can also call a **deploy mode** alias (e.g. `POST /process/fast?trace=true`) — the path segment is resolved via `data/modes.json`.

The API response includes an `intermediary_trace` array with one snapshot per step.

## Adding a new pipe

Adding a detector requires three things: a config, a pipe class, and a registration call.

### Step 1: Define the config

Create a Pydantic model for your pipe's configuration:

```python
# src/clinical_deid/pipes/my_detector/pipe.py
from __future__ import annotations
from pydantic import BaseModel, Field

class MyDetectorConfig(BaseModel):
    threshold: float = Field(0.5, description="Minimum confidence", ge=0.0, le=1.0)
    labels: list[str] = Field(default_factory=lambda: ["PATIENT", "DATE"])
```

Use `Field()` with `description` for automatic UI form generation. Additional UI hints are available via the `ui_*` class-var convention:

```python
class MyDetectorConfig(BaseModel):
    model_path: str = Field("", description="Path to model checkpoint")
    model_path_ui_widget: ClassVar[str] = "file"  # renders as file picker in UI
```

### Step 2: Implement the pipe

```python
from clinical_deid.domain import AnnotatedDocument, EntitySpan

class MyDetectorPipe:
    def __init__(self, config: MyDetectorConfig) -> None:
        self.config = config
        # Expensive init (load model, compile patterns, etc.)

    @property
    def labels(self) -> list[str]:
        return self.config.labels

    def forward(self, doc: AnnotatedDocument) -> AnnotatedDocument:
        new_spans = []
        # ... your detection logic ...
        # Example: find all "SECRET" substrings
        text = doc.document.text
        import re
        for m in re.finditer(r"SECRET", text):
            new_spans.append(EntitySpan(
                start=m.start(),
                end=m.end(),
                label="SECRET",
                confidence=1.0,
                source="my_detector",
            ))
        return AnnotatedDocument(
            document=doc.document,
            spans=[*doc.spans, *new_spans],
        )
```

Key rules:
- **Don't mutate the input** — return a new `AnnotatedDocument`.
- **Append to existing spans** — detectors add to `doc.spans`, they don't replace them.
- **Set `source`** — helps with debugging and tracing.

### Step 3: Register

**For built-in pipes**, add a single `PipeCatalogEntry` to the `_CATALOG` list in `registry.py`. The `config_path` and `pipe_path` fields use `"module:Class"` format. `_register_builtins()` imports and registers every catalog entry automatically (optional deps are silently skipped):

```python
PipeCatalogEntry(
    name="my_detector",
    description="My custom PHI detector",
    role="detector",
    extra="my_extra",                # None if always available
    install_hint="pip install '.[my_extra]'",
    config_path="clinical_deid.pipes.my_detector.pipe:MyDetectorConfig",
    pipe_path="clinical_deid.pipes.my_detector.pipe:MyDetectorPipe",
),
```

**For external/plugin pipes**, call `register()` directly from your package:

```python
from clinical_deid.pipes.registry import register
from my_plugin.pipe import MyDetectorConfig, MyDetectorPipe

register("my_detector", MyDetectorConfig, MyDetectorPipe)
```

### Step 5 (optional): Label mapping support

If your detector should support label remapping, use the `DetectorWithLabelMapping` protocol and the shared utilities:

```python
from clinical_deid.pipes.detector_label_mapping import (
    apply_detector_label_mapping,
    detector_label_mapping_field,
)

class MyDetectorConfig(BaseModel):
    label_mapping: dict[str, str | None] = detector_label_mapping_field()

class MyDetectorPipe:
    def forward(self, doc: AnnotatedDocument) -> AnnotatedDocument:
        # ... detect spans ...
        mapped_spans = apply_detector_label_mapping(new_spans, self.config.label_mapping)
        return AnnotatedDocument(document=doc.document, spans=[*doc.spans, *mapped_spans])
```

Setting a label to `null` in the mapping drops those spans entirely.

## Pipeline execution flow

When the API receives `POST /process/{pipeline_name}`:

1. **Load config** — Read the pipeline JSON from the filesystem (`data/pipelines/{name}.json`).
2. **Build** — `load_pipeline(config)` deserialises each step in order and instantiates the registered pipe types.
3. **Execute** — Run the chain (`forward`) on the request text wrapped as an `AnnotatedDocument`. With `?trace=true`, capture snapshots after each step.
4. **Output** — The response includes spans. Redacted or surrogate **text** is produced from those spans when `output_mode` is `redacted` or `surrogate` (see [api.md](api.md)), not from a separate redactor pipe in the catalog.

## UI schema generation

The platform auto-generates JSON Schema for each pipe config, enriched with UI hints (`ui_widget`, `ui_placeholder`, etc.). The Playground pipeline builder consumes these schemas for dynamic forms.

```python
from clinical_deid.pipes.ui_schema import pipe_config_json_schema
from clinical_deid.pipes.regex_ner import RegexNerConfig

schema = pipe_config_json_schema(RegexNerConfig)
# Returns JSON Schema dict with ui_* annotations
```

The `/pipelines/pipe-types` endpoint returns these schemas for all registered pipes.
