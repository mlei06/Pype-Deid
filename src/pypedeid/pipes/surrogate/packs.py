"""Pluggable surrogate strategy packs.

A :class:`SurrogatePack` is a named map of canonical label → strategy name.
Strategy names are understood by :class:`~pypedeid.pipes.surrogate.strategies.SurrogateGenerator`
(``"Name"``, ``"Email"``, ``"Phone"``, ``"Date"``, ``"ID"``, ``"Address"``,
``"Postal Code"``, ``"Organization"``, ``"Age"``, ``"Country"``, ``"State"``,
``"URL"``).

Two built-in packs ship:

- ``clinical_phi`` — maps the clinical label set to surrogate strategies.
- ``generic_pii`` — covers the universal labels only (NAME, EMAIL, PHONE,
  ADDRESS, DATE, ID, LOCATION, ORGANIZATION, URL).

Register custom packs via :func:`register_surrogate_pack`. Pack selection
happens through ``SurrogateConfig.strategy_pack``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SurrogatePack:
    """A named bundle of ``label → surrogate strategy`` mappings.

    Attributes:
        name: Registry key.
        label_to_strategy: Map of canonical label → strategy name. The strategy
            name must be one of the values understood by
            :meth:`~pypedeid.pipes.surrogate.strategies.SurrogateGenerator._generate`.
        description: Human-readable summary for UIs.
    """

    name: str
    label_to_strategy: dict[str, str] = field(default_factory=dict)
    description: str = ""

    def strategies_to_labels(self) -> dict[str, list[str]]:
        """Return the inverse map ``strategy -> [labels]`` (for UI/legacy consumers)."""
        out: dict[str, list[str]] = {}
        for label, strategy in self.label_to_strategy.items():
            out.setdefault(strategy, []).append(label)
        for labels in out.values():
            labels.sort()
        return out


# The clinical pack covers every label in the HIPAA / clinical set that has a
# reasonable fake equivalent.
_CLINICAL_PHI_LABEL_TO_STRATEGY: dict[str, str] = {
    # Names
    "NAME": "Name",
    "PATIENT": "Name",
    "PERSON": "Name",
    "STAFF": "Name",
    "HCW": "Name",
    "DOCTOR": "Name",
    "FIRST_NAME": "Name",
    "LAST_NAME": "Name",
    "FIRSTNAME": "Name",
    "LASTNAME": "Name",
    "FULL_NAME": "Name",
    "FULLNAME": "Name",
    "USERNAME": "Name",
    # Dates
    "DATE": "Date",
    "DATE_TIME": "Date",
    # Phone/Fax
    "PHONE": "Phone",
    "PHONE_NUMBER": "Phone",
    "FAX": "Phone",
    # Email
    "EMAIL": "Email",
    "EMAIL_ADDRESS": "Email",
    # Identifiers
    "ID": "ID",
    "MRN": "ID",
    "SSN": "ID",
    "SIN": "ID",
    "OHIP": "ID",
    "IDNUM": "ID",
    # Addresses
    "LOCATION": "Address",
    "ADDRESS": "Address",
    "LOCATION_OTHER": "Address",
    # Postal
    "POSTAL_CODE": "Postal Code",
    "POSTAL_CODE_CA": "Postal Code",
    "ZIP_CODE": "Postal Code",
    "ZIP_CODE_US": "Postal Code",
    # Organizations
    "HOSPITAL": "Organization",
    "ORGANIZATION": "Organization",
    # Misc
    "AGE": "Age",
    "COUNTRY": "Country",
    "STATE": "State",
    "URL": "URL",
}

CLINICAL_PHI_SURROGATE = SurrogatePack(
    name="clinical_phi",
    label_to_strategy=_CLINICAL_PHI_LABEL_TO_STRATEGY,
    description="Clinical/HIPAA labels mapped to realistic fake-data strategies.",
)


# Minimal general-purpose pack — only universal labels.
_GENERIC_PII_LABEL_TO_STRATEGY: dict[str, str] = {
    "NAME": "Name",
    "EMAIL": "Email",
    "PHONE": "Phone",
    "ADDRESS": "Address",
    "DATE": "Date",
    "ID": "ID",
    "LOCATION": "Address",
    "ORGANIZATION": "Organization",
    "URL": "URL",
}

GENERIC_PII_SURROGATE = SurrogatePack(
    name="generic_pii",
    label_to_strategy=_GENERIC_PII_LABEL_TO_STRATEGY,
    description="Universal PII labels mapped to surrogate strategies.",
)


_REGISTRY: dict[str, SurrogatePack] = {
    CLINICAL_PHI_SURROGATE.name: CLINICAL_PHI_SURROGATE,
    GENERIC_PII_SURROGATE.name: GENERIC_PII_SURROGATE,
}


def register_surrogate_pack(pack: SurrogatePack) -> None:
    """Register (or replace) a surrogate pack by name."""
    _REGISTRY[pack.name] = pack


def get_surrogate_pack(name: str) -> SurrogatePack:
    """Return the surrogate pack named *name*; raises ``KeyError`` listing known packs."""
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(
            f"No surrogate pack {name!r} registered. Known: {sorted(_REGISTRY)}"
        ) from exc


def list_surrogate_packs() -> list[str]:
    """Return registered pack names, sorted."""
    return sorted(_REGISTRY)
