"""Tests for training data export (CoNLL, spaCy DocBin, HuggingFace JSONL)."""

from __future__ import annotations

import json

import pytest

from pypedeid.domain import AnnotatedDocument, Document, EntitySpan
from pypedeid.training_export import (
    FORMATS,
    _bio_tags,
    _tokenize,
    export_annotated_jsonl,
    export_training_data,
    to_annotated_jsonl,
    to_conll,
    to_huggingface_jsonl,
    write_conll,
    write_huggingface,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_doc(
    doc_id: str,
    text: str,
    spans: list[tuple[int, int, str]],
) -> AnnotatedDocument:
    return AnnotatedDocument(
        document=Document(id=doc_id, text=text),
        spans=[EntitySpan(start=s, end=e, label=label) for s, e, label in spans],
    )


@pytest.fixture
def sample_docs() -> list[AnnotatedDocument]:
    return [
        _make_doc("doc1", "Patient John Smith DOB 01/15/1980", [
            (8, 18, "NAME"),
            (23, 33, "DATE"),
        ]),
        _make_doc("doc2", "Dr. Jane Doe phone 555-1234", [
            (4, 12, "NAME"),
            (19, 27, "PHONE"),
        ]),
    ]


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------


def test_tokenize_basic():
    tokens = _tokenize("Patient John Smith")
    assert [(t, s, e) for t, s, e in tokens] == [
        ("Patient", 0, 7),
        ("John", 8, 12),
        ("Smith", 13, 18),
    ]


def test_tokenize_empty():
    assert _tokenize("") == []


def test_tokenize_preserves_offsets():
    text = "  hello   world  "
    tokens = _tokenize(text)
    for tok, start, end in tokens:
        assert text[start:end] == tok


# ---------------------------------------------------------------------------
# BIO tagging
# ---------------------------------------------------------------------------


def test_bio_tags_simple():
    tokens = _tokenize("Patient John Smith DOB 01/15/1980")
    spans = [EntitySpan(start=8, end=18, label="NAME")]
    tags = _bio_tags(tokens, spans)
    assert tags == ["O", "B-NAME", "I-NAME", "O", "O"]


def test_bio_tags_no_spans():
    tokens = _tokenize("Hello world")
    assert _bio_tags(tokens, []) == ["O", "O"]


def test_bio_tags_multiple_spans():
    tokens = _tokenize("Patient John Smith DOB 01/15/1980")
    spans = [
        EntitySpan(start=8, end=18, label="NAME"),
        EntitySpan(start=23, end=33, label="DATE"),
    ]
    tags = _bio_tags(tokens, spans)
    assert tags == ["O", "B-NAME", "I-NAME", "O", "B-DATE"]


def test_bio_tags_single_token_span():
    tokens = _tokenize("Call 555-1234 now")
    spans = [EntitySpan(start=5, end=13, label="PHONE")]
    tags = _bio_tags(tokens, spans)
    assert tags == ["O", "B-PHONE", "O"]


# ---------------------------------------------------------------------------
# CoNLL export
# ---------------------------------------------------------------------------


def test_to_conll_format(sample_docs):
    output = to_conll(sample_docs)
    lines = output.split("\n")

    # Should start with DOCSTART
    assert lines[0] == "-DOCSTART- -X- O O"
    assert lines[1] == ""

    # First token line should be "Patient O"
    first_batch: list[str] = []
    for line in lines[2:]:
        if line == "":
            break
        first_batch.append(line)
    assert first_batch[0] == "Patient O"
    assert first_batch[1] == "John B-NAME"
    assert first_batch[2] == "Smith I-NAME"


def test_write_conll(sample_docs, tmp_path):
    path = write_conll(sample_docs, tmp_path)
    assert path.exists()
    assert path.name == "train.conll"
    content = path.read_text()
    assert "-DOCSTART-" in content
    assert "B-NAME" in content


def test_write_conll_custom_filename(sample_docs, tmp_path):
    path = write_conll(sample_docs, tmp_path, filename="test.conll")
    assert path.name == "test.conll"


# ---------------------------------------------------------------------------
# HuggingFace JSONL export
# ---------------------------------------------------------------------------


def test_to_huggingface_jsonl(sample_docs):
    output = to_huggingface_jsonl(sample_docs)
    lines = output.strip().split("\n")
    assert len(lines) == 2

    rec = json.loads(lines[0])
    assert rec["id"] == "doc1"
    assert isinstance(rec["tokens"], list)
    assert isinstance(rec["ner_tags"], list)
    assert len(rec["tokens"]) == len(rec["ner_tags"])
    assert "B-NAME" in rec["ner_tags"]


def test_write_huggingface(sample_docs, tmp_path):
    path = write_huggingface(sample_docs, tmp_path)
    assert path.exists()
    assert path.name == "train.jsonl"


# ---------------------------------------------------------------------------
# Unified export interface
# ---------------------------------------------------------------------------


def test_export_training_data_conll(sample_docs, tmp_path):
    path = export_training_data(sample_docs, tmp_path, "conll")
    assert path.exists()
    assert "B-NAME" in path.read_text()


def test_export_training_data_huggingface(sample_docs, tmp_path):
    path = export_training_data(sample_docs, tmp_path, "huggingface")
    assert path.exists()
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 2


def test_export_training_data_unknown_format(sample_docs, tmp_path):
    with pytest.raises(ValueError, match="Unknown format"):
        export_training_data(sample_docs, tmp_path, "unknown")


def test_export_training_data_custom_filename(sample_docs, tmp_path):
    path = export_training_data(
        sample_docs, tmp_path, "conll", filename="custom.conll"
    )
    assert path.name == "custom.conll"


def test_formats_constant():
    assert "conll" in FORMATS
    assert "spacy" in FORMATS
    assert "huggingface" in FORMATS
    assert "jsonl" in FORMATS


# ---------------------------------------------------------------------------
# Annotated JSONL export
# ---------------------------------------------------------------------------


def test_annotated_jsonl_roundtrip(sample_docs, tmp_path):
    path = export_annotated_jsonl(sample_docs, tmp_path)
    assert path.exists()
    assert path.name == "train.jsonl"
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == len(sample_docs)
    restored = [AnnotatedDocument.model_validate_json(ln) for ln in lines]
    for original, parsed in zip(sample_docs, restored):
        assert parsed.document.id == original.document.id
        assert parsed.document.text == original.document.text
        assert [(s.start, s.end, s.label) for s in parsed.spans] == [
            (s.start, s.end, s.label) for s in original.spans
        ]


def test_annotated_jsonl_to_string(sample_docs):
    out = to_annotated_jsonl(sample_docs)
    lines = out.split("\n")
    assert len(lines) == len(sample_docs)
    first = json.loads(lines[0])
    assert first["document"]["id"] == "doc1"
    assert len(first["spans"]) == 2


def test_export_training_data_jsonl(sample_docs, tmp_path):
    path = export_training_data(sample_docs, tmp_path, "jsonl")
    assert path.exists()
    assert path.name == "train.jsonl"
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == len(sample_docs)


def test_export_training_data_jsonl_custom_filename(sample_docs, tmp_path):
    path = export_training_data(
        sample_docs, tmp_path, "jsonl", filename="gold.jsonl"
    )
    assert path.name == "gold.jsonl"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_export_empty_docs(tmp_path):
    docs = [_make_doc("empty", "No PHI here", [])]
    path = export_training_data(docs, tmp_path, "conll")
    content = path.read_text()
    assert "B-" not in content
    assert "I-" not in content


def test_export_doc_with_no_text(tmp_path):
    doc = AnnotatedDocument(
        document=Document(id="blank", text="word"),
        spans=[],
    )
    path = export_training_data([doc], tmp_path, "huggingface")
    rec = json.loads(path.read_text().strip())
    assert rec["tokens"] == ["word"]
    assert rec["ner_tags"] == ["O"]
