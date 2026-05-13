"""Tests for the pluggable LabelSpace abstraction in ``pypedeid.labels``."""

from __future__ import annotations

import pytest

from pypedeid.labels import (
    CLINICAL_PHI,
    GENERIC_PII,
    LabelSpace,
    default_label_space,
    get_label_space,
    list_label_spaces,
    register_label_space,
)


def test_normalize_direct_match() -> None:
    assert CLINICAL_PHI.normalize("PHONE") == "PHONE"
    assert CLINICAL_PHI.normalize("TELEPHONE") == "TELEPHONE"  # label_mapper + API normalize
    assert CLINICAL_PHI.normalize("DATE") == "DATE"


def test_normalize_case_insensitive_and_separators() -> None:
    assert CLINICAL_PHI.normalize("phone") == "PHONE"
    assert CLINICAL_PHI.normalize("Phone Number") == "PHONE"
    assert CLINICAL_PHI.normalize("phone-number") == "PHONE"


def test_normalize_alias_mapping() -> None:
    assert CLINICAL_PHI.normalize("PHONE_NUMBER") == "PHONE"
    assert CLINICAL_PHI.normalize("EMAIL_ADDRESS") == "EMAIL"
    assert CLINICAL_PHI.normalize("DOB") == "DATE"
    assert CLINICAL_PHI.normalize("STREET_ADDRESS") == "ADDRESS"


def test_normalize_unknown_returns_fallback() -> None:
    assert CLINICAL_PHI.normalize("COMPLETELY_UNKNOWN") == "OTHER"
    assert GENERIC_PII.normalize("NOT_A_REAL_LABEL") == "OTHER"


def test_contains_check_uses_aliases() -> None:
    assert "PHONE" in CLINICAL_PHI
    assert "TELEPHONE" in CLINICAL_PHI
    assert "PHONE_NUMBER" in CLINICAL_PHI  # alias
    assert "phone number" in CLINICAL_PHI  # normalized form
    assert "COMPLETELY_UNKNOWN" not in CLINICAL_PHI


def test_values_preserves_declaration_order() -> None:
    vals = CLINICAL_PHI.values()
    assert isinstance(vals, list)
    assert vals[0] == "NAME"
    assert "OTHER" in vals


def test_invalid_alias_target_raises() -> None:
    with pytest.raises(ValueError, match="alias targets not in labels"):
        LabelSpace(
            name="bad",
            labels=("A", "B"),
            aliases={"X": "NOT_A_LABEL"},
            fallback="A",
        )


def test_invalid_fallback_raises() -> None:
    with pytest.raises(ValueError, match="fallback"):
        LabelSpace(
            name="bad",
            labels=("A", "B"),
            fallback="NOT_IN_LABELS",
        )


def test_registry_get_and_list() -> None:
    assert "clinical_phi" in list_label_spaces()
    assert "generic_pii" in list_label_spaces()
    assert get_label_space("clinical_phi") is CLINICAL_PHI


def test_registry_unknown_name_error_lists_known() -> None:
    with pytest.raises(KeyError, match="Known:"):
        get_label_space("does_not_exist")


def test_register_label_space_roundtrip() -> None:
    space = LabelSpace(name="test_pack_xyz", labels=("A", "B"), fallback="B")
    register_label_space(space)
    try:
        assert get_label_space("test_pack_xyz") is space
    finally:
        from pypedeid.labels import _REGISTRY  # type: ignore[attr-defined]

        _REGISTRY.pop("test_pack_xyz", None)


def test_default_label_space_reads_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from pypedeid.config import reset_settings

    reset_settings()
    assert default_label_space() is CLINICAL_PHI

    monkeypatch.setenv("PYPEDEID_LABEL_SPACE_NAME", "generic_pii")
    reset_settings()
    try:
        assert default_label_space() is GENERIC_PII
    finally:
        reset_settings()


def test_clinical_phi_normalize_matches_static_aliases() -> None:
    """Alias table stays consistent with common upstream tag names."""
    assert CLINICAL_PHI.normalize("PHONE_NUMBER") == "PHONE"
    assert CLINICAL_PHI.normalize("dob") == "DATE"
    assert CLINICAL_PHI.normalize("nope_lbl_xyz") == "OTHER"
