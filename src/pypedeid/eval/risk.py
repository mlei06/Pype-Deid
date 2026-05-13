"""Risk-weighted recall and coverage reporting.

This module is now a thin back-compat shim over :mod:`pypedeid.risk`.
Prefer the :class:`~pypedeid.risk.RiskProfile` API directly: construct a
profile (or look one up via :func:`~pypedeid.risk.get_risk_profile`) and
call its :meth:`~pypedeid.risk.RiskProfile.risk_weighted_recall` and
:meth:`~pypedeid.risk.RiskProfile.coverage_report` methods.
"""

from __future__ import annotations

from pypedeid.domain import EntitySpan
from pypedeid.risk import CLINICAL_PHI_RISK


# Backward-compatible module-level values — all derived from CLINICAL_PHI_RISK.

DEFAULT_RISK_WEIGHTS: dict[str, float] = dict(CLINICAL_PHI_RISK.weights)
"""HIPAA clinical-severity weights. Delegates to ``CLINICAL_PHI_RISK.weights``."""

LABEL_TO_HIPAA: dict[str, list[int]] = {
    label: [k for k in keys if isinstance(k, int)]
    for label, keys in CLINICAL_PHI_RISK.label_to_identifiers.items()
}
"""Map of canonical labels to HIPAA identifier numbers."""

HIPAA_IDENTIFIER_NAMES: dict[int, str] = {
    ident.key: ident.name
    for ident in CLINICAL_PHI_RISK.identifiers
    if isinstance(ident.key, int)
}
"""Human-readable names for HIPAA identifiers 1-18."""


def risk_weighted_recall(
    false_negatives: list[EntitySpan],
    gold_spans: list[EntitySpan],
    weights: dict[str, float] | None = None,
) -> float:
    """Recall where each missed span is weighted by its label's risk.

    If *weights* is ``None``, uses the clinical_phi profile's weights.
    """
    if weights is None:
        return CLINICAL_PHI_RISK.risk_weighted_recall(false_negatives, gold_spans)
    # Build an ad-hoc profile for custom weights (preserves historical behavior
    # where unknown labels fell back to 1.0).
    from pypedeid.risk import RiskProfile

    adhoc = RiskProfile(name="adhoc", weights=weights, default_weight=1.0)
    return adhoc.risk_weighted_recall(false_negatives, gold_spans)


def hipaa_coverage_report(
    pipeline_labels: set[str],
    label_to_hipaa: dict[str, list[int]] | None = None,
) -> dict[int, str]:
    """Return ``{hipaa_id: status}`` (``covered``/``partial``/``uncovered``/``n/a``).

    When *label_to_hipaa* is ``None``, uses the clinical_phi profile's mapping.
    """
    if label_to_hipaa is None:
        report = CLINICAL_PHI_RISK.coverage_report(pipeline_labels)
        # Narrow key type for back-compat callers that expect int keys.
        return {k: v for k, v in report.items() if isinstance(k, int)}

    # Custom mapping — build an ad-hoc profile reusing the HIPAA identifier list.
    from pypedeid.risk import RiskProfile

    adhoc = RiskProfile(
        name="adhoc",
        identifiers=CLINICAL_PHI_RISK.identifiers,
        label_to_identifiers={
            label: tuple(ids) for label, ids in label_to_hipaa.items()
        },
    )
    report = adhoc.coverage_report(pipeline_labels)
    return {k: v for k, v in report.items() if isinstance(k, int)}
