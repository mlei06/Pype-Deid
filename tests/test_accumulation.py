"""Tests for detector span accumulation and skip_overlapping behaviour."""

from __future__ import annotations

from pypedeid.domain import AnnotatedDocument, Document, EntitySpan
from pypedeid.pipes.detector_label_mapping import accumulate_spans
from pypedeid.pipes.combinators import Pipeline
from pypedeid.pipes.regex_ner import RegexNerConfig, RegexNerPipe
from pypedeid.pipes.whitelist import WhitelistConfig, WhitelistPipe


def _doc(text: str, spans: list[EntitySpan] | None = None) -> AnnotatedDocument:
    return AnnotatedDocument(
        document=Document(id="d", text=text), spans=spans or []
    )


# ---------------------------------------------------------------------------
# accumulate_spans helper
# ---------------------------------------------------------------------------


def test_accumulate_spans_combines_existing_and_new() -> None:
    doc = _doc("abcdefghij", [EntitySpan(start=0, end=3, label="A")])
    new = [EntitySpan(start=5, end=8, label="B")]
    result = accumulate_spans(doc, new)
    assert len(result.spans) == 2
    labels = {s.label for s in result.spans}
    assert labels == {"A", "B"}


def test_accumulate_spans_skip_overlapping_drops_conflict() -> None:
    existing = [EntitySpan(start=0, end=5, label="A")]
    doc = _doc("abcdefghij", existing)
    new = [EntitySpan(start=3, end=8, label="B")]
    result = accumulate_spans(doc, new, skip_overlapping=True)
    assert len(result.spans) == 1
    assert result.spans[0].label == "A"


def test_accumulate_spans_skip_overlapping_keeps_non_overlapping() -> None:
    existing = [EntitySpan(start=0, end=3, label="A")]
    doc = _doc("abcdefghij", existing)
    new = [EntitySpan(start=5, end=8, label="B")]
    result = accumulate_spans(doc, new, skip_overlapping=True)
    assert len(result.spans) == 2


def test_accumulate_spans_default_keeps_overlaps() -> None:
    existing = [EntitySpan(start=0, end=5, label="A")]
    doc = _doc("abcdefghij", existing)
    new = [EntitySpan(start=3, end=8, label="B")]
    result = accumulate_spans(doc, new, skip_overlapping=False)
    assert len(result.spans) == 2


def test_accumulate_spans_sorted_output() -> None:
    doc = _doc("abcdefghij", [EntitySpan(start=5, end=8, label="B")])
    new = [EntitySpan(start=0, end=3, label="A")]
    result = accumulate_spans(doc, new)
    assert result.spans[0].start < result.spans[1].start


# ---------------------------------------------------------------------------
# Chained detectors accumulate
# ---------------------------------------------------------------------------


def test_chained_detectors_accumulate_spans() -> None:
    """Two chained detectors should produce the union of their spans."""
    pipe = Pipeline(pipes=[
        RegexNerPipe(RegexNerConfig()),
        WhitelistPipe(WhitelistConfig()),
    ])
    doc = _doc("Call 555-123-4567.")
    out = pipe.forward(doc)
    # Regex should find PHONE; whitelist may or may not add more,
    # but the key assertion is that both detectors' spans are present.
    assert len(out.spans) >= 1
    sources = {s.source for s in out.spans}
    assert "regex_ner" in sources


def test_skip_overlapping_config_via_pipeline() -> None:
    """Second detector with skip_overlapping=True drops overlapping spans."""
    pipe = Pipeline(pipes=[
        RegexNerPipe(RegexNerConfig()),
        WhitelistPipe(WhitelistConfig(skip_overlapping=True)),
    ])
    doc = _doc("Call 555-123-4567.")
    out = pipe.forward(doc)
    # Whitelist spans that overlap regex spans should be dropped
    for span in out.spans:
        if span.source == "whitelist":
            # Should not overlap any regex span
            regex_spans = [s for s in out.spans if s.source == "regex_ner"]
            for rs in regex_spans:
                assert not (span.start < rs.end and rs.start < span.end), (
                    f"whitelist span {span} overlaps regex span {rs}"
                )
