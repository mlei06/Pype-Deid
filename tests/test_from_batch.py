"""Tests for ``ingest/from_batch.py`` — batch → AnnotatedDocument converter."""

from __future__ import annotations

import json
from pathlib import Path

from pypedeid.domain import AnnotatedDocument, EntitySpan
from pypedeid.ingest.from_batch import (
    _iter_text_inputs,
    batch_to_annotated_docs,
)


class _StubPipeline:
    """Forward: mark the first 4 chars as NAME so tests can verify span flow."""

    def forward(self, doc: AnnotatedDocument) -> AnnotatedDocument:
        end = min(4, len(doc.document.text))
        return AnnotatedDocument(
            document=doc.document,
            spans=[EntitySpan(start=0, end=end, label="NAME", source="stub")] if end > 0 else [],
        )


def test_batch_to_annotated_docs_yields_spans():
    inputs = [("a", "Alice went"), ("b", "Bob is here")]
    out = list(batch_to_annotated_docs(inputs, pipeline=_StubPipeline()))
    assert [d.document.id for d in out] == ["a", "b"]
    assert [d.document.text for d in out] == ["Alice went", "Bob is here"]
    for d in out:
        assert len(d.spans) == 1
        assert d.spans[0].label == "NAME"
        assert d.spans[0].start == 0
        assert d.spans[0].end == 4


def test_batch_to_annotated_docs_empty_text_no_span():
    inputs = [("empty", "")]
    out = list(batch_to_annotated_docs(inputs, pipeline=_StubPipeline()))
    assert out[0].spans == []


def test_iter_text_inputs_directory(tmp_path: Path):
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")
    (tmp_path / "b.txt").write_text("beta", encoding="utf-8")
    (tmp_path / "skip.md").write_text("ignored", encoding="utf-8")
    result = list(_iter_text_inputs(tmp_path))
    assert result == [("a", "alpha"), ("b", "beta")]


def test_iter_text_inputs_single_txt(tmp_path: Path):
    p = tmp_path / "note.txt"
    p.write_text("hello", encoding="utf-8")
    assert list(_iter_text_inputs(p)) == [("note", "hello")]


def test_iter_text_inputs_jsonl_accepts_bare_and_wrapped(tmp_path: Path):
    p = tmp_path / "docs.jsonl"
    lines = [
        {"id": "x1", "text": "first"},
        {"document": {"id": "x2", "text": "second"}, "spans": []},
        {"text": "no id"},
    ]
    p.write_text(
        "\n".join(json.dumps(ln) for ln in lines) + "\n", encoding="utf-8"
    )
    result = list(_iter_text_inputs(p))
    assert result[0] == ("x1", "first")
    assert result[1] == ("x2", "second")
    assert result[2][1] == "no id"
    assert result[2][0].startswith("docs_line_")


def test_iter_text_inputs_jsonl_skips_blank_lines(tmp_path: Path):
    p = tmp_path / "with_blanks.jsonl"
    p.write_text(
        json.dumps({"id": "a", "text": "t1"}) + "\n\n"
        + json.dumps({"id": "b", "text": "t2"}) + "\n",
        encoding="utf-8",
    )
    result = list(_iter_text_inputs(p))
    assert [r[0] for r in result] == ["a", "b"]
