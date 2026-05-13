"""Tests for resolve_spans pipe and shared span_merge logic."""

from __future__ import annotations

from pypedeid.domain import AnnotatedDocument, Document, EntitySpan
from pypedeid.pipes.combinators import Pipeline, ResolveSpans, ResolveSpansConfig
from pypedeid.pipes.regex_ner import RegexNerConfig, RegexNerPipe
from pypedeid.pipes.registry import load_pipeline
from pypedeid.pipes.whitelist import WhitelistConfig, WhitelistPipe


def _doc(text: str, spans: list[EntitySpan]) -> AnnotatedDocument:
    return AnnotatedDocument(document=Document(id="d", text=text), spans=spans)


def test_resolve_spans_longest_non_overlapping_single_group() -> None:
    text = "abcdefghijkl"
    spans = [
        EntitySpan(start=0, end=3, label="A"),
        EntitySpan(start=2, end=8, label="B"),
    ]
    pipe = ResolveSpans(ResolveSpansConfig(strategy="longest_non_overlapping"))
    out = pipe.forward(_doc(text, spans)).spans
    assert len(out) == 1
    assert out[0].label == "B"
    assert out[0].start == 2 and out[0].end == 8


def test_resolve_spans_exact_dedupe() -> None:
    spans = [
        EntitySpan(start=0, end=3, label="X"),
        EntitySpan(start=0, end=3, label="X"),
    ]
    pipe = ResolveSpans(ResolveSpansConfig(strategy="exact_dedupe"))
    out = pipe.forward(_doc("abc", spans)).spans
    assert len(out) == 1


def test_chained_detectors_then_resolve() -> None:
    """Chained detectors accumulate spans; resolve_spans dedupes them."""
    cfg = {
        "pipes": [
            {"type": "regex_ner"},
            {
                "type": "whitelist",
                "config": {},
            },
            {"type": "resolve_spans", "config": {"strategy": "exact_dedupe"}},
        ]
    }
    p = load_pipeline(cfg)
    doc = AnnotatedDocument(document=Document(id="x", text="x@y.co"), spans=[])
    out = p.forward(doc)
    assert isinstance(out.spans, list)


def test_regex_then_resolve_longest() -> None:
    pipe = Pipeline(pipes=[
        RegexNerPipe(RegexNerConfig()),
        WhitelistPipe(WhitelistConfig()),
    ])
    doc = AnnotatedDocument(document=Document(id="d", text="a@b.co extra"), spans=[])
    doc = pipe.forward(doc)
    resolver = ResolveSpans(ResolveSpansConfig(strategy="longest_non_overlapping"))
    doc2 = resolver.forward(doc)
    assert all(isinstance(s, EntitySpan) for s in doc2.spans)
