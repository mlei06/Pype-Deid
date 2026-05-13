"""Label-space abstraction — the pluggable canonical-label source of truth.

A :class:`LabelSpace` pairs a set of canonical entity labels with an alias table
and a fallback label. Detectors and pipes operate on plain label strings; the
active label space is the reference schema that the platform normalizes against
when translating external labels (e.g. Presidio entity names, upstream NER tags)
into canonical ones.

This module ships two built-in packs:

- ``clinical_phi`` — HIPAA Safe Harbor identifiers plus clinical additions.
- ``generic_pii`` — a small general-purpose PII label set (NAME, EMAIL, PHONE,
  ADDRESS, DATE, ID, LOCATION, ORGANIZATION, URL, IP_ADDRESS, OTHER). Useful as
  a minimal starting point when clinical labels are not appropriate.

Register additional packs at application startup::

    from pypedeid.labels import LabelSpace, register_label_space
    register_label_space(LabelSpace(name="financial_pii", labels=(...), ...))

Then select it via ``PYPEDEID_LABEL_SPACE_NAME`` or by calling :func:`get_label_space` directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pypedeid.domain import EntitySpan


@dataclass(frozen=True)
class LabelSpace:
    """A named set of canonical entity labels plus aliases and a fallback.

    Attributes:
        name: Identifier used in settings and API responses.
        labels: Canonical label strings, in the order a pack author cares about.
        aliases: Map from external/raw label → canonical label. Normalization
            also lowercases and replaces spaces with underscores before lookup.
        fallback: Label returned by :meth:`normalize` when no canonical match
            exists. Must be one of ``labels`` (or the empty string to signal
            "raise on unknown").
        description: Human-readable summary for UIs.
    """

    name: str
    labels: tuple[str, ...]
    aliases: dict[str, str] = field(default_factory=dict)
    fallback: str = "OTHER"
    description: str = ""

    def __post_init__(self) -> None:
        label_set = set(self.labels)
        bad_targets = sorted(v for v in self.aliases.values() if v not in label_set)
        if bad_targets:
            raise ValueError(
                f"LabelSpace {self.name!r} alias targets not in labels: {bad_targets}"
            )
        if self.fallback and self.fallback not in label_set:
            raise ValueError(
                f"LabelSpace {self.name!r} fallback {self.fallback!r} is not in labels"
            )

    def normalize(self, raw: str) -> str:
        """Map *raw* to a canonical label, or return ``fallback`` if unknown.

        Matching is case-insensitive and treats spaces and hyphens as underscores,
        so ``"Phone Number"``, ``"phone-number"``, and ``"PHONE_NUMBER"`` all
        resolve identically through the alias table.
        """
        key = raw.upper().replace(" ", "_").replace("-", "_")
        if key in self.labels:
            return key
        if key in self.aliases:
            return self.aliases[key]
        return self.fallback

    def values(self) -> list[str]:
        """Return canonical labels as a list, preserving declaration order."""
        return list(self.labels)

    def __contains__(self, raw: str) -> bool:
        key = raw.upper().replace(" ", "_").replace("-", "_") if isinstance(raw, str) else raw
        return key in self.labels or key in self.aliases


# ---------------------------------------------------------------------------
# Built-in packs
# ---------------------------------------------------------------------------

# Clinical / HIPAA Safe Harbor pack.
CLINICAL_PHI_LABELS: tuple[str, ...] = (
    # HIPAA #1 — Names
    "NAME", "FIRST_NAME", "LAST_NAME", "PATIENT", "DOCTOR", "STAFF", "HCW",
    # HIPAA #2 — Geographic
    "ADDRESS", "LOCATION", "CITY", "STATE", "COUNTRY", "ZIP_CODE", "POSTAL_CODE",
    # HIPAA #3 — Dates
    "DATE", "DATE_TIME",
    # HIPAA #4-5 — Phone / Fax
    "PHONE",
    "TELEPHONE",  # alternate canonical; pipe label_mapper may emit this name
    "FAX",
    # HIPAA #6 — Email
    "EMAIL",
    # HIPAA #7 — SSN
    "SSN",
    # HIPAA #8 — MRN
    "MRN",
    # HIPAA #9-11 — Beneficiary / Account / License
    "ID", "ACCOUNT", "LICENSE",
    # HIPAA #12-13 — Vehicle / Device
    "VEHICLE_ID", "DEVICE_ID",
    # HIPAA #14-15 — Web / IP
    "URL", "IP_ADDRESS",
    # HIPAA #16 — Biometric
    "BIOMETRIC",
    # HIPAA #17 — Photos (included for schema completeness; not text-detectable)
    "PHOTO",
    # Clinical / practical additions
    "AGE", "ORGANIZATION", "HOSPITAL", "IDNUM", "OHIP", "SIN", "PERSON",
    # Catch-all
    "OTHER",
)

CLINICAL_PHI_ALIASES: dict[str, str] = {
    "PHONE_NUMBER": "PHONE",
    "EMAIL_ADDRESS": "EMAIL",
    "LOCATION_OTHER": "LOCATION",
    "POSTAL_CODE_CA": "POSTAL_CODE",
    "ZIP_CODE_US": "ZIP_CODE",
    "ZIP": "ZIP_CODE",
    "FIRSTNAME": "FIRST_NAME",
    "LASTNAME": "LAST_NAME",
    "FULLNAME": "NAME",
    "FULL_NAME": "NAME",
    "DATE_OF_BIRTH": "DATE",
    "DOB": "DATE",
    "STREET_ADDRESS": "ADDRESS",
    "MEDICAL_RECORD": "MRN",
    "SOCIAL_SECURITY": "SSN",
}

CLINICAL_PHI = LabelSpace(
    name="clinical_phi",
    labels=CLINICAL_PHI_LABELS,
    aliases=CLINICAL_PHI_ALIASES,
    fallback="OTHER",
    description="HIPAA Safe Harbor identifiers plus common clinical additions.",
)


# A minimal general-purpose PII pack — proves the abstraction and gives
# non-clinical callers a ready-made starting point.
GENERIC_PII_LABELS: tuple[str, ...] = (
    "NAME", "EMAIL", "PHONE", "ADDRESS", "DATE", "ID",
    "LOCATION", "ORGANIZATION", "URL", "IP_ADDRESS", "OTHER",
)

GENERIC_PII_ALIASES: dict[str, str] = {
    "PHONE_NUMBER": "PHONE",
    "EMAIL_ADDRESS": "EMAIL",
    "STREET_ADDRESS": "ADDRESS",
    "FULL_NAME": "NAME",
    "PERSON": "NAME",
    "IP": "IP_ADDRESS",
}

GENERIC_PII = LabelSpace(
    name="generic_pii",
    labels=GENERIC_PII_LABELS,
    aliases=GENERIC_PII_ALIASES,
    fallback="OTHER",
    description="Minimal general-purpose PII labels for non-clinical use.",
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


_REGISTRY: dict[str, LabelSpace] = {
    CLINICAL_PHI.name: CLINICAL_PHI,
    GENERIC_PII.name: GENERIC_PII,
}


def register_label_space(space: LabelSpace) -> None:
    """Register (or replace) a label space by name."""
    _REGISTRY[space.name] = space


def get_label_space(name: str) -> LabelSpace:
    """Return the label space named *name*.

    Raises ``KeyError`` with a list of known packs if the name is unregistered.
    """
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(
            f"No label space {name!r} registered. Known: {sorted(_REGISTRY)}"
        ) from exc


def list_label_spaces() -> list[str]:
    """Return the names of all registered label spaces, sorted."""
    return sorted(_REGISTRY)


def default_label_space() -> LabelSpace:
    """Return the active label space (``PYPEDEID_LABEL_SPACE_NAME``, default ``clinical_phi``)."""
    from pypedeid.config import get_settings

    return get_label_space(get_settings().label_space_name)


def normalize_entity_spans(spans: list[EntitySpan]) -> list[EntitySpan]:
    """Map each span's ``label`` through :func:`default_label_space` (alias table + fallback).

    Used for inference API responses (``process_single``), not for evaluation
    (eval compares raw gold vs predicted labels).
    """
    space = default_label_space()
    return [s.model_copy(update={"label": space.normalize(s.label)}) for s in spans]
