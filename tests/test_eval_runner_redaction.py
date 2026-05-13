"""Tests for the eval runner — detection-only pipelines (no in-pipeline redaction)."""

from __future__ import annotations

from pypedeid.domain import AnnotatedDocument, Document, EntitySpan
from pypedeid.eval.runner import evaluate_pipeline
from pypedeid.pipes.base import Pipe


class MockDetector(Pipe):
    """Detects PHI at fixed positions for testing."""

    def __init__(self, spans: list[EntitySpan]):
        self._spans = spans

    def forward(self, doc: AnnotatedDocument) -> AnnotatedDocument:
        return doc.with_spans(self._spans)


def _make_gold_doc(text: str, spans: list[EntitySpan]) -> AnnotatedDocument:
    return AnnotatedDocument(
        document=Document(id="test-doc", text=text),
        spans=spans,
    )


def test_evaluate_detection_only_pipeline():
    """Detection-only pipeline with perfect predictions."""
    gold_spans = [EntitySpan(start=8, end=18, label="PATIENT")]
    gold_doc = _make_gold_doc("Patient John Smith was here.", gold_spans)

    detector = MockDetector(gold_spans)
    result = evaluate_pipeline(detector, [gold_doc])

    assert result.overall.strict.f1 == 1.0


def test_evaluate_partial_detection():
    """Pipeline that misses some PHI — partial recall."""
    gold_spans = [
        EntitySpan(start=8, end=18, label="PATIENT"),
        EntitySpan(start=26, end=38, label="PHONE"),
    ]
    gold_doc = _make_gold_doc("Patient John Smith called 555-123-4567.", gold_spans)

    # Detector only finds the name, not the phone
    partial_detector = MockDetector([EntitySpan(start=8, end=18, label="PATIENT")])
    result = evaluate_pipeline(partial_detector, [gold_doc])

    assert result.overall.strict.recall < 1.0
    assert result.overall.strict.precision == 1.0


def test_evaluate_no_spans():
    """Pipeline that finds nothing."""
    gold_spans = [EntitySpan(start=8, end=18, label="PATIENT")]
    gold_doc = _make_gold_doc("Patient John Smith was here.", gold_spans)

    detector = MockDetector([])
    result = evaluate_pipeline(detector, [gold_doc])

    assert result.overall.strict.recall == 0.0
    assert result.overall.strict.f1 == 0.0
