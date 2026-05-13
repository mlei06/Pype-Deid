"""Pluggable regex pattern packs for the regex_ner detector.

A :class:`RegexPatternPack` bundles a set of ``label → regex`` patterns under
a single name. Packs let non-clinical callers swap out the default clinical
pattern library without forking the detector.

Built-ins:

- ``clinical_phi`` — HIPAA-oriented patterns over a deliberately compact label
  set: ``DATE``, ``DATE_TIME``, ``AGE``, ``PHONE``, ``EMAIL``, ``ID``, ``SSN``,
  ``URL``, ``IP_ADDRESS``, ``ORGANIZATION``, ``POSTAL_CODE``, ``ADDRESS``.
  Sub-types like MRN/DEA/OHIP/VIN all collapse into ``ID`` because regex alone
  cannot reliably tell them apart.
- ``generic_pii`` — a minimal universal subset: ``EMAIL``, ``PHONE``, ``URL``,
  ``IP_ADDRESS``, ``DATE``, ``SSN``. Safe to use when the clinical label set
  does not apply.

Register custom packs at startup::

    from pypedeid.pipes.regex_ner.packs import RegexPatternPack, register_pattern_pack
    register_pattern_pack(RegexPatternPack(name="my_patterns", patterns={...}))

Packs are looked up by name through :func:`get_pattern_pack` and selected via
``RegexNerConfig.pattern_pack``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RegexPatternPack:
    """A named bundle of ``label → regex`` patterns for the regex_ner detector.

    Attributes:
        name: Registry key.
        patterns: Map of canonical label → regex source string. Patterns are
            compiled with ``re.IGNORECASE`` by the detector; embed ``(?-i:...)``
            if a segment must remain case-sensitive.
        description: Human-readable summary for UIs.
    """

    name: str
    patterns: dict[str, str] = field(default_factory=dict)
    description: str = ""

    def labels(self) -> list[str]:
        """Return the pack's labels in sorted order."""
        return sorted(self.patterns.keys())


_REGISTRY: dict[str, RegexPatternPack] = {}


def register_pattern_pack(pack: RegexPatternPack) -> None:
    """Register (or replace) a regex pattern pack by name."""
    _REGISTRY[pack.name] = pack


def get_pattern_pack(name: str) -> RegexPatternPack:
    """Return the pack named *name*; raises ``KeyError`` listing known packs."""
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(
            f"No regex pattern pack {name!r} registered. Known: {sorted(_REGISTRY)}"
        ) from exc


def list_pattern_packs() -> list[str]:
    """Return registered pack names, sorted."""
    return sorted(_REGISTRY)


def _register_builtin_packs() -> None:
    """Populate the registry with the clinical and generic packs.

    Called lazily from :mod:`pypedeid.pipes.regex_ner.pipe` after the
    module-level pattern strings have been defined (avoids circular imports).
    """
    # Import here to sidestep the pipe.py → packs.py chain at import time.
    from pypedeid.pipes.regex_ner.pipe import _CLINICAL_PHI_PATTERNS

    clinical = RegexPatternPack(
        name="clinical_phi",
        patterns=dict(_CLINICAL_PHI_PATTERNS),
        description="HIPAA-oriented regex patterns for clinical de-identification.",
    )
    register_pattern_pack(clinical)

    # Minimal general-purpose subset. Only includes patterns that emit labels
    # usable across domains (no HOSPITAL, no OHIP, no POSTAL_CODE_CA, etc.).
    generic_labels = {"EMAIL", "PHONE", "URL", "IP_ADDRESS", "DATE", "SSN"}
    generic = RegexPatternPack(
        name="generic_pii",
        patterns={
            label: pat
            for label, pat in _CLINICAL_PHI_PATTERNS.items()
            if label in generic_labels
        },
        description="Universal PII patterns (email, phone, URL, IP, date, SSN).",
    )
    register_pattern_pack(generic)
