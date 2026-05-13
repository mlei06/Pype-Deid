"""Tests for risk profile selection in ``evaluate_pipeline`` (settings + explicit profile)."""

from __future__ import annotations

import pytest

from pypedeid.config import reset_settings
from pypedeid.domain import AnnotatedDocument, Document, EntitySpan
from pypedeid.eval.runner import evaluate_pipeline
from pypedeid.pipes.base import Pipe
from pypedeid.risk import CLINICAL_PHI_RISK, GENERIC_PII_RISK, default_risk_profile


# Text length must cover gold spans: [0,3) SSN, [4,8) NAME → len ≥ 8
_GOLD_TEXT = "SSS NNNN"


class _NameOnly(Pipe):
    def forward(self, doc: AnnotatedDocument) -> AnnotatedDocument:
        # Matches gold NAME; gold SSN is a false negative.
        return doc.with_spans([EntitySpan(start=4, end=8, label="NAME")])


def _doc_with_gold(
    *spans: EntitySpan,
) -> AnnotatedDocument:
    return AnnotatedDocument(
        document=Document(id="d1", text=_GOLD_TEXT),
        spans=list(spans),
    )


def test_evaluate_pipeline_default_uses_risk_profile_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``risk_profile`` is omitted, :func:`default_risk_profile` is used (env-configurable)."""
    # Gold: SSN + NAME. Predictor only finds NAME → one FN (SSN).
    gold = _doc_with_gold(
        EntitySpan(start=0, end=3, label="SSN"),
        EntitySpan(start=4, end=8, label="NAME"),
    )
    reset_settings()
    monkeypatch.delenv("PYPEDEID_RISK_PROFILE_NAME", raising=False)
    clinical_rwr = evaluate_pipeline(_NameOnly(), [gold], risk_profile=CLINICAL_PHI_RISK).risk_weighted_recall
    generic_rwr = evaluate_pipeline(_NameOnly(), [gold], risk_profile=GENERIC_PII_RISK).risk_weighted_recall
    assert clinical_rwr != generic_rwr

    reset_settings()
    monkeypatch.setenv("PYPEDEID_RISK_PROFILE_NAME", "generic_pii")
    try:
        assert default_risk_profile() is GENERIC_PII_RISK
        assert (
            evaluate_pipeline(_NameOnly(), [gold]).risk_weighted_recall
            == generic_rwr
        )
    finally:
        reset_settings()


def test_evaluate_pipeline_explicit_risk_profile_wins_over_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit ``risk_profile=`` is not replaced by :func:`default_risk_profile`."""
    gold = _doc_with_gold(
        EntitySpan(start=0, end=3, label="SSN"),
        EntitySpan(start=4, end=8, label="NAME"),
    )
    reset_settings()
    monkeypatch.setenv("PYPEDEID_RISK_PROFILE_NAME", "generic_pii")
    try:
        out = evaluate_pipeline(
            _NameOnly(),
            [gold],
            risk_profile=CLINICAL_PHI_RISK,
        )
        assert out.risk_weighted_recall == evaluate_pipeline(
            _NameOnly(), [gold], risk_profile=CLINICAL_PHI_RISK
        ).risk_weighted_recall
    finally:
        reset_settings()
