"""Tests for the regex pattern and surrogate strategy pack registries."""

from __future__ import annotations

import pytest

from pypedeid.pipes.regex_ner.packs import (
    RegexPatternPack,
    get_pattern_pack,
    list_pattern_packs,
    register_pattern_pack,
)
from pypedeid.pipes.surrogate.packs import (
    CLINICAL_PHI_SURROGATE,
    GENERIC_PII_SURROGATE,
    SurrogatePack,
    get_surrogate_pack,
    list_surrogate_packs,
    register_surrogate_pack,
)


def test_regex_pack_registry_contains_builtins() -> None:
    assert "clinical_phi" in list_pattern_packs()
    assert "generic_pii" in list_pattern_packs()


def test_regex_pack_clinical_has_consolidated_labels() -> None:
    pack = get_pattern_pack("clinical_phi")
    # The pack ships a deliberately compact set of labels — sub-types like
    # MRN/DEA/OHIP collapse into ``ID`` because regex alone cannot reliably
    # tell them apart.
    assert set(pack.patterns) == {
        "ADDRESS", "AGE", "DATE", "DATE_TIME", "EMAIL", "ID",
        "IP_ADDRESS", "ORGANIZATION", "PHONE", "POSTAL_CODE", "SSN", "URL",
    }


def test_regex_pack_generic_is_universal_subset() -> None:
    generic = get_pattern_pack("generic_pii")
    clinical = get_pattern_pack("clinical_phi")
    assert set(generic.patterns) <= set(clinical.patterns)
    # Must not contain clinical-specific labels.
    assert "ID" not in generic.patterns
    assert "ORGANIZATION" not in generic.patterns
    assert "ADDRESS" not in generic.patterns
    # But must cover universal labels.
    assert set(generic.patterns) == {"EMAIL", "PHONE", "URL", "DATE", "IP_ADDRESS", "SSN"}


def test_regex_pack_register_roundtrip() -> None:
    pack = RegexPatternPack(name="test_pattern_pack_xyz", patterns={"A": r"\bfoo\b"})
    register_pattern_pack(pack)
    try:
        assert get_pattern_pack("test_pattern_pack_xyz") is pack
    finally:
        from pypedeid.pipes.regex_ner.packs import _REGISTRY  # type: ignore[attr-defined]

        _REGISTRY.pop("test_pattern_pack_xyz", None)


def test_regex_pack_unknown_name_error() -> None:
    with pytest.raises(KeyError, match="Known:"):
        get_pattern_pack("does_not_exist")


def test_regex_pipe_respects_pattern_pack() -> None:
    """Selecting the generic_pii pack means clinical-only labels don't fire."""
    from pypedeid.pipes.regex_ner import RegexNerConfig, RegexNerPipe

    clinical_cfg = RegexNerConfig(pattern_pack="clinical_phi")
    generic_cfg = RegexNerConfig(pattern_pack="generic_pii")

    clinical_pipe = RegexNerPipe(clinical_cfg)
    generic_pipe = RegexNerPipe(generic_cfg)

    assert "ID" in clinical_pipe.base_labels
    assert "ORGANIZATION" in clinical_pipe.base_labels
    assert "ID" not in generic_pipe.base_labels
    assert "ORGANIZATION" not in generic_pipe.base_labels
    # Email is common to both.
    assert "EMAIL" in clinical_pipe.base_labels
    assert "EMAIL" in generic_pipe.base_labels


def test_surrogate_pack_registry_contains_builtins() -> None:
    assert "clinical_phi" in list_surrogate_packs()
    assert "generic_pii" in list_surrogate_packs()


def test_surrogate_pack_clinical_covers_clinical_labels() -> None:
    pack = get_surrogate_pack("clinical_phi")
    assert pack.label_to_strategy["PATIENT"] == "Name"
    assert pack.label_to_strategy["MRN"] == "ID"
    # POSTAL_CODE (the consolidated label emitted by the regex pack) and the
    # legacy CA/US aliases all map to the same surrogate strategy.
    assert pack.label_to_strategy["POSTAL_CODE"] == "Postal Code"
    assert pack.label_to_strategy["POSTAL_CODE_CA"] == "Postal Code"
    assert pack.label_to_strategy["ZIP_CODE"] == "Postal Code"
    assert pack.label_to_strategy["HOSPITAL"] == "Organization"


def test_surrogate_pack_generic_is_universal() -> None:
    pack = get_surrogate_pack("generic_pii")
    # Universal labels present; clinical-only absent.
    assert "MRN" not in pack.label_to_strategy
    assert "HOSPITAL" not in pack.label_to_strategy
    assert pack.label_to_strategy["NAME"] == "Name"
    assert pack.label_to_strategy["EMAIL"] == "Email"


def test_surrogate_pack_strategies_to_labels_inverse() -> None:
    inverse = CLINICAL_PHI_SURROGATE.strategies_to_labels()
    assert "Name" in inverse
    assert "PATIENT" in inverse["Name"]
    # Must be sorted within each strategy.
    for labels in inverse.values():
        assert labels == sorted(labels)


def test_surrogate_pack_register_roundtrip() -> None:
    pack = SurrogatePack(name="test_surrogate_xyz", label_to_strategy={"FOO": "Name"})
    register_surrogate_pack(pack)
    try:
        assert get_surrogate_pack("test_surrogate_xyz") is pack
    finally:
        from pypedeid.pipes.surrogate.packs import _REGISTRY  # type: ignore[attr-defined]

        _REGISTRY.pop("test_surrogate_xyz", None)


def test_surrogate_generator_uses_provided_pack() -> None:
    from pypedeid.pipes.surrogate.strategies import SurrogateGenerator

    # Generic pack doesn't have MRN → falls through to the mask fallback.
    gen = SurrogateGenerator(
        seed=42,
        consistency=True,
        label_to_strategy=GENERIC_PII_SURROGATE.label_to_strategy,
    )
    replaced = gen.replace("MRN", "ABC12345")
    assert replaced == "*" * len("ABC12345")

    # But a known generic label produces a Faker-backed value.
    email_replaced = gen.replace("EMAIL", "x@y.com")
    assert "@" in email_replaced
