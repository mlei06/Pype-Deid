"""Tests for macro-averaged metrics in evaluate_pipeline."""

from __future__ import annotations

from pypedeid.domain import AnnotatedDocument, Document, EntitySpan
from pypedeid.eval.matching import macro_average, make_match_result
from pypedeid.eval.metrics_json import build_persisted_eval_metrics
from pypedeid.eval.runner import evaluate_pipeline
from pypedeid.pipes.base import Pipe


class _PerfectName(Pipe):
    """Predicts NAME perfectly; never predicts RARE."""

    def forward(self, doc: AnnotatedDocument) -> AnnotatedDocument:
        return doc.with_spans([EntitySpan(start=0, end=4, label="NAME")])


def _doc(text: str, *spans: EntitySpan) -> AnnotatedDocument:
    return AnnotatedDocument(document=Document(id="d1", text=text), spans=list(spans))


def test_macro_average_unweighted_mean():
    """Macro = mean of per-label F1, regardless of support."""
    a = make_match_result(tp=99, fp=1, fn=1)   # high support, near-perfect
    b = make_match_result(tp=0, fp=0, fn=1)    # rare label, missed entirely
    avg = macro_average([a, b])
    # F1 of `a` ≈ 0.99; F1 of `b` = 0.0 → macro F1 ≈ 0.495
    assert abs(avg.f1 - (a.f1 + b.f1) / 2) < 1e-9
    assert avg.label_count == 2


def test_macro_empty_returns_zeros():
    avg = macro_average([])
    assert avg.precision == avg.recall == avg.f1 == 0.0
    assert avg.label_count == 0


def test_evaluate_pipeline_returns_macro_lower_than_micro():
    """Rare-label miss should drag macro F1 below micro F1."""
    # Three NAME golds (all hit) + one RARE gold (always missed).
    gold = _doc(
        "John......RARE",
        EntitySpan(start=0, end=4, label="NAME"),
        EntitySpan(start=10, end=14, label="RARE"),
    )
    result = evaluate_pipeline(_PerfectName(), [gold])

    # Micro: TP=1, FN=1 → F1 = 0.667
    # Macro: NAME F1=1.0, RARE F1=0.0 → mean = 0.5
    assert result.overall.strict.f1 > result.macro.strict.f1
    assert abs(result.macro.strict.f1 - 0.5) < 1e-9
    assert result.macro.strict.label_count == 2


def test_macro_in_persisted_metrics():
    """build_persisted_eval_metrics emits a `macro` block with all three modes."""
    gold = _doc(
        "John......RARE",
        EntitySpan(start=0, end=4, label="NAME"),
        EntitySpan(start=10, end=14, label="RARE"),
    )
    result = evaluate_pipeline(_PerfectName(), [gold])
    metrics = build_persisted_eval_metrics(result, risk_profile_name="clinical_phi")
    assert "macro" in metrics
    assert set(metrics["macro"]) == {"strict", "partial_overlap", "token_level"}
    for mode in ("strict", "partial_overlap", "token_level"):
        block = metrics["macro"][mode]
        assert set(block) == {"precision", "recall", "f1", "label_count"}
        assert block["label_count"] == 2
