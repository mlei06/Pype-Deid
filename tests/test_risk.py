"""Tests for the pluggable RiskProfile abstraction in ``pypedeid.risk``."""

from __future__ import annotations

import pytest

from pypedeid.domain import EntitySpan
from pypedeid.risk import (
    CLINICAL_PHI_RISK,
    GENERIC_PII_RISK,
    CoverageIdentifier,
    RiskProfile,
    default_risk_profile,
    get_risk_profile,
    list_risk_profiles,
    register_risk_profile,
)


def _span(start: int, end: int, label: str) -> EntitySpan:
    return EntitySpan(start=start, end=end, label=label)


def test_weight_for_known_and_unknown() -> None:
    assert CLINICAL_PHI_RISK.weight_for("SSN") == 10.0
    # Unknown label → default_weight (1.0)
    assert CLINICAL_PHI_RISK.weight_for("COMPLETELY_UNKNOWN") == 1.0


def test_risk_weighted_recall_perfect_when_no_misses() -> None:
    gold = [_span(0, 3, "SSN"), _span(10, 13, "DATE")]
    assert CLINICAL_PHI_RISK.risk_weighted_recall([], gold) == 1.0


def test_risk_weighted_recall_all_missed() -> None:
    gold = [_span(0, 3, "SSN")]
    fn = list(gold)
    assert CLINICAL_PHI_RISK.risk_weighted_recall(fn, gold) == 0.0


def test_risk_weighted_recall_weights_by_severity() -> None:
    # SSN has weight 10, AGE has weight 1. Missing AGE hurts less than missing SSN.
    gold = [_span(0, 3, "SSN"), _span(10, 13, "AGE")]
    miss_age = CLINICAL_PHI_RISK.risk_weighted_recall([gold[1]], gold)
    miss_ssn = CLINICAL_PHI_RISK.risk_weighted_recall([gold[0]], gold)
    assert miss_age > miss_ssn


def test_risk_weighted_recall_empty_gold_is_one() -> None:
    assert CLINICAL_PHI_RISK.risk_weighted_recall([], []) == 1.0


def test_coverage_report_all_covered() -> None:
    # A pipeline that emits all HIPAA-covered labels (unrealistic but valid) should
    # have every applicable identifier "covered".
    all_labels = set(CLINICAL_PHI_RISK.label_to_identifiers.keys())
    report = CLINICAL_PHI_RISK.coverage_report(all_labels)
    # HIPAA #17 (photographs) is non-required → n/a regardless of pipeline.
    assert report[17] == "n/a"
    # Identifiers 1-16, 18 should all be "covered" or "partial" (ID covers
    # several IDs but needs the sibling labels to be fully covered).
    statuses = {k: v for k, v in report.items() if k != 17}
    assert "uncovered" not in statuses.values()


def test_coverage_report_empty_pipeline_is_uncovered() -> None:
    report = CLINICAL_PHI_RISK.coverage_report(set())
    assert report[1] == "uncovered"
    assert report[7] == "uncovered"
    assert report[17] == "n/a"


def test_coverage_report_partial() -> None:
    # HIPAA #8 is covered by MRN AND ID. Emitting only MRN → partial (other labels
    # that can cover #8 exist but aren't in the pipeline).
    report = CLINICAL_PHI_RISK.coverage_report({"MRN"})
    assert report[8] == "partial"


def test_identifier_name_hipaa_int_keys() -> None:
    assert CLINICAL_PHI_RISK.identifier_name(1) == "Names"
    assert CLINICAL_PHI_RISK.identifier_name(7) == "Social Security numbers"
    assert CLINICAL_PHI_RISK.identifier_name(17) == "Full-face photographs"


def test_identifier_name_generic_str_keys() -> None:
    assert GENERIC_PII_RISK.identifier_name("names") == "Personal names"
    assert GENERIC_PII_RISK.identifier_name("contact") == "Contact info (email, phone)"
    # Unknown key → str(key)
    assert GENERIC_PII_RISK.identifier_name("nope") == "nope"


def test_generic_pii_profile_uniform_weights() -> None:
    # default_weight applies to every label.
    assert GENERIC_PII_RISK.weight_for("NAME") == 1.0
    assert GENERIC_PII_RISK.weight_for("SSN") == 1.0


def test_generic_pii_coverage_uses_string_keys() -> None:
    report = GENERIC_PII_RISK.coverage_report({"EMAIL", "NAME", "PHONE"})
    assert report["contact"] == "covered"  # both EMAIL and PHONE present
    assert report["names"] == "partial"  # NAME present, ORGANIZATION absent
    assert report["temporal"] == "uncovered"


def test_registry_get_and_list() -> None:
    assert "clinical_phi" in list_risk_profiles()
    assert "generic_pii" in list_risk_profiles()
    assert get_risk_profile("clinical_phi") is CLINICAL_PHI_RISK


def test_registry_unknown_name_error() -> None:
    with pytest.raises(KeyError, match="Known:"):
        get_risk_profile("does_not_exist")


def test_register_risk_profile_roundtrip() -> None:
    profile = RiskProfile(
        name="test_profile_xyz",
        weights={"A": 5.0},
        identifiers=(CoverageIdentifier("thing", "A thing"),),
        label_to_identifiers={"A": ("thing",)},
    )
    register_risk_profile(profile)
    try:
        assert get_risk_profile("test_profile_xyz") is profile
    finally:
        from pypedeid.risk import _REGISTRY  # type: ignore[attr-defined]

        _REGISTRY.pop("test_profile_xyz", None)


def test_default_risk_profile_reads_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from pypedeid.config import reset_settings

    reset_settings()
    assert default_risk_profile() is CLINICAL_PHI_RISK

    monkeypatch.setenv("PYPEDEID_RISK_PROFILE_NAME", "generic_pii")
    reset_settings()
    try:
        assert default_risk_profile() is GENERIC_PII_RISK
    finally:
        reset_settings()


def test_legacy_eval_risk_shim_still_works() -> None:
    """The old module-level API in ``eval/risk.py`` continues to function."""
    from pypedeid.eval.risk import (
        DEFAULT_RISK_WEIGHTS,
        HIPAA_IDENTIFIER_NAMES,
        LABEL_TO_HIPAA,
        hipaa_coverage_report,
        risk_weighted_recall,
    )

    assert DEFAULT_RISK_WEIGHTS["SSN"] == 10.0
    assert HIPAA_IDENTIFIER_NAMES[1] == "Names"
    assert LABEL_TO_HIPAA["MRN"] == [8]

    gold = [_span(0, 3, "SSN")]
    assert risk_weighted_recall([], gold) == 1.0
    assert risk_weighted_recall(gold, gold) == 0.0

    report = hipaa_coverage_report({"MRN"})
    assert report[8] == "partial"
    assert report[17] == "n/a"
