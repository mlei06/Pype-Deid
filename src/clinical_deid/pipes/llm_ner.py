"""LLM-prompted NER detector.

Sends document text to an OpenAI-compatible LLM and asks it to identify PHI
substrings. The model returns each PHI string verbatim with a label; the pipe
locates each substring in the original text to produce
:class:`~clinical_deid.domain.EntitySpan` objects with exact offsets.

For backward compatibility with previously saved configs, the parser also
accepts the legacy offset-based response shape (``{start, end, label}``) and
will trust those offsets directly.

Requires ``pip install clinical-deid-playground[llm]``.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Iterable, Literal

from pydantic import BaseModel, Field

from clinical_deid.domain import AnnotatedDocument, EntitySpan
from clinical_deid.pipes.base import ConfigurablePipe
from clinical_deid.pipes.detector_label_mapping import accumulate_spans
from clinical_deid.pipes.ui_schema import field_ui

logger = logging.getLogger(__name__)

_DEFAULT_LABELS = [
    "PATIENT", "DOCTOR", "DATE", "HOSPITAL", "ID", "PHONE", "EMAIL",
    "LOCATION", "AGE", "SSN", "MRN",
]

_DEFAULT_PROMPT_TEMPLATE = """\
You are a clinical de-identification system. Identify all Protected Health Information (PHI) \
in the following clinical text.

Return a JSON object with a single key "spans" whose value is an array of objects, each with \
keys: "text" (string, the exact PHI substring as it appears in the text) and "label" (string, \
one of: {labels}).

Rules:
- Copy each PHI string EXACTLY as it appears, preserving punctuation, casing, and whitespace.
- Use only the labels listed above.
- If a PHI string occurs multiple times, list it once — the system will mark every occurrence.
- If no PHI is found, return: {{"spans": []}}
- Return ONLY the JSON object, no other text.

Clinical text:
---
{text}
---
"""

_REASONING_MODEL_PREFIXES: tuple[str, ...] = ("gpt-5", "o1", "o3", "o4")


def _is_reasoning_model(model: str) -> bool:
    return any(model.startswith(p) for p in _REASONING_MODEL_PREFIXES)


KnownLlmModel = Literal[
    "gpt-5.5",
    "gpt-5.5-pro",
    "gpt-5.4",
    "gpt-5.4-pro",
    "gpt-5.4-mini",
    "gpt-5.4-nano",
    "gpt-5.1",
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "o3",
    "o4-mini",
    "gpt-4o",
    "gpt-4o-mini",
]

ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh"]

_MODEL_DESCRIPTIONS: dict[str, str] = {
    "gpt-5.5": "GPT-5.5 — newest flagship reasoning model, highest accuracy on complex extraction.",
    "gpt-5.5-pro": "GPT-5.5 Pro — extended-reasoning flagship, slowest and most expensive.",
    "gpt-5.4": "GPT-5.4 — flagship reasoning model, high accuracy on complex extraction.",
    "gpt-5.4-pro": "GPT-5.4 Pro — extended-reasoning 5.4 tier.",
    "gpt-5.4-mini": "GPT-5.4 Mini — mid-tier reasoning model, strong accuracy at lower cost.",
    "gpt-5.4-nano": "GPT-5.4 Nano — cheapest 5.4 reasoning tier, fast structured extraction.",
    "gpt-5.1": "GPT-5.1 — reasoning model (deprecated in ChatGPT but still on the API).",
    "gpt-5": "GPT-5 — flagship reasoning model, highest accuracy on complex extraction.",
    "gpt-5-mini": "GPT-5 Mini — strong accuracy at a fraction of the cost.",
    "gpt-5-nano": "GPT-5 Nano — cheapest GPT-5 tier, fast structured extraction.",
    "gpt-4.1": "GPT-4.1 — high accuracy, large 1M-token context window.",
    "gpt-4.1-mini": "GPT-4.1 Mini — balanced speed and accuracy, long context.",
    "gpt-4.1-nano": "GPT-4.1 Nano — cheapest 4.1-tier, fast lightweight extraction.",
    "o3": "o3 — reasoning model, best on hard cases requiring multi-step inference.",
    "o4-mini": "o4-mini — reasoning model, fast and inexpensive for tricky cases.",
    "gpt-4o": "GPT-4o — legacy flagship, fast and accurate.",
    "gpt-4o-mini": "GPT-4o Mini — legacy small model, low-cost structured extraction.",
}


def default_base_labels() -> list[str]:
    """Default label space for the llm_ner detector."""
    return sorted(_DEFAULT_LABELS)


class LlmNerConfig(BaseModel):
    """Configuration for LLM-based NER."""

    model: KnownLlmModel = Field(
        default="gpt-4o-mini",
        description="OpenAI model to use.",
        json_schema_extra=field_ui(
            ui_group="Model",
            ui_order=1,
            ui_widget="described_select",
            ui_enum_descriptions=_MODEL_DESCRIPTIONS,
        ),
    )
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Sampling temperature (0 = deterministic). Ignored for reasoning models.",
        json_schema_extra={
            "multipleOf": 0.05,
            **field_ui(
                ui_group="Model",
                ui_order=2,
                ui_widget="slider",
            ),
        },
    )
    reasoning_effort: ReasoningEffort | None = Field(
        default="low",
        description=(
            "Reasoning depth for gpt-5 / o-series models. NER rarely needs deep reasoning; "
            "'low' keeps latency low and is supported across all reasoning models. "
            "'minimal' is faster but only works on gpt-5 / o-series (not gpt-5.1+). "
            "'none' / 'xhigh' are only supported on gpt-5.1+. Ignored for non-reasoning models."
        ),
        json_schema_extra=field_ui(
            ui_group="Model",
            ui_order=3,
            ui_widget="select",
        ),
    )
    labels: list[str] = Field(
        default_factory=lambda: list(_DEFAULT_LABELS),
        description="Entity labels injected into the prompt. The LLM will only detect these.",
        json_schema_extra={
            "default": list(_DEFAULT_LABELS),
            **field_ui(
                ui_group="Labels",
                ui_order=1,
                ui_widget="tag_list",
            ),
        },
    )
    prompt_template: str = Field(
        default=_DEFAULT_PROMPT_TEMPLATE,
        description="Prompt template sent to the LLM. Use {text} and {labels} placeholders.",
        json_schema_extra={
            "default": _DEFAULT_PROMPT_TEMPLATE,
            **field_ui(
                ui_group="Prompt",
                ui_order=1,
                ui_widget="textarea",
                ui_rows=14,
            ),
        },
    )
    max_text_length: int = Field(
        default=30_000,
        description="Truncate input text beyond this length to avoid token limits.",
        json_schema_extra=field_ui(
            ui_group="Advanced",
            ui_order=1,
            ui_widget="number",
            ui_advanced=True,
        ),
    )
    base_url: str | None = Field(
        default=None,
        description="Base URL for an OpenAI-compatible API. None uses the default.",
        json_schema_extra=field_ui(
            ui_group="Advanced",
            ui_order=2,
            ui_widget="text",
            ui_advanced=True,
        ),
    )
    api_key_env: str = Field(
        default="OPENAI_API_KEY",
        description="Environment variable name holding the API key.",
        json_schema_extra=field_ui(
            ui_group="Advanced",
            ui_order=3,
            ui_widget="text",
            ui_advanced=True,
        ),
    )
    source_name: str = Field(
        default="llm_ner",
        description="Source tag for detected spans.",
        json_schema_extra=field_ui(
            ui_group="Advanced",
            ui_order=4,
            ui_widget="text",
            ui_advanced=True,
        ),
    )
    skip_overlapping: bool = Field(
        default=False,
        description="Drop new spans that overlap any existing span in the document.",
        json_schema_extra=field_ui(
            ui_group="General",
            ui_order=99,
            ui_widget="switch",
        ),
    )


_SPAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "spans": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "label": {"type": "string"},
                },
                "required": ["text", "label"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["spans"],
    "additionalProperties": False,
}


def _coerce_to_span_items(parsed: Any) -> list[dict[str, Any]]:
    """Pull a list of span dicts out of a tolerant variety of response shapes.

    Accepts both the new ``{"spans": [{"text", "label"}, ...]}`` shape and the
    legacy offset-based shape ``[{"start", "end", "label"}, ...]``.
    """
    if isinstance(parsed, dict):
        parsed = parsed.get("spans", [])
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _parse_llm_response(raw: str) -> list[dict[str, Any]]:
    """Extract a list of span dicts from a raw model response string.

    Used when structured-output decoding is unavailable (e.g. the legacy
    chat-completions path) or when a custom prompt produces fenced JSON.
    """
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}|\[.*\]", cleaned, re.DOTALL)
        if not match:
            logger.warning(
                "Could not parse LLM response as JSON (response length: %d chars)",
                len(cleaned),
            )
            return []
        try:
            parsed = json.loads(match.group())
        except json.JSONDecodeError:
            return []

    return _coerce_to_span_items(parsed)


def _build_offset_spans(
    items: Iterable[dict[str, Any]],
    text_length: int,
    allowed_labels: set[str],
    source: str,
) -> list[EntitySpan]:
    """Legacy path: trust offsets returned directly by the model."""
    spans: list[EntitySpan] = []
    for item in items:
        start = item.get("start")
        end = item.get("end")
        label = item.get("label")
        if (
            isinstance(start, int)
            and isinstance(end, int)
            and isinstance(label, str)
            and label in allowed_labels
            and 0 <= start < end <= text_length
        ):
            spans.append(
                EntitySpan(
                    start=start,
                    end=end,
                    label=label,
                    confidence=item.get("confidence"),
                    source=source,
                )
            )
    return spans


def _locate_text_spans(
    text: str,
    items: Iterable[dict[str, Any]],
    allowed_labels: set[str],
    source: str,
) -> list[EntitySpan]:
    """New path: locate every non-overlapping occurrence of each PHI string.

    Longer strings are matched first so that ``"John Smith"`` wins over a bare
    ``"John"`` when both are returned by the model.
    """
    candidates: list[tuple[str, str, Any]] = []
    for item in items:
        phi_text = item.get("text")
        label = item.get("label")
        if not isinstance(phi_text, str) or not isinstance(label, str):
            continue
        if not phi_text or label not in allowed_labels:
            continue
        candidates.append((phi_text, label, item.get("confidence")))

    candidates.sort(key=lambda c: len(c[0]), reverse=True)

    spans: list[EntitySpan] = []
    occupied: list[tuple[int, int]] = []

    def _overlaps(start: int, end: int) -> bool:
        return any(start < e and end > s for s, e in occupied)

    for phi_text, label, confidence in candidates:
        cursor = 0
        found_any = False
        while True:
            idx = text.find(phi_text, cursor)
            if idx == -1:
                break
            end = idx + len(phi_text)
            if _overlaps(idx, end):
                cursor = idx + 1
                continue
            spans.append(
                EntitySpan(
                    start=idx,
                    end=end,
                    label=label,
                    confidence=confidence,
                    source=source,
                )
            )
            occupied.append((idx, end))
            found_any = True
            cursor = end
        if not found_any:
            logger.info(
                "llm_ner: model-reported PHI %r not found in document text", phi_text
            )

    spans.sort(key=lambda s: (s.start, s.end))
    return spans


def _build_spans(
    items: list[dict[str, Any]],
    text: str,
    allowed_labels: set[str],
    source: str,
) -> list[EntitySpan]:
    """Dispatch to text-locate or offset-trust based on the response shape."""
    if not items:
        return []
    sample = items[0]
    if "text" in sample:
        return _locate_text_spans(text, items, allowed_labels, source)
    if "start" in sample and "end" in sample:
        return _build_offset_spans(items, len(text), allowed_labels, source)
    return []


class LlmNerPipe(ConfigurablePipe):
    """Detector that uses an LLM to identify PHI spans."""

    def __init__(self, config: LlmNerConfig | None = None) -> None:
        self._config = config or LlmNerConfig()
        self._cached_client: Any = None

    @property
    def base_labels(self) -> set[str]:
        return set(self._config.labels)

    @property
    def labels(self) -> set[str]:
        return set(self._config.labels)

    def _resolve_api_key(self) -> str:
        api_key = os.environ.get(self._config.api_key_env, "")
        if not api_key and self._config.api_key_env in {
            "OPENAI_API_KEY",
            "CLINICAL_DEID_OPENAI_API_KEY",
        }:
            from clinical_deid.config import get_settings

            api_key = get_settings().openai_api_key or ""
        if not api_key:
            raise RuntimeError(
                f"LLM NER requires API key in environment variable "
                f"{self._config.api_key_env!r}"
            )
        return api_key

    def _get_client(self) -> Any:
        if self._cached_client is not None:
            return self._cached_client
        from clinical_deid.config import get_settings
        from clinical_deid.synthesis.client import OpenAIResponsesClient

        get_settings().require_external_llm_allowed()
        api_key = self._resolve_api_key()
        self._cached_client = OpenAIResponsesClient(
            model=self._config.model,
            api_key=api_key,
            base_url=self._config.base_url,
        )
        return self._cached_client

    def forward(self, doc: AnnotatedDocument) -> AnnotatedDocument:
        text = doc.document.text
        if not text.strip():
            return doc

        llm_text = text
        if len(text) > self._config.max_text_length:
            llm_text = text[: self._config.max_text_length]
            logger.info(
                "LLM NER: truncated text from %d to %d chars", len(text), len(llm_text)
            )

        template = self._config.prompt_template or _DEFAULT_PROMPT_TEMPLATE
        labels_str = ", ".join(self._config.labels)
        prompt = template.format(text=llm_text, labels=labels_str)

        client = self._get_client()

        reasoning = (
            self._config.reasoning_effort
            if _is_reasoning_model(self._config.model)
            else None
        )
        temperature = (
            self._config.temperature
            if not _is_reasoning_model(self._config.model)
            else None
        )

        try:
            parsed = client.extract_structured(
                prompt,
                schema=_SPAN_SCHEMA,
                schema_name="PhiSpans",
                temperature=temperature,
                reasoning_effort=reasoning,
            )
        except Exception:
            logger.exception("LLM NER call failed")
            return doc

        items = _coerce_to_span_items(parsed) if parsed is not None else []
        if not items and isinstance(parsed, str):
            items = _parse_llm_response(parsed)

        allowed_labels = set(self._config.labels)
        spans = _build_spans(items, llm_text, allowed_labels, self._config.source_name)

        return accumulate_spans(doc, spans, skip_overlapping=self._config.skip_overlapping)
