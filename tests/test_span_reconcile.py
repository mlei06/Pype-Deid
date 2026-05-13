"""Tests for reconcile_overlapping_spans — sliding-window span reconciliation.

Contract: same-label overlapping or adjacent spans collapse into a union
span; different-label spans never merge; output is deterministic and
order-independent. Used when a segmenter (e.g. sliding window) produces
overlapping segments that emit duplicate / partial predictions.
"""

from __future__ import annotations

import random

from pypedeid.domain import EntitySpan
from pypedeid.pipes.span_merge import reconcile_overlapping_spans


def _span(start: int, end: int, label: str, confidence: float | None = None) -> EntitySpan:
    return EntitySpan(start=start, end=end, label=label, confidence=confidence)


# ---------------------------------------------------------------------------
# Required cases
# ---------------------------------------------------------------------------


def test_duplicate_spans_collapse_into_one():
    # Two windows both predict the exact same (start, end, label).
    spans = [
        _span(10, 20, "NAME", 0.9),
        _span(10, 20, "NAME", 0.8),
    ]
    out = reconcile_overlapping_spans(spans)
    assert len(out) == 1
    assert out[0].start == 10
    assert out[0].end == 20
    assert out[0].label == "NAME"
    assert out[0].confidence == 0.9  # max of inputs


def test_partial_spans_at_window_edges_merge_into_union():
    # Window A sees "John Smi" at [0, 8); window B sees "n Smith" at [3, 10).
    # Union = [0, 10) covering all of "John Smith".
    spans = [
        _span(0, 8, "NAME", 0.7),
        _span(3, 10, "NAME", 0.6),
    ]
    out = reconcile_overlapping_spans(spans)
    assert len(out) == 1
    assert out[0].start == 0
    assert out[0].end == 10
    assert out[0].label == "NAME"
    assert out[0].confidence == 0.7


def test_adjacent_same_label_spans_merge():
    # Adjacency rule: span.start == cluster_end + 1 still merges (end+1).
    # E.g. "John" at [0, 4) and "Smith" at [5, 10); gap of exactly 1.
    spans = [
        _span(0, 4, "NAME"),
        _span(5, 10, "NAME"),
    ]
    out = reconcile_overlapping_spans(spans)
    assert len(out) == 1
    assert out[0].start == 0
    assert out[0].end == 10
    assert out[0].label == "NAME"


def test_non_adjacent_same_label_spans_do_not_merge():
    # Gap of 2 characters (end+2 == start) — must NOT merge.
    spans = [
        _span(0, 4, "NAME"),
        _span(6, 10, "NAME"),
    ]
    out = reconcile_overlapping_spans(spans)
    assert len(out) == 2
    assert (out[0].start, out[0].end) == (0, 4)
    assert (out[1].start, out[1].end) == (6, 10)


def test_overlapping_different_labels_do_not_merge():
    # Same geometry, different labels — both must survive independently.
    spans = [
        _span(5, 15, "NAME", 0.9),
        _span(5, 15, "DOCTOR", 0.8),
        _span(10, 20, "NAME", 0.7),  # overlaps NAME above
    ]
    out = reconcile_overlapping_spans(spans)
    # Expect: merged NAME [5, 20), and DOCTOR [5, 15) untouched.
    labels = sorted((s.label, s.start, s.end) for s in out)
    assert labels == [("DOCTOR", 5, 15), ("NAME", 5, 20)]


def test_input_order_does_not_affect_output():
    base = [
        _span(0, 5, "NAME", 0.9),
        _span(3, 8, "NAME", 0.5),
        _span(20, 25, "DATE", 0.7),
        _span(25, 30, "DATE", 0.6),   # adjacent — should merge
        _span(40, 45, "PHONE", 0.8),
        _span(10, 12, "NAME", 0.4),   # not adjacent to [0,8) — gap 2
    ]
    # Reconcile from original order
    canonical = reconcile_overlapping_spans(base)

    # Shuffle and re-run many times; output must be identical.
    rng = random.Random(12345)
    for _ in range(25):
        shuffled = list(base)
        rng.shuffle(shuffled)
        out = reconcile_overlapping_spans(shuffled)
        assert out == canonical, f"order-dependent output for shuffle: {shuffled}"


def test_single_window_span_passes_through():
    # A span predicted by only one window still appears in the output,
    # with identical bounds/label/confidence.
    spans = [
        _span(100, 110, "MRN", 0.95),
    ]
    out = reconcile_overlapping_spans(spans)
    assert len(out) == 1
    assert out[0].start == 100
    assert out[0].end == 110
    assert out[0].label == "MRN"
    assert out[0].confidence == 0.95


# ---------------------------------------------------------------------------
# Contract edges (deterministic, no-side-effect behaviors)
# ---------------------------------------------------------------------------


def test_empty_input_returns_empty_list():
    assert reconcile_overlapping_spans([]) == []


def test_output_sorted_by_start_end():
    spans = [
        _span(50, 60, "NAME"),
        _span(10, 20, "DATE"),
        _span(20, 30, "NAME"),  # separate from [50,60) — gap 30
    ]
    out = reconcile_overlapping_spans(spans)
    # Sorted ascending by (start, end).
    keys = [(s.start, s.end) for s in out]
    assert keys == sorted(keys)


def test_no_intra_label_overlaps_in_output():
    spans = [
        _span(0, 5, "NAME"),
        _span(3, 10, "NAME"),
        _span(8, 15, "NAME"),
        _span(20, 25, "NAME"),
    ]
    out = reconcile_overlapping_spans(spans)
    # Same-label pairs must be disjoint in output.
    same_label = [s for s in out if s.label == "NAME"]
    for a, b in zip(same_label, same_label[1:]):
        assert a.end < b.start or a.end + 1 <= b.start, (
            f"intra-label overlap/adjacency in output: {a}, {b}"
        )


def test_max_confidence_with_none_treated_as_one():
    # A span with confidence=None (treated as 1.0) should dominate.
    spans = [
        _span(0, 5, "NAME", 0.2),
        _span(0, 5, "NAME", None),
    ]
    out = reconcile_overlapping_spans(spans)
    assert len(out) == 1
    assert out[0].confidence == 1.0


def test_three_way_chain_collapses_to_single_union():
    # Three windows, each picking up part of the same entity; chain merges.
    spans = [
        _span(0, 4, "NAME", 0.5),
        _span(3, 7, "NAME", 0.9),
        _span(6, 10, "NAME", 0.7),
    ]
    out = reconcile_overlapping_spans(spans)
    assert len(out) == 1
    assert out[0].start == 0
    assert out[0].end == 10
    assert out[0].confidence == 0.9


def test_mixed_labels_interleaved_output_is_independent_per_label():
    spans = [
        _span(0, 5, "NAME", 0.9),
        _span(2, 8, "DATE", 0.8),   # overlaps NAME but different label
        _span(4, 9, "NAME", 0.7),   # overlaps NAME — merges
        _span(7, 12, "DATE", 0.6),  # overlaps DATE — merges
    ]
    out = reconcile_overlapping_spans(spans)
    keyed = sorted((s.label, s.start, s.end) for s in out)
    assert keyed == [("DATE", 2, 12), ("NAME", 0, 9)]
