"""Tests for the LLM-NER pipe (text-based extraction + legacy offset fallback)."""

from __future__ import annotations

from typing import Any

import pytest

from pypedeid.domain import AnnotatedDocument, Document
from pypedeid.pipes.llm_ner import (
    LlmNerConfig,
    LlmNerPipe,
    _build_offset_spans,
    _build_spans,
    _coerce_to_span_items,
    _is_reasoning_model,
    _locate_text_spans,
    _parse_llm_response,
)


def _doc(text: str) -> AnnotatedDocument:
    return AnnotatedDocument(document=Document(id="t", text=text), spans=[])


class _FakeClient:
    """In-memory stand-in for OpenAIResponsesClient.

    Records the args it was called with so tests can assert latency-relevant
    knobs (reasoning_effort, temperature) are passed through correctly.
    """

    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    def extract_structured(self, prompt: str, **kwargs: Any) -> Any:
        self.calls.append({"prompt": prompt, **kwargs})
        return self.payload


def _pipe_with_payload(payload: Any, **config_kwargs: Any) -> tuple[LlmNerPipe, _FakeClient]:
    pipe = LlmNerPipe(LlmNerConfig(**config_kwargs))
    fake = _FakeClient(payload)
    pipe._cached_client = fake  # type: ignore[attr-defined]
    return pipe, fake


# ---------- text-based extraction ----------


def test_locate_marks_all_occurrences_of_repeated_phi() -> None:
    text = "Mr. Smith arrived. Smith was admitted. Smith left."
    spans = _locate_text_spans(
        text,
        [{"text": "Smith", "label": "PATIENT"}],
        allowed_labels={"PATIENT"},
        source="llm_ner",
    )
    assert [(s.start, s.end) for s in spans] == [(4, 9), (19, 24), (39, 44)]
    assert all(s.label == "PATIENT" for s in spans)


def test_locate_prefers_longer_match_over_shorter_overlap() -> None:
    text = "Patient John Smith arrived."
    spans = _locate_text_spans(
        text,
        [
            {"text": "John", "label": "PATIENT"},
            {"text": "John Smith", "label": "PATIENT"},
        ],
        allowed_labels={"PATIENT"},
        source="llm_ner",
    )
    assert len(spans) == 1
    assert (spans[0].start, spans[0].end) == (8, 18)


def test_locate_drops_strings_not_present_in_text() -> None:
    text = "Patient arrived today."
    spans = _locate_text_spans(
        text,
        [{"text": "Hallucinated Name", "label": "PATIENT"}],
        allowed_labels={"PATIENT"},
        source="llm_ner",
    )
    assert spans == []


def test_locate_drops_disallowed_labels() -> None:
    text = "Mr. Smith arrived."
    spans = _locate_text_spans(
        text,
        [{"text": "Smith", "label": "BANNED"}],
        allowed_labels={"PATIENT"},
        source="llm_ner",
    )
    assert spans == []


# ---------- legacy offset shape ----------


def test_legacy_offset_response_still_parses() -> None:
    text = "Mr. Smith arrived."
    spans = _build_offset_spans(
        [{"start": 4, "end": 9, "label": "PATIENT"}],
        text_length=len(text),
        allowed_labels={"PATIENT"},
        source="llm_ner",
    )
    assert len(spans) == 1
    assert (spans[0].start, spans[0].end, spans[0].label) == (4, 9, "PATIENT")


def test_build_spans_dispatches_on_response_shape() -> None:
    text = "Mr. Smith arrived."

    text_shape = _build_spans(
        [{"text": "Smith", "label": "PATIENT"}],
        text,
        {"PATIENT"},
        "llm_ner",
    )
    offset_shape = _build_spans(
        [{"start": 4, "end": 9, "label": "PATIENT"}],
        text,
        {"PATIENT"},
        "llm_ner",
    )

    assert (text_shape[0].start, text_shape[0].end) == (4, 9)
    assert (offset_shape[0].start, offset_shape[0].end) == (4, 9)


# ---------- parser tolerance ----------


def test_parse_strips_markdown_fences_and_extracts_spans() -> None:
    raw = '```json\n{"spans": [{"text": "Smith", "label": "PATIENT"}]}\n```'
    items = _parse_llm_response(raw)
    assert items == [{"text": "Smith", "label": "PATIENT"}]


def test_parse_falls_back_to_regex_match_on_garbage_prefix() -> None:
    raw = 'Sure! Here is the JSON:\n{"spans": [{"text": "Smith", "label": "PATIENT"}]}'
    items = _parse_llm_response(raw)
    assert items == [{"text": "Smith", "label": "PATIENT"}]


def test_coerce_accepts_bare_array_for_back_compat() -> None:
    assert _coerce_to_span_items([{"text": "x", "label": "PATIENT"}]) == [
        {"text": "x", "label": "PATIENT"}
    ]
    assert _coerce_to_span_items({"spans": []}) == []
    assert _coerce_to_span_items("not-json") == []


# ---------- pipe wiring ----------


def test_pipe_uses_text_response_to_locate_spans() -> None:
    pipe, _fake = _pipe_with_payload(
        {"spans": [{"text": "Smith", "label": "PATIENT"}]}
    )
    out = pipe.forward(_doc("Mr. Smith arrived."))
    assert [(s.start, s.end, s.label) for s in out.spans] == [(4, 9, "PATIENT")]


def test_pipe_falls_back_to_legacy_offset_response() -> None:
    pipe, _fake = _pipe_with_payload(
        {"spans": [{"start": 4, "end": 9, "label": "PATIENT"}]}
    )
    out = pipe.forward(_doc("Mr. Smith arrived."))
    assert [(s.start, s.end, s.label) for s in out.spans] == [(4, 9, "PATIENT")]


def test_pipe_returns_doc_unchanged_on_client_failure() -> None:
    class _Boom:
        def extract_structured(self, *a: Any, **k: Any) -> Any:
            raise RuntimeError("network down")

    pipe = LlmNerPipe(LlmNerConfig())
    pipe._cached_client = _Boom()  # type: ignore[attr-defined]
    out = pipe.forward(_doc("Mr. Smith arrived."))
    assert out.spans == []


# ---------- reasoning_effort / temperature gating ----------


def test_reasoning_effort_passed_only_for_reasoning_models() -> None:
    pipe, fake = _pipe_with_payload(
        {"spans": []},
        model="gpt-5-mini",
        reasoning_effort="minimal",
    )
    pipe.forward(_doc("note"))
    call = fake.calls[-1]
    assert call["reasoning_effort"] == "minimal"
    assert call["temperature"] is None


def test_temperature_passed_only_for_non_reasoning_models() -> None:
    pipe, fake = _pipe_with_payload(
        {"spans": []},
        model="gpt-4o-mini",
        temperature=0.2,
        reasoning_effort="minimal",
    )
    pipe.forward(_doc("note"))
    call = fake.calls[-1]
    assert call["reasoning_effort"] is None
    assert call["temperature"] == pytest.approx(0.2)


def test_minimal_effort_is_translated_for_gpt_5_1_plus() -> None:
    """gpt-5.1+ rejects 'minimal'; saved configs must keep working."""
    from pypedeid.synthesis.client import _sanitize_reasoning_effort

    assert _sanitize_reasoning_effort("gpt-5.5", "minimal") == "low"
    assert _sanitize_reasoning_effort("gpt-5.5-mini", "minimal") == "low"
    assert _sanitize_reasoning_effort("gpt-5.4", "minimal") == "low"
    assert _sanitize_reasoning_effort("gpt-5.1-nano", "minimal") == "low"
    # Original GPT-5 and o-series still support 'minimal'.
    assert _sanitize_reasoning_effort("gpt-5", "minimal") == "minimal"
    assert _sanitize_reasoning_effort("gpt-5-mini", "minimal") == "minimal"
    assert _sanitize_reasoning_effort("o3", "minimal") == "minimal"
    # Other values pass through untouched.
    assert _sanitize_reasoning_effort("gpt-5.5", "low") == "low"
    assert _sanitize_reasoning_effort("gpt-5.5", "xhigh") == "xhigh"
    assert _sanitize_reasoning_effort("gpt-5.5", None) is None


def test_is_reasoning_model_classification() -> None:
    assert _is_reasoning_model("gpt-5") is True
    assert _is_reasoning_model("gpt-5-mini") is True
    assert _is_reasoning_model("o3") is True
    assert _is_reasoning_model("o4-mini") is True
    assert _is_reasoning_model("gpt-4o-mini") is False
    assert _is_reasoning_model("gpt-4.1") is False
