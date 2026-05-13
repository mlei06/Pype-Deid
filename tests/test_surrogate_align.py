"""Tests for the surrogate alignment algorithm (pipes/surrogate/align.py)."""

from __future__ import annotations

import pytest

from pypedeid.domain import EntitySpan

faker = pytest.importorskip("faker", reason="surrogate alignment requires faker")
from pypedeid.pipes.surrogate.align import surrogate_text_with_spans  # noqa: E402


def test_empty_spans_returns_original_text():
    text = "Just some text, no PHI"
    out_text, out_spans = surrogate_text_with_spans(text, [])
    assert out_text == text
    assert out_spans == []


def test_deterministic_seed_produces_identical_output():
    text = "Patient John Smith visited on 01/15/1980"
    spans = [
        EntitySpan(start=8, end=18, label="NAME"),
        EntitySpan(start=30, end=40, label="DATE"),
    ]
    out1, spans1 = surrogate_text_with_spans(text, spans, seed=42)
    out2, spans2 = surrogate_text_with_spans(text, spans, seed=42)
    assert out1 == out2
    assert [(s.start, s.end, s.label) for s in spans1] == [
        (s.start, s.end, s.label) for s in spans2
    ]


def test_spans_point_to_surrogate_entities():
    text = "Patient John Smith visited"
    spans = [EntitySpan(start=8, end=18, label="NAME")]
    out_text, out_spans = surrogate_text_with_spans(text, spans, seed=1)
    assert len(out_spans) == 1
    s = out_spans[0]
    # The surrogate substring must match what replaced the original.
    substring = out_text[s.start:s.end]
    # Non-empty replacement, and the prefix of out_text up to s.start preserves original prefix.
    assert substring != ""
    assert out_text[:s.start] == text[:8]
    # Suffix after span also preserved
    assert out_text.endswith(" visited")


def test_adjacent_spans_back_to_back():
    text = "JohnSmith01151980"
    spans = [
        EntitySpan(start=0, end=9, label="NAME"),
        EntitySpan(start=9, end=17, label="DATE"),
    ]
    out_text, out_spans = surrogate_text_with_spans(text, spans, seed=7)
    # No gap between the two output spans.
    assert out_spans[0].end == out_spans[1].start
    # Every output char up to the end of span2 is replaced.
    assert out_spans[0].start == 0
    assert out_text[out_spans[1].end:] == ""


def test_surrogate_longer_than_original_shifts_following_spans():
    # Short original is replaced by a longer surrogate for typical Name/Date strategies.
    text = "AB likes CD"
    spans = [
        EntitySpan(start=0, end=2, label="NAME"),
        EntitySpan(start=9, end=11, label="NAME"),
    ]
    out_text, out_spans = surrogate_text_with_spans(text, spans, seed=3)
    # First span starts at 0.
    assert out_spans[0].start == 0
    # Second span starts where first ended + len(" likes ").
    between = " likes "
    assert out_text[out_spans[0].end:out_spans[1].start] == between
    # Span offsets reflect cumulative shift; names are generally > 2 chars.
    assert out_spans[1].start >= 9


def test_surrogate_shorter_than_original_also_aligns():
    # Use a label + original pair where surrogate is shorter (strategy unknown → "*" * len).
    text = "prefix LONGORIGINAL suffix"
    spans = [EntitySpan(start=7, end=19, label="UNKNOWN_LABEL")]
    out_text, out_spans = surrogate_text_with_spans(text, spans, seed=5)
    s = out_spans[0]
    assert out_text[:s.start] == "prefix "
    assert out_text[s.end:] == " suffix"
    # Replacement length == substring length
    assert s.end - s.start == len(out_text[s.start:s.end])


def test_overlapping_spans_rejected():
    text = "Overlap here"
    spans = [
        EntitySpan(start=0, end=8, label="NAME"),
        EntitySpan(start=4, end=12, label="NAME"),
    ]
    with pytest.raises(ValueError, match="Overlapping"):
        surrogate_text_with_spans(text, spans, seed=1)


def test_consistency_same_entity_same_surrogate():
    """Same (label, original) pair within one call should yield the same replacement."""
    text = "John said and then John said"
    spans = [
        EntitySpan(start=0, end=4, label="NAME"),
        EntitySpan(start=19, end=23, label="NAME"),
    ]
    out_text, out_spans = surrogate_text_with_spans(text, spans, seed=11, consistency=True)
    first = out_text[out_spans[0].start:out_spans[0].end]
    second = out_text[out_spans[1].start:out_spans[1].end]
    assert first == second


def test_labels_and_metadata_preserved():
    text = "Patient Jane at 555-1234"
    spans = [
        EntitySpan(start=8, end=12, label="NAME", confidence=0.9, source="detector-a"),
        EntitySpan(start=16, end=24, label="PHONE", confidence=0.5, source="detector-b"),
    ]
    _, out_spans = surrogate_text_with_spans(text, spans, seed=17)
    assert out_spans[0].label == "NAME"
    assert out_spans[0].confidence == 0.9
    assert out_spans[0].source == "detector-a"
    assert out_spans[1].label == "PHONE"
    assert out_spans[1].source == "detector-b"


def test_unordered_input_spans_are_sorted_internally():
    text = "AA BB CC"
    spans = [
        EntitySpan(start=6, end=8, label="NAME"),
        EntitySpan(start=0, end=2, label="NAME"),
    ]
    out_text, out_spans = surrogate_text_with_spans(text, spans, seed=19)
    # Output spans must be in text order (sorted by start).
    assert out_spans[0].start < out_spans[1].start
    # Middle " BB " preserved (between the two replacements).
    assert " BB " in out_text
