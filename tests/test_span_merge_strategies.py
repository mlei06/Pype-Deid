"""Tests for left_to_right and label_priority span merge strategies."""

from __future__ import annotations

from pypedeid.domain import AnnotatedDocument, Document, EntitySpan
from pypedeid.pipes.combinators import ResolveSpans, ResolveSpansConfig
from pypedeid.pipes.span_merge import (
    DEFAULT_LABEL_PRIORITY,
    apply_resolve_spans,
    merge_label_priority,
    merge_left_to_right,
)


def _spans(*tuples: tuple[int, int, str]) -> list[list[EntitySpan]]:
    """Build a single-group span list from (start, end, label) tuples."""
    return [[EntitySpan(start=s, end=e, label=lbl) for s, e, lbl in tuples]]


def _doc(text: str, spans: list[EntitySpan]) -> AnnotatedDocument:
    return AnnotatedDocument(document=Document(id="d", text=text), spans=spans)


# ---------------------------------------------------------------------------
# merge_left_to_right
# ---------------------------------------------------------------------------


class TestMergeLeftToRight:
    def test_no_overlap_preserves_all(self) -> None:
        groups = _spans((0, 3, "A"), (5, 8, "B"), (10, 12, "C"))
        result = merge_left_to_right(groups)
        assert len(result) == 3

    def test_overlap_leftmost_wins(self) -> None:
        groups = _spans((0, 5, "A"), (3, 8, "B"))
        result = merge_left_to_right(groups)
        assert len(result) == 1
        assert result[0].label == "A"
        assert result[0].start == 0 and result[0].end == 5

    def test_same_start_longest_wins(self) -> None:
        groups = _spans((0, 3, "SHORT"), (0, 8, "LONG"))
        result = merge_left_to_right(groups)
        assert len(result) == 1
        assert result[0].label == "LONG"

    def test_three_way_overlap(self) -> None:
        groups = _spans((0, 5, "A"), (3, 8, "B"), (6, 10, "C"))
        result = merge_left_to_right(groups)
        assert len(result) == 2
        assert result[0].label == "A"
        assert result[1].label == "C"

    def test_empty_input(self) -> None:
        assert merge_left_to_right([[]]) == []
        assert merge_left_to_right([]) == []

    def test_via_apply(self) -> None:
        groups = _spans((0, 5, "A"), (3, 8, "B"))
        result = apply_resolve_spans(groups, strategy="left_to_right")
        assert len(result) == 1
        assert result[0].label == "A"


# ---------------------------------------------------------------------------
# merge_label_priority
# ---------------------------------------------------------------------------


class TestMergeLabelPriority:
    def test_higher_priority_wins(self) -> None:
        groups = _spans((0, 5, "AGE"), (0, 5, "NAME"))
        result = merge_label_priority(groups, label_priority=["NAME", "AGE"])
        assert len(result) == 1
        assert result[0].label == "NAME"

    def test_overlap_priority_beats_position(self) -> None:
        groups = _spans((0, 5, "AGE"), (3, 8, "NAME"))
        result = merge_label_priority(groups, label_priority=["NAME", "AGE"])
        assert len(result) == 1
        assert result[0].label == "NAME"
        assert result[0].start == 3

    def test_same_priority_longest_wins(self) -> None:
        groups = _spans((0, 3, "NAME"), (0, 8, "NAME"))
        result = merge_label_priority(groups, label_priority=["NAME"])
        assert len(result) == 1
        assert result[0].end == 8

    def test_unlisted_label_lowest_priority(self) -> None:
        groups = _spans((0, 5, "UNKNOWN"), (0, 5, "NAME"))
        result = merge_label_priority(groups, label_priority=["NAME"])
        assert len(result) == 1
        assert result[0].label == "NAME"

    def test_no_overlap_preserves_all(self) -> None:
        groups = _spans((0, 3, "NAME"), (5, 8, "AGE"), (10, 12, "DATE"))
        result = merge_label_priority(groups, label_priority=["NAME", "DATE", "AGE"])
        assert len(result) == 3

    def test_default_ranking_used_when_none(self) -> None:
        groups = _spans((0, 5, "AGE"), (0, 5, "NAME"))
        result = merge_label_priority(groups, label_priority=None)
        assert result[0].label == "NAME"
        assert DEFAULT_LABEL_PRIORITY.index("NAME") < DEFAULT_LABEL_PRIORITY.index("AGE")

    def test_default_ranking_used_when_empty(self) -> None:
        groups = _spans((0, 5, "AGE"), (0, 5, "NAME"))
        result = merge_label_priority(groups, label_priority=[])
        assert result[0].label == "NAME"

    def test_empty_input(self) -> None:
        assert merge_label_priority([[]]) == []
        assert merge_label_priority([]) == []

    def test_via_apply(self) -> None:
        groups = _spans((0, 5, "AGE"), (0, 5, "NAME"))
        result = apply_resolve_spans(
            groups,
            strategy="label_priority",
            label_priority=["NAME", "AGE"],
        )
        assert len(result) == 1
        assert result[0].label == "NAME"

    def test_via_apply_default_ranking(self) -> None:
        groups = _spans((0, 5, "AGE"), (0, 5, "NAME"))
        result = apply_resolve_spans(groups, strategy="label_priority")
        assert result[0].label == "NAME"


# ---------------------------------------------------------------------------
# Integration via ResolveSpans pipe
# ---------------------------------------------------------------------------


class TestResolveSpansPipeIntegration:
    def test_left_to_right_pipe(self) -> None:
        text = "John Smith was born 1990-01-01"
        spans = [
            EntitySpan(start=0, end=10, label="NAME"),
            EntitySpan(start=5, end=10, label="LAST_NAME"),
        ]
        pipe = ResolveSpans(ResolveSpansConfig(strategy="left_to_right"))
        out = pipe.forward(_doc(text, spans)).spans
        assert len(out) == 1
        assert out[0].label == "NAME"

    def test_label_priority_pipe_with_custom_ranking(self) -> None:
        text = "John Smith was born 1990-01-01"
        spans = [
            EntitySpan(start=0, end=10, label="ORGANIZATION"),
            EntitySpan(start=0, end=10, label="NAME"),
        ]
        pipe = ResolveSpans(ResolveSpansConfig(
            strategy="label_priority",
            label_priority=["NAME", "ORGANIZATION"],
        ))
        out = pipe.forward(_doc(text, spans)).spans
        assert len(out) == 1
        assert out[0].label == "NAME"

    def test_label_priority_pipe_default_ranking(self) -> None:
        text = "John Smith was born 1990-01-01"
        spans = [
            EntitySpan(start=0, end=10, label="ORGANIZATION"),
            EntitySpan(start=0, end=10, label="NAME"),
        ]
        pipe = ResolveSpans(ResolveSpansConfig(strategy="label_priority"))
        out = pipe.forward(_doc(text, spans)).spans
        assert len(out) == 1
        assert out[0].label == "NAME"
