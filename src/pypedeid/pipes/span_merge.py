"""Shared span merge / resolution strategies.

:class:`ResolveSpans` passes ``[doc.spans]`` — a single group — so these
strategies can resolve overlaps accumulated from any number of upstream detectors.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Literal

from pypedeid.domain import EntitySpan

# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def overlaps(a: EntitySpan, b: EntitySpan) -> bool:
    return a.start < b.end and b.start < a.end


def has_overlap_with_kept(span: EntitySpan, kept: list[EntitySpan]) -> bool:
    """Check if *span* overlaps any span in *kept* (sorted by start).

    Uses the sorted order of *kept* to skip spans that end before ``span.start``
    and stop early once spans start at or after ``span.end``.  This brings amortised
    cost from O(n) per call to O(k) where k is the number of overlapping neighbours.
    """
    for k in kept:
        if k.end <= span.start:
            continue
        if k.start >= span.end:
            break
        return True
    return False


# ---------------------------------------------------------------------------
# Strategies (multi-group)
# ---------------------------------------------------------------------------


def merge_union(span_groups: list[list[EntitySpan]]) -> list[EntitySpan]:
    """Concatenate all spans from every group and sort."""
    out: list[EntitySpan] = []
    for group in span_groups:
        out.extend(group)
    out.sort(key=lambda s: (s.start, s.end, s.label))
    return out


def merge_exact_dedupe(span_groups: list[list[EntitySpan]]) -> list[EntitySpan]:
    """Drop exact duplicate (start, end, label) spans."""
    seen: set[tuple[int, int, str]] = set()
    out: list[EntitySpan] = []
    for group in span_groups:
        for s in group:
            key = (s.start, s.end, s.label)
            if key not in seen:
                seen.add(key)
                out.append(s)
    out.sort(key=lambda s: (s.start, s.end, s.label))
    return out


def merge_consensus(span_groups: list[list[EntitySpan]], threshold: int) -> list[EntitySpan]:
    """Keep spans where >= *threshold* groups have an overlapping same-label span."""
    tagged: list[tuple[EntitySpan, int]] = []
    for gidx, group in enumerate(span_groups):
        for span in group:
            tagged.append((span, gidx))

    kept: list[EntitySpan] = []
    for span, gidx in tagged:
        votes = 0
        for other_idx, other_group in enumerate(span_groups):
            if other_idx == gidx:
                votes += 1
                continue
            for other in other_group:
                if other.label == span.label and overlaps(span, other):
                    votes += 1
                    break
        if votes >= threshold:
            kept.append(span)

    kept.sort(key=lambda s: (s.start, -(s.end - s.start)))
    deduped: list[EntitySpan] = []
    for span in kept:
        if not any(overlaps(span, d) and span.label == d.label for d in deduped):
            deduped.append(span)
    deduped.sort(key=lambda s: (s.start, s.end, s.label))
    return deduped


def merge_max_confidence(span_groups: list[list[EntitySpan]]) -> list[EntitySpan]:
    """Greedily keep highest-confidence spans; skip any overlap with an already kept span.

    Spans with ``confidence=None`` are treated as 1.0 (fully confident),
    since rule-based detectors produce deterministic matches.
    """
    all_spans = [s for group in span_groups for s in group]
    all_spans.sort(key=lambda s: (s.confidence if s.confidence is not None else 1.0), reverse=True)

    kept: list[EntitySpan] = []
    for span in all_spans:
        if not has_overlap_with_kept(span, kept):
            # Insert into sorted position (by start) to maintain order for sweep.
            _insort_by_start(kept, span)

    kept.sort(key=lambda s: (s.start, s.end, s.label))
    return kept


def merge_longest_non_overlapping(span_groups: list[list[EntitySpan]]) -> list[EntitySpan]:
    """Greedily keep longest spans first; skip any overlap with an already kept span (any label)."""
    all_spans = [s for group in span_groups for s in group]
    all_spans.sort(key=lambda s: (s.end - s.start), reverse=True)

    kept: list[EntitySpan] = []
    for span in all_spans:
        if not has_overlap_with_kept(span, kept):
            _insort_by_start(kept, span)

    kept.sort(key=lambda s: (s.start, s.end, s.label))
    return kept


def merge_left_to_right(span_groups: list[list[EntitySpan]]) -> list[EntitySpan]:
    """Greedily keep spans in document order; leftmost span wins on overlap.

    Ties at the same start position are broken by longest span first.
    """
    all_spans = [s for group in span_groups for s in group]
    all_spans.sort(key=lambda s: (s.start, -(s.end - s.start)))

    kept: list[EntitySpan] = []
    for span in all_spans:
        if not has_overlap_with_kept(span, kept):
            _insort_by_start(kept, span)

    kept.sort(key=lambda s: (s.start, s.end, s.label))
    return kept


DEFAULT_LABEL_PRIORITY: list[str] = [
    "NAME", "PATIENT", "FIRST_NAME", "LAST_NAME",
    "SSN", "MRN", "ID",
    "DATE", "DOB",
    "PHONE", "FAX", "EMAIL",
    "ADDRESS", "STREET", "CITY", "STATE", "ZIP", "COUNTRY",
    "HOSPITAL", "ORGANIZATION",
    "AGE", "URL", "IP",
    "DEVICE", "PLATE", "VIN", "ACCOUNT",
]


def merge_label_priority(
    span_groups: list[list[EntitySpan]],
    label_priority: list[str] | None = None,
) -> list[EntitySpan]:
    """Greedily keep spans with the highest-priority label first.

    *label_priority* is an ordered list where index 0 is the most important
    label.  Labels not in the list are assigned lowest priority.  Ties within
    the same priority level are broken by longest span, then leftmost.

    Falls back to :data:`DEFAULT_LABEL_PRIORITY` when *label_priority* is
    ``None`` or empty.
    """
    ranking = label_priority or DEFAULT_LABEL_PRIORITY
    priority_map = {label: i for i, label in enumerate(ranking)}
    default_rank = len(ranking)

    all_spans = [s for group in span_groups for s in group]
    all_spans.sort(key=lambda s: (
        priority_map.get(s.label, default_rank),
        -(s.end - s.start),
        s.start,
    ))

    kept: list[EntitySpan] = []
    for span in all_spans:
        if not has_overlap_with_kept(span, kept):
            _insort_by_start(kept, span)

    kept.sort(key=lambda s: (s.start, s.end, s.label))
    return kept


def _insort_by_start(lst: list[EntitySpan], span: EntitySpan) -> None:
    """Insert *span* into *lst* keeping it sorted by ``start``."""
    lo, hi = 0, len(lst)
    while lo < hi:
        mid = (lo + hi) // 2
        if lst[mid].start < span.start:
            lo = mid + 1
        else:
            hi = mid
    lst.insert(lo, span)


MergeFunc = Callable[[list[list[EntitySpan]]], list[EntitySpan]]
MergeStrategy = (
    Literal[
        "union",
        "exact_dedupe",
        "consensus",
        "max_confidence",
        "longest_non_overlapping",
        "left_to_right",
        "label_priority",
    ]
    | MergeFunc
)


def resolve_merge_strategy(
    strategy: MergeStrategy,
    consensus_threshold: int,
    label_priority: list[str] | None = None,
) -> MergeFunc:
    if callable(strategy) and not isinstance(strategy, str):
        return strategy
    if strategy == "union":
        return merge_union
    if strategy == "exact_dedupe":
        return merge_exact_dedupe
    if strategy == "consensus":
        return lambda groups: merge_consensus(groups, consensus_threshold)
    if strategy == "max_confidence":
        return merge_max_confidence
    if strategy == "longest_non_overlapping":
        return merge_longest_non_overlapping
    if strategy == "left_to_right":
        return merge_left_to_right
    if strategy == "label_priority":
        return lambda groups: merge_label_priority(groups, label_priority)
    raise ValueError(f"Unknown span resolve strategy: {strategy!r}")


def apply_resolve_spans(
    span_groups: list[list[EntitySpan]],
    strategy: MergeStrategy = "union",
    consensus_threshold: int = 2,
    label_priority: list[str] | None = None,
) -> list[EntitySpan]:
    """Run the chosen merge over one or more span lists."""
    merge = resolve_merge_strategy(strategy, consensus_threshold, label_priority)
    return merge(span_groups)


# ---------------------------------------------------------------------------
# Sliding-window / overlapping-segment reconciliation
# ---------------------------------------------------------------------------


def reconcile_overlapping_spans(spans: Iterable[EntitySpan]) -> list[EntitySpan]:
    """Document-level reconciliation for overlapping segmenter outputs.

    Use this when a segmenter produces overlapping segments (e.g. a sliding
    window) and therefore emits duplicate or partial span predictions for the
    same entity across segments. Given a flat list of document-coordinate
    spans, this collapses same-label spans that overlap or are adjacent into
    a single *union* span.

    Why union (and not majority / max-confidence / intersection): in
    de-identification, missing PHI is worse than over-redaction. A union
    keeps every character any segment flagged as PHI, preserving recall at
    the cost of slightly wider spans. Token- and BIO-level reconciliation
    are deliberately avoided — they discard information that sentence- or
    window-level predictors disagree on and are brittle under remapped
    offsets.

    Rules (matches the approved reference implementation):

    * Spans with different labels are **never** merged, even when they
      overlap. They are grouped by label first.
    * Within a label, spans are sorted by (start, end) and swept
      left-to-right. A span joins the current cluster when
      ``span.start <= cluster_end + 1`` (overlap OR immediate adjacency).
    * The merged span is the geometric union:
      ``start = min(starts)``, ``end = max(ends)``.
    * Merged confidence is ``max(confidences)``; ``None`` is treated as 1.0.
    * Output is sorted by (start, end) and has no intra-label overlaps.
      Different-label spans may still overlap in the output.

    The function is deterministic and order-independent: the initial sort
    on ``(label, start, end)`` normalises input ordering before clustering.
    It is agnostic to the segmenter that produced ``spans`` — sliding
    window, sentence, or anything else — and is intended to be the single
    place where overlapping-segment outputs are merged. Callers using
    non-overlapping segmentations (truncate, sentence) do not need to
    invoke it.
    """
    items = sorted(spans, key=lambda s: (s.label, s.start, s.end))
    result: list[EntitySpan] = []

    i = 0
    n = len(items)
    while i < n:
        label = items[i].label
        cluster: list[EntitySpan] = [items[i]]
        cluster_end = items[i].end
        i += 1

        # Grow the cluster while next span is same-label AND overlaps or is
        # immediately adjacent (end+1 == start).
        while (
            i < n
            and items[i].label == label
            and items[i].start <= cluster_end + 1
        ):
            cluster.append(items[i])
            if items[i].end > cluster_end:
                cluster_end = items[i].end
            i += 1

        merged_start = min(s.start for s in cluster)
        merged_end = max(s.end for s in cluster)
        merged_confidence = max(
            (s.confidence if s.confidence is not None else 1.0) for s in cluster
        )
        # Source is metadata, not part of the reconciliation contract;
        # pick the cluster's leading span's source for deterministic output.
        merged_source = cluster[0].source

        result.append(
            EntitySpan(
                start=merged_start,
                end=merged_end,
                label=label,
                confidence=merged_confidence,
                source=merged_source,
            )
        )

    result.sort(key=lambda s: (s.start, s.end, s.label))
    return result
