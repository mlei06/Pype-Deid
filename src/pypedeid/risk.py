"""Risk-profile abstraction — pluggable per-label risk weights and coverage schemes.

A :class:`RiskProfile` pairs three things an evaluation needs:

1. **Risk weights** — per-label floats used by :func:`RiskProfile.risk_weighted_recall`.
2. **Coverage identifiers** — an ordered list of enumerated categories the profile
   wants to see covered (HIPAA's 18 identifiers, an EU GDPR schema, a custom
   compliance checklist, ...).
3. **Label → identifier map** — which labels count as "covering" each identifier.

Two packs are registered out of the box:

- ``clinical_phi`` — HIPAA Safe Harbor with clinical-severity weights. Matches the
  legacy behavior of :mod:`pypedeid.eval.risk`.
- ``generic_pii`` — a minimal general-purpose scheme with uniform weights and a
  small categorical coverage checklist (names, contact, location, id, temporal).

Register custom profiles at startup::

    from pypedeid.risk import RiskProfile, register_risk_profile
    register_risk_profile(RiskProfile(name="my_scheme", ...))

Select the active profile via ``PYPEDEID_RISK_PROFILE_NAME`` or
:func:`get_risk_profile` directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from pypedeid.domain import EntitySpan

IdentifierKey = Union[str, int]


@dataclass(frozen=True)
class CoverageIdentifier:
    """An enumerated category a :class:`RiskProfile` wants to see covered.

    Attributes:
        key: Stable identifier (int for HIPAA, str for named schemes).
        name: Human-readable label, shown in reports and UIs.
        required: If ``False``, the coverage report always reports ``"n/a"``
            (e.g. HIPAA #17 full-face photographs, not detectable in text).
    """

    key: IdentifierKey
    name: str
    required: bool = True


@dataclass(frozen=True)
class RiskProfile:
    """A named bundle of risk weights + coverage scheme.

    Attributes:
        name: Registry key.
        weights: Per-label weight (higher = more important to detect). Labels
            missing from the map fall back to :attr:`default_weight`.
        identifiers: Ordered list of :class:`CoverageIdentifier` the profile tracks.
        label_to_identifiers: Map ``label → identifier keys`` this label covers.
        default_weight: Weight applied to labels not in :attr:`weights`.
        description: Human-readable summary for UIs.
    """

    name: str
    weights: dict[str, float] = field(default_factory=dict)
    identifiers: tuple[CoverageIdentifier, ...] = ()
    label_to_identifiers: dict[str, tuple[IdentifierKey, ...]] = field(default_factory=dict)
    default_weight: float = 1.0
    description: str = ""

    def weight_for(self, label: str) -> float:
        """Return the risk weight for *label*, or :attr:`default_weight`."""
        return self.weights.get(label, self.default_weight)

    def risk_weighted_recall(
        self,
        false_negatives: list[EntitySpan],
        gold_spans: list[EntitySpan],
    ) -> float:
        """Recall weighted by each span's label risk.

        Returns a value in ``[0, 1]`` where ``1.0`` means no weighted misses.
        """
        if not gold_spans:
            return 1.0
        total = sum(self.weight_for(s.label) for s in gold_spans)
        missed = sum(self.weight_for(s.label) for s in false_negatives)
        if total == 0:
            return 1.0
        return max(0.0, 1.0 - missed / total)

    def coverage_report(
        self, pipeline_labels: set[str]
    ) -> dict[IdentifierKey, str]:
        """Return ``{identifier.key: status}`` with ``"covered"``, ``"partial"``, ``"uncovered"``, or ``"n/a"``.

        ``"n/a"`` is used for identifiers marked ``required=False``.
        ``"covered"`` requires *all* labels that can cover the identifier to be
        present in *pipeline_labels*; ``"partial"`` means some but not all.
        """
        covering: dict[IdentifierKey, set[str]] = {}
        for label, ids in self.label_to_identifiers.items():
            for id_key in ids:
                covering.setdefault(id_key, set()).add(label)

        report: dict[IdentifierKey, str] = {}
        for ident in self.identifiers:
            if not ident.required:
                report[ident.key] = "n/a"
                continue
            cover = covering.get(ident.key, set())
            if not cover:
                report[ident.key] = "uncovered"
            elif cover & pipeline_labels:
                report[ident.key] = "covered" if cover <= pipeline_labels else "partial"
            else:
                report[ident.key] = "uncovered"
        return report

    def identifier_name(self, key: IdentifierKey) -> str:
        """Return the human-readable name for *key*, or ``str(key)`` if unknown."""
        for ident in self.identifiers:
            if ident.key == key:
                return ident.name
        return str(key)


# ---------------------------------------------------------------------------
# Built-in packs
# ---------------------------------------------------------------------------

# HIPAA Safe Harbor — severity weights mirror the legacy DEFAULT_RISK_WEIGHTS.
_CLINICAL_PHI_WEIGHTS: dict[str, float] = {
    "SSN": 10.0,
    "SIN": 10.0,
    "MRN": 8.0,
    "BIOMETRIC": 8.0,
    "PATIENT": 7.0,
    "NAME": 6.0,
    "PHONE": 6.0,
    "FAX": 6.0,
    "EMAIL": 6.0,
    "ID": 5.0,
    "IDNUM": 5.0,
    "OHIP": 5.0,
    "ACCOUNT": 5.0,
    "LICENSE": 5.0,
    "VEHICLE_ID": 5.0,
    "DEVICE_ID": 5.0,
    "URL": 4.0,
    "IP_ADDRESS": 4.0,
    "DOCTOR": 4.0,
    "ADDRESS": 4.0,
    "STAFF": 3.0,
    "HCW": 3.0,
    "PERSON": 3.0,
    "DATE": 3.0,
    "DATE_TIME": 3.0,
    "ZIP_CODE": 3.0,
    "POSTAL_CODE": 3.0,
    "CITY": 2.0,
    "HOSPITAL": 2.0,
    "ORGANIZATION": 2.0,
    "LOCATION": 2.0,
    "STATE": 1.0,
    "COUNTRY": 1.0,
    "AGE": 1.0,
}

# HIPAA Safe Harbor identifiers (§164.514(b)(2)) — #17 (photographs) is not
# detectable in text-only data, hence ``required=False``.
_HIPAA_IDENTIFIERS: tuple[CoverageIdentifier, ...] = (
    CoverageIdentifier(1, "Names"),
    CoverageIdentifier(2, "Geographic data (smaller than state)"),
    CoverageIdentifier(3, "Dates (except year)"),
    CoverageIdentifier(4, "Phone numbers"),
    CoverageIdentifier(5, "Fax numbers"),
    CoverageIdentifier(6, "Email addresses"),
    CoverageIdentifier(7, "Social Security numbers"),
    CoverageIdentifier(8, "Medical record numbers"),
    CoverageIdentifier(9, "Health plan beneficiary numbers"),
    CoverageIdentifier(10, "Account numbers"),
    CoverageIdentifier(11, "Certificate/license numbers"),
    CoverageIdentifier(12, "Vehicle identifiers"),
    CoverageIdentifier(13, "Device identifiers"),
    CoverageIdentifier(14, "Web URLs"),
    CoverageIdentifier(15, "IP addresses"),
    CoverageIdentifier(16, "Biometric identifiers"),
    CoverageIdentifier(17, "Full-face photographs", required=False),
    CoverageIdentifier(18, "Any other unique identifying number"),
)

_CLINICAL_PHI_LABEL_TO_IDS: dict[str, tuple[IdentifierKey, ...]] = {
    "NAME": (1,),
    "PATIENT": (1,),
    "DOCTOR": (1,),
    "STAFF": (1,),
    "HCW": (1,),
    "PERSON": (1,),
    "HOSPITAL": (1, 18),
    "ORGANIZATION": (1, 18),
    "LOCATION": (2,),
    "ADDRESS": (2,),
    "CITY": (2,),
    "STATE": (2,),
    "COUNTRY": (2,),
    "ZIP": (2,),
    "ZIP_CODE": (2,),
    "POSTAL_CODE": (2,),
    "DATE": (3,),
    "DATE_TIME": (3,),
    "AGE": (3,),
    "PHONE": (4,),
    "FAX": (5,),
    "EMAIL": (6,),
    "SSN": (7,),
    "SIN": (7,),
    "MRN": (8,),
    "OHIP": (9,),
    "ACCOUNT": (10,),
    "LICENSE": (11,),
    "ID": (8, 9, 10, 11, 18),
    "IDNUM": (18,),
    "VEHICLE_ID": (12,),
    "DEVICE_ID": (13,),
    "URL": (14,),
    "IP_ADDRESS": (15,),
    "BIOMETRIC": (16,),
}

CLINICAL_PHI_RISK = RiskProfile(
    name="clinical_phi",
    weights=_CLINICAL_PHI_WEIGHTS,
    identifiers=_HIPAA_IDENTIFIERS,
    label_to_identifiers=_CLINICAL_PHI_LABEL_TO_IDS,
    description="HIPAA Safe Harbor identifiers with clinical-severity weights.",
)


# Minimal general-purpose PII risk profile. Coverage identifiers are broad
# categories rather than a specific regulatory checklist.
_GENERIC_PII_IDENTIFIERS: tuple[CoverageIdentifier, ...] = (
    CoverageIdentifier("names", "Personal names"),
    CoverageIdentifier("contact", "Contact info (email, phone)"),
    CoverageIdentifier("location", "Locations and addresses"),
    CoverageIdentifier("id", "Identifiers and account numbers"),
    CoverageIdentifier("temporal", "Dates and timestamps"),
    CoverageIdentifier("network", "URLs and network identifiers"),
)

_GENERIC_PII_LABEL_TO_IDS: dict[str, tuple[IdentifierKey, ...]] = {
    "NAME": ("names",),
    "EMAIL": ("contact",),
    "PHONE": ("contact",),
    "ADDRESS": ("location",),
    "LOCATION": ("location",),
    "ORGANIZATION": ("names",),
    "DATE": ("temporal",),
    "ID": ("id",),
    "URL": ("network",),
    "IP_ADDRESS": ("network",),
}

GENERIC_PII_RISK = RiskProfile(
    name="generic_pii",
    weights={},  # uniform weights: every label counts equally
    identifiers=_GENERIC_PII_IDENTIFIERS,
    label_to_identifiers=_GENERIC_PII_LABEL_TO_IDS,
    default_weight=1.0,
    description="Minimal general-purpose PII scheme with category-based coverage.",
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


_REGISTRY: dict[str, RiskProfile] = {
    CLINICAL_PHI_RISK.name: CLINICAL_PHI_RISK,
    GENERIC_PII_RISK.name: GENERIC_PII_RISK,
}


def register_risk_profile(profile: RiskProfile) -> None:
    """Register (or replace) a risk profile by name."""
    _REGISTRY[profile.name] = profile


def get_risk_profile(name: str) -> RiskProfile:
    """Return the profile named *name*; raises ``KeyError`` listing known packs."""
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(
            f"No risk profile {name!r} registered. Known: {sorted(_REGISTRY)}"
        ) from exc


def list_risk_profiles() -> list[str]:
    """Return registered profile names, sorted."""
    return sorted(_REGISTRY)


def default_risk_profile() -> RiskProfile:
    """Return the active profile (``PYPEDEID_RISK_PROFILE_NAME``, default ``clinical_phi``)."""
    from pypedeid.config import get_settings

    return get_risk_profile(get_settings().risk_profile_name)
