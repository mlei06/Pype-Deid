"""Tests for Production UI export line → AnnotatedDocument conversion."""

from __future__ import annotations

import json

import pytest

from pypedeid.domain import AnnotatedDocument
from pypedeid.ingest.production_export_jsonl import (
    production_export_bytes_to_annotated_jsonl_bytes,
    production_line_to_annotated_document,
)


def _minimal_production_line() -> dict:
    return {
        "schema_version": 1,
        "output_type": "annotated",
        "id": "f1",
        "source_label": "L",
        "text": "Hello world",
        "spans": [{"start": 0, "end": 5, "label": "X", "confidence": 0.9, "source": "g"}],
        "resolved": True,
        "metadata": {"dataset_name": "ds", "exported_at": "2024-01-01T00:00:00Z"},
    }


def test_production_line_to_annotated_document() -> None:
    raw = _minimal_production_line()
    doc = production_line_to_annotated_document(raw)
    assert isinstance(doc, AnnotatedDocument)
    assert doc.document.id == "f1"
    assert doc.document.text == "Hello world"
    assert doc.spans[0].label == "X"
    assert doc.spans[0].start == 0
    assert doc.spans[0].end == 5
    assert "export_output_type" in doc.document.metadata
    b = production_export_bytes_to_annotated_jsonl_bytes(
        (json.dumps(raw) + "\n").encode("utf-8")
    )
    line = b.decode("utf-8").strip()
    back = AnnotatedDocument.model_validate_json(line)
    assert back.document.id == doc.document.id
    assert back.spans[0].label == "X"


def test_production_redacted_empty_spans() -> None:
    raw = {
        "schema_version": 1,
        "output_type": "redacted",
        "id": "r1",
        "source_label": "L",
        "text": "Patient [PERSON] visited.",
        "spans": [],
        "resolved": True,
        "metadata": {},
    }
    doc = production_line_to_annotated_document(raw)
    assert doc.spans == []


def test_production_rejects_wrong_schema() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        production_line_to_annotated_document({"schema_version": 2})


def test_production_bytes_empty() -> None:
    with pytest.raises(ValueError, match="no non-empty"):
        production_export_bytes_to_annotated_jsonl_bytes(b"  \n  \n")
