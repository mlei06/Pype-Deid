# LLM Synthesis

Generate synthetic clinical notes with embedded PHI entities using an OpenAI-compatible LLM. The synthesis module produces `AnnotatedDocument` objects with character-level span offsets, ready for training or evaluation.

**Requires:** included in the base install (`httpx` and `openai` ship with `pip install -e .`).

## Architecture

The synthesis pipeline is composed of swappable components:

```
LLMSynthesizer
  ├── LLMClient            — HTTP client (OpenAI-compatible)
  ├── PromptTemplate       — System/user message templates
  ├── PhiTypesFormatter    — Formats the allowed entity type list
  ├── FewShotFormatter     — Formats example notes for the prompt
  └── parse response       — Extracts clinical note + PHI dict from model output
         │
         ▼
  SynthesisResult → AnnotatedDocument (with span alignment)
```

## Quick start

### 1. Configure the LLM client

Set your API key and model in `.env`:

```
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

Or use any OpenAI-compatible endpoint (local Ollama, vLLM, etc.) by changing `OPENAI_BASE_URL`.

### 2. Generate a note

```python
from pypedeid.config import get_settings
from pypedeid.synthesis import (
    LLMSynthesizer,
    FewShotExample,
    default_clinical_note_synthesis_template,
    DefaultPhiTypesFormatter,
    DefaultFewShotFormatter,
    CompositePromptParts,
    synthesis_result_to_annotated_document,
)

settings = get_settings()
client = settings.openai_chat_client()

# Define which PHI types to include
phi_types = ["PATIENT", "DATE", "HOSPITAL", "DOCTOR", "AGE", "PHONE"]

# Provide few-shot examples
examples = [
    FewShotExample(
        clinical_note="Patient John Smith, DOB 03/15/1952, was admitted to MGH on 01/10/2024.",
        phi={"PATIENT": ["John Smith"], "DATE": ["03/15/1952", "01/10/2024"], "HOSPITAL": ["MGH"]},
    ),
]

# Build the synthesizer
template = default_clinical_note_synthesis_template()
parts = CompositePromptParts(
    phi_types=DefaultPhiTypesFormatter(phi_types=phi_types),
    few_shot=DefaultFewShotFormatter(examples=examples),
)

synthesizer = LLMSynthesizer(
    client=client,
    template=template,
    parts=parts,
)

# Generate
result = synthesizer.generate_one()

# Convert to AnnotatedDocument with aligned spans
doc = synthesis_result_to_annotated_document(result, doc_id="synth-001")
print(doc.document.text)
print(doc.spans)
```

## Components in detail

### LLMClient

A protocol with a single method:

```python
class LLMClient(Protocol):
    def complete(self, messages: list[ChatMessage], **kwargs) -> str: ...
```

Two implementations ship:

| Class | Purpose |
|-------|---------|
| `OpenAICompatibleChatClient` | HTTP client for any OpenAI-compatible API (OpenAI, Azure, Ollama, vLLM) |
| `StaticResponseClient` | Returns canned responses for testing |

`OpenAICompatibleChatClient` takes `base_url`, `api_key`, and `model`. It sends a `POST` to `{base_url}/chat/completions` with the standard message format.

### PromptTemplate

String templates with placeholders that are filled by the formatters:

| Placeholder | Filled by |
|-------------|-----------|
| `{phi_types_block}` | `PhiTypesFormatter` |
| `{examples_block}` | `FewShotFormatter` |
| `{special_rules}` | Optional extra instructions |

The default template (`default_clinical_note_synthesis_template()`) instructs the model to produce output in the format:

```
Clinical Note: "..."
PHI: {"LABEL": ["value1", "value2"], ...}
```

### Formatters

| Formatter | What it does |
|-----------|-------------|
| `DefaultPhiTypesFormatter` | Renders entity types as a comma-separated quoted list |
| `DefaultFewShotFormatter` | Renders examples as `Clinical Note: "...", PHI: {...}` blocks |

Both follow protocols (`PhiTypesFormatter`, `FewShotFormatter`), so you can swap in custom implementations.

### Response parsing

`parse_synthesis_response()` extracts:
- The clinical note text (from the `Clinical Note: "..."` block)
- The PHI dictionary (from the `PHI: {...}` block)

It handles common LLM formatting quirks: missing quotes, trailing commas, markdown code fences, and alternative JSON layouts.

### Span alignment

`synthesis_result_to_annotated_document()` converts a `SynthesisResult` (note text + PHI dict) into an `AnnotatedDocument` with character-level spans:

1. For each label in the PHI dict, iterates over the surface strings.
2. Finds each string's first unseen occurrence in the note text (greedy forward search).
3. Creates an `EntitySpan(start, end, label)`.
4. Optionally drops overlapping spans.
5. Stores the full PHI dict in `document.metadata["phi_entities"]` for reference.

```python
doc = synthesis_result_to_annotated_document(
    result,
    doc_id="synth-001",
    remove_overlaps=True,   # default: True
)
```

## Special rules

You can inject extra instructions into the prompt (e.g. handling titles):

```python
from pypedeid.synthesis import person_title_fewshot_rules

template = default_clinical_note_synthesis_template()
# The special_rules slot accepts any string
synthesizer = LLMSynthesizer(
    client=client,
    template=template,
    parts=parts,
    special_rules=person_title_fewshot_rules(),
)
```

`person_title_fewshot_rules()` returns instructions for how to handle "Dr. John" vs "Mr. John" extraction (include the title in the PATIENT span).

## Batch generation

The synthesizer generates one note at a time. For bulk generation, loop and collect:

```python
docs = []
for i in range(100):
    result = synthesizer.generate_one()
    doc = synthesis_result_to_annotated_document(
        result, document_id=f"synth-{i:04d}"
    )
    docs.append(doc)

# Write into the colocated corpora layout (same as ``POST /datasets/generate``)
from pypedeid.config import get_settings
from pypedeid.dataset_store import CORPUS_JSONL_NAME, commit_colocated_dataset
from pypedeid.ingest.sink import write_annotated_corpus

settings = get_settings()
output_name = "llm-batch"  # must not already exist under corpora_dir
home = settings.corpora_dir / output_name
home.mkdir(parents=True)
write_annotated_corpus(docs, jsonl=home / CORPUS_JSONL_NAME)
commit_colocated_dataset(
    settings.corpora_dir,
    output_name,
    "jsonl",
    description="Local LLM batch",
)
```

## Testing

Use `StaticResponseClient` to test synthesis pipelines without hitting an API:

```python
from pypedeid.synthesis import StaticResponseClient

client = StaticResponseClient(
    response='Clinical Note: "Patient Jane Doe, DOB 01/01/1990."\nPHI: {"PATIENT": ["Jane Doe"], "DATE": ["01/01/1990"]}'
)
```
