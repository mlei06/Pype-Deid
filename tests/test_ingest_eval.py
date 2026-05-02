from __future__ import annotations

from pathlib import Path

from clinical_deid.domain import AnnotatedDocument, Document, EntitySpan
from clinical_deid.eval.matching import compute_metrics
from clinical_deid.ingest.jsonl import load_annotated_documents_from_jsonl_bytes
from clinical_deid.pipes.regex_ner import RegexNerPipe


def test_load_sample_jsonl() -> None:
    p = Path(__file__).parent / "fixtures" / "sample.jsonl"
    data = p.read_bytes()
    docs = load_annotated_documents_from_jsonl_bytes(data)
    assert len(docs) == 2
    assert docs[0].document.id == "doc_a"


def test_strict_f1_perfect_match() -> None:
    text = "x"
    d = AnnotatedDocument(
        document=Document(id="1", text=text),
        spans=[EntitySpan(start=0, end=1, label="A")],
    )
    m = compute_metrics(d.spans, d.spans, text).strict
    assert m.precision == m.recall == m.f1 == 1.0
    assert m.tp == 1 and m.fp == m.fn == 0


def test_regex_pipe_finds_phone() -> None:
    ad = AnnotatedDocument(
        document=Document(id="1", text="Phone 555-999-0000 today."),
        spans=[],
    )
    out = RegexNerPipe().forward(ad)
    labels = {s.label for s in out.spans}
    assert "PHONE" in labels
