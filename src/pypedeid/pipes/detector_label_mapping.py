"""Shared label mapping and span accumulation for detector pipes."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from pypedeid.domain import AnnotatedDocument, EntitySpan
from pypedeid.pipes.ui_schema import field_ui

DETECTOR_LABEL_MAPPING_DESCRIPTION = (
    "Map each base detector label to a new label, or null to drop all spans with that base label. "
    "Labels not listed are left unchanged."
)


def detector_label_mapping_field(**ui: Any) -> Any:
    """Reusable ``label_mapping`` field with optional extra ``ui_*`` overrides."""
    return Field(
        default_factory=dict,
        description=DETECTOR_LABEL_MAPPING_DESCRIPTION,
        json_schema_extra=field_ui(
            ui_group="Output labels",
            ui_widget="label_space",
            ui_allow_custom_labels=False,
            **ui,
        ),
    )


DETECTOR_LABEL_MAPPING = detector_label_mapping_field()


def remap_span_labels(
    spans: list[EntitySpan],
    mapping: dict[str, str | None],
    *,
    drop_unmapped: bool = False,
) -> list[EntitySpan]:
    """Single primitive for span-label remap.

    - Key present with non-null value → relabel.
    - Key present with null value → drop the span.
    - Key absent → kept as-is, unless *drop_unmapped* is True (then dropped).
    """
    if not mapping and not drop_unmapped:
        return spans
    out: list[EntitySpan] = []
    for s in spans:
        if s.label in mapping:
            new_label = mapping[s.label]
            if new_label is None:
                continue
            out.append(s.model_copy(update={"label": new_label}))
        elif not drop_unmapped:
            out.append(s)
    return out


def remap_label_set(
    labels: set[str] | frozenset[str],
    mapping: dict[str, str | None],
    *,
    drop_unmapped: bool = False,
) -> set[str]:
    """Set-valued twin of :func:`remap_span_labels` — the symbolic label transform."""
    if not mapping and not drop_unmapped:
        return set(labels)
    out: set[str] = set()
    for lab in labels:
        if lab in mapping:
            v = mapping[lab]
            if v is not None:
                out.add(v)
        elif not drop_unmapped:
            out.add(lab)
    return out


def apply_detector_label_mapping(
    spans: list[EntitySpan],
    mapping: dict[str, str | None],
) -> list[EntitySpan]:
    """Apply *mapping* to span labels; null values remove the span.

    The active :func:`default_label_space` is applied at **inference** API
    ``process_single`` — not here — so ad-hoc remaps (e.g. ``PHONE`` → ``TEL``)
    are preserved through the pipe chain. Eval compares raw span labels.
    """
    return remap_span_labels(spans, mapping, drop_unmapped=False)


def accumulate_spans(
    doc: AnnotatedDocument,
    new_spans: list[EntitySpan],
    skip_overlapping: bool = False,
) -> AnnotatedDocument:
    """Return *doc* with existing spans plus *new_spans* accumulated.

    If *skip_overlapping* is True, new spans that overlap any existing
    span in ``doc.spans`` are silently dropped.
    """
    existing = list(doc.spans)
    if skip_overlapping and existing:
        from pypedeid.pipes.span_merge import has_overlap_with_kept

        sorted_existing = sorted(existing, key=lambda s: s.start)
        kept_new = [
            s for s in new_spans if not has_overlap_with_kept(s, sorted_existing)
        ]
    else:
        kept_new = new_spans
    combined = existing + kept_new
    combined.sort(key=lambda s: (s.start, s.end, s.label))
    return doc.with_spans(combined)


def effective_detector_labels(
    base_labels: set[str],
    mapping: dict[str, str | None],
) -> set[str]:
    """Labels that can appear after applying *mapping* to spans whose base labels are in *base_labels*."""
    return remap_label_set(base_labels, mapping, drop_unmapped=False)
