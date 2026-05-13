"""Pre-built pipeline profiles for CLI usage (no database required).

Each profile function returns a plain ``dict`` pipeline config that can be
passed directly to :func:`~pypedeid.pipes.registry.load_pipeline`.

Pipelines only produce spans — redaction/surrogate is applied separately
via ``output_mode`` at the API/CLI layer.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Shipped default whitelist — matches ``data/dictionaries/whitelist/`` file stems.
_DEFAULT_WHITELIST_LABELS: dict[str, Any] = {
    "FIRST_NAME": {
        "enabled": True,
        "remap": None,
        "terms": [],
        "dictionaries": ["male-first-names", "female_first_names"],
    },
    "LAST_NAME": {
        "enabled": True,
        "remap": None,
        "terms": [],
        "dictionaries": ["last_names"],
    },
    "HOSPITAL": {
        "enabled": True,
        "remap": None,
        "terms": [],
        "dictionaries": ["us_hospitals"],
    },
    "LOCATION": {
        "enabled": True,
        "remap": None,
        "terms": [],
        "dictionaries": ["us_cities", "local_places_unambig_v2", "LOCATION__us_states"],
    },
    "STATE": {
        "enabled": True,
        "remap": None,
        "terms": [],
        "dictionaries": ["STATE__us_states"],
    },
}


def fast_profile() -> dict[str, Any]:
    """Regex + whitelist + blacklist + resolve.  ~10 ms, no ML."""
    return {
        "pipes": [
            {"type": "regex_ner"},
            {
                "type": "whitelist",
                "config": {
                    "source_name": "whitelist",
                    "skip_overlapping": False,
                    "labels": _DEFAULT_WHITELIST_LABELS,
                },
            },
            {"type": "blacklist"},
            {"type": "resolve_spans", "config": {"strategy": "longest_non_overlapping"}},
        ],
    }


def balanced_profile() -> dict[str, Any]:
    """Regex + whitelist + presidio (if installed) + resolve.  Falls back to fast."""
    from pypedeid.pipes.registry import registered_pipes

    if "presidio_ner" not in registered_pipes():
        logger.warning(
            "presidio not installed — balanced profile falling back to fast "
            "(install with: pip install '.[presidio]')"
        )
        return fast_profile()

    return {
        "pipes": [
            {"type": "regex_ner"},
            {
                "type": "whitelist",
                "config": {
                    "source_name": "whitelist",
                    "skip_overlapping": False,
                    "labels": _DEFAULT_WHITELIST_LABELS,
                },
            },
            {"type": "presidio_ner"},
            {"type": "blacklist"},
            {"type": "resolve_spans", "config": {"strategy": "longest_non_overlapping"}},
        ],
    }


def accurate_profile() -> dict[str, Any]:
    """Regex + whitelist + presidio + consistency propagation + span resolution.

    Highest quality: chains all detectors, propagates high-confidence
    spans across the document, then resolves overlaps by confidence.
    """
    from pypedeid.pipes.registry import registered_pipes

    if "presidio_ner" not in registered_pipes():
        raise RuntimeError(
            "accurate profile requires presidio — install with: pip install '.[presidio]'"
        )

    return {
        "pipes": [
            {"type": "regex_ner"},
            {
                "type": "whitelist",
                "config": {
                    "source_name": "whitelist",
                    "skip_overlapping": False,
                    "labels": _DEFAULT_WHITELIST_LABELS,
                },
            },
            {"type": "presidio_ner"},
            {"type": "blacklist"},
            {"type": "consistency_propagator", "config": {"min_confidence": 0.7}},
            {"type": "resolve_spans", "config": {"strategy": "max_confidence"}},
        ],
    }


_PROFILE_BUILDERS = {
    "fast": fast_profile,
    "balanced": balanced_profile,
    "accurate": accurate_profile,
}


def get_profile_config(name: str) -> dict[str, Any]:
    """Build a complete pipeline config dict for the named profile."""
    builder = _PROFILE_BUILDERS.get(name)
    if builder is None:
        raise ValueError(f"Unknown profile {name!r}. Choose from: {sorted(_PROFILE_BUILDERS)}")
    return builder()
