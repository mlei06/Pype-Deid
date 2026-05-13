"""Tests for blacklist span transformer."""

from __future__ import annotations

from pypedeid.domain import AnnotatedDocument, Document, EntitySpan
from pypedeid.pipes.blacklist import BlacklistSpans, BlacklistSpansConfig
from pypedeid.pipes.registry import load_pipeline


def _doc(text: str, spans: list[EntitySpan]) -> AnnotatedDocument:
    return AnnotatedDocument(document=Document(id="d", text=text), spans=spans)


def test_blacklist_drops_span_with_token_in_notes_common() -> None:
    """Token PATIENT is a common clinical term and should be blacklisted."""
    text = "seen in PATIENT room"
    spans = [
        EntitySpan(start=text.index("PATIENT"), end=text.index("PATIENT") + 7, label="FOO"),
    ]
    pipe = BlacklistSpans(
        BlacklistSpansConfig(terms=["PATIENT"], load_all_dictionaries=False, match="any_token")
    )
    out = pipe.forward(_doc(text, spans)).spans
    assert len(out) == 0


def test_blacklist_keeps_when_no_token_match() -> None:
    text = "Smith J"
    spans = [EntitySpan(start=0, end=5, label="NAME")]
    pipe = BlacklistSpans(
        BlacklistSpansConfig(
            terms=["PATIENT"],
            load_all_dictionaries=False,
            match="any_token",
            apply_to_labels=["NAME"],
        )
    )
    out = pipe.forward(_doc(text, spans)).spans
    assert len(out) == 1


def test_blacklist_apply_to_labels_skips_other_labels() -> None:
    text = "PATIENT room"
    spans = [
        EntitySpan(start=0, end=7, label="NAME"),
        EntitySpan(start=0, end=7, label="OTHER"),
    ]
    pipe = BlacklistSpans(
        BlacklistSpansConfig(
            terms=["PATIENT"],
            load_all_dictionaries=False,
            match="any_token",
            apply_to_labels=["NAME"],
        )
    )
    out = pipe.forward(_doc(text, spans)).spans
    assert len(out) == 1
    assert out[0].label == "OTHER"


def test_whole_span_drops_only_full_match() -> None:
    text = "PATIENTFOO"
    spans = [EntitySpan(start=0, end=10, label="X")]
    pipe = BlacklistSpans(
        BlacklistSpansConfig(
            terms=["PATIENT"],
            load_all_dictionaries=False,
            match="whole_span",
        )
    )
    assert len(pipe.forward(_doc(text, spans)).spans) == 1

    text2 = "PATIENT"
    spans2 = [EntitySpan(start=0, end=7, label="X")]
    assert len(pipe.forward(_doc(text2, spans2)).spans) == 0


def test_exact_span_migrates_to_whole_span() -> None:
    """exact_span was redundant; the validator silently migrates it."""
    cfg = BlacklistSpansConfig(
        terms=["PATIENT"],
        load_all_dictionaries=False,
        match="exact_span",
    )
    assert cfg.match == "whole_span"


def test_overlap_document_regex_only_regions() -> None:
    text = "ok Bell palsy end"
    spans = [
        EntitySpan(start=0, end=2, label="X"),
        EntitySpan(start=3, end=13, label="X"),
    ]
    pipe = BlacklistSpans(
        BlacklistSpansConfig(
            load_all_dictionaries=False,
            match="overlap_document",
            regex_blacklist_patterns=[r"Bell\s+palsy"],
        )
    )
    out = pipe.forward(_doc(text, spans)).spans
    assert len(out) == 1
    assert out[0].start == 0 and out[0].end == 2


def test_overlap_document_drops_when_span_overlaps_region() -> None:
    text = "aa PATIENT bb"
    spans = [
        EntitySpan(start=0, end=2, label="X"),
        EntitySpan(start=3, end=10, label="X"),
    ]
    pipe = BlacklistSpans(
        BlacklistSpansConfig(
            terms=["PATIENT"],
            load_all_dictionaries=False,
            match="overlap_document",
        )
    )
    out = pipe.forward(_doc(text, spans)).spans
    assert len(out) == 1
    assert out[0].start == 0 and out[0].end == 2


def test_blacklist_merge_wordlists_endpoint(client) -> None:
    r = client.post(
        "/pipelines/blacklist/parse-wordlists",
        files=[
            ("files", ("a.txt", b"alpha\nbeta\n", "text/plain")),
            ("files", ("b.txt", b"beta\ngamma\n", "text/plain")),
        ],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 3
    assert set(body["terms"]) == {"alpha", "beta", "gamma"}
    assert len(body["source_files"]) == 2


def test_blacklist_load_pipeline() -> None:
    cfg = {
        "pipes": [
            {"type": "regex_ner"},
            {"type": "whitelist", "config": {"load_all_dictionaries": False}},
            {
                "type": "blacklist",
                "config": {
                    "terms": ["PATIENT"],
                    "load_all_dictionaries": False,
                    "match": "any_token",
                },
            },
        ]
    }
    p = load_pipeline(cfg)
    doc = AnnotatedDocument(document=Document(id="x", text="No special tokens."), spans=[])
    out = p.forward(doc)
    assert isinstance(out.spans, list)
