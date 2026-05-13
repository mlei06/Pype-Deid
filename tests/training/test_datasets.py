"""Tests for label derivation and subword alignment.

Alignment tests use a mock fast tokenizer so they don't need network access.
Integration tests that use a real tokenizer are gated with @pytest.mark.train.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from pypedeid.domain import AnnotatedDocument, Document, EntitySpan
from pypedeid.training.datasets import derive_label_list, tokenize_and_align
from pypedeid.training.errors import SlowTokenizerUnsupported


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _doc(text: str, spans: list[tuple[int, int, str]]) -> AnnotatedDocument:
    return AnnotatedDocument(
        document=Document(id="test", text=text),
        spans=[EntitySpan(start=s, end=e, label=label) for s, e, label in spans],
    )


class MockEncoding:
    """Minimal BatchEncoding-alike returned by a mock fast tokenizer."""

    def __init__(
        self,
        input_ids: list[int],
        attention_mask: list[int],
        word_ids: list[int | None],
        offset_mapping: list[tuple[int, int]],
    ):
        self._word_ids = word_ids
        self._data = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "offset_mapping": offset_mapping,
        }

    def word_ids(self) -> list[int | None]:
        return self._word_ids

    def __getitem__(self, key: str) -> Any:
        return self._data[key]


def _make_tokenizer(encoding: MockEncoding, is_fast: bool = True) -> MagicMock:
    tok = MagicMock()
    tok.is_fast = is_fast
    tok.return_value = encoding
    return tok


# ---------------------------------------------------------------------------
# derive_label_list
# ---------------------------------------------------------------------------


def test_derive_from_docs():
    docs = [
        _doc("John 1980", [(0, 4, "NAME"), (5, 9, "DATE")]),
        _doc("Alice", [(0, 5, "NAME")]),
    ]
    bio = derive_label_list(docs, override=None)
    assert bio[0] == "O"
    assert "B-DATE" in bio
    assert "I-DATE" in bio
    assert "B-NAME" in bio
    assert "I-NAME" in bio
    assert bio.index("B-DATE") < bio.index("I-DATE")


def test_derive_determinism():
    docs = [_doc("t", [(0, 1, "Z"), (0, 1, "A")])]
    bio1 = derive_label_list(docs, None)
    bio2 = derive_label_list(docs, None)
    assert bio1 == bio2


def test_derive_with_override():
    bio = derive_label_list([], override=["DATE", "NAME"])
    # Override sorted → DATE before NAME
    assert bio == ["O", "B-DATE", "I-DATE", "B-NAME", "I-NAME"]


def test_derive_override_ignores_doc_labels():
    docs = [_doc("t", [(0, 1, "SSN")])]
    bio = derive_label_list(docs, override=["NAME"])
    assert "B-SSN" not in bio
    assert "B-NAME" in bio


# ---------------------------------------------------------------------------
# tokenize_and_align — using mock tokenizer
# ---------------------------------------------------------------------------

# "John Smith was here"
#  0123456789012345678
# words: John[0,4], Smith[5,10], was[11,14], here[15,19]
# span: NAME [0, 10]

_JOHN_SMITH_IDS = [101, 1234, 5678, 2001, 2182, 102]
_JOHN_SMITH_MASK = [1, 1, 1, 1, 1, 1]
# word_ids: CLS=None, John=0, Smith=1, was=2, here=3, SEP=None
_JOHN_SMITH_WIDS = [None, 0, 1, 2, 3, None]
# offset_mapping per token (subword start, end)
_JOHN_SMITH_OFFSETS = [(0, 0), (0, 4), (5, 10), (11, 14), (15, 19), (0, 0)]


def _john_smith_encoding() -> MockEncoding:
    return MockEncoding(
        _JOHN_SMITH_IDS,
        _JOHN_SMITH_MASK,
        _JOHN_SMITH_WIDS,
        _JOHN_SMITH_OFFSETS,
    )


def test_special_tokens_get_minus100():
    enc = _john_smith_encoding()
    tok = _make_tokenizer(enc)
    bio2id = {"O": 0, "B-NAME": 1, "I-NAME": 2}
    doc = _doc("John Smith was here", [(0, 10, "NAME")])
    result = tokenize_and_align(doc, tok, bio2id, max_length=128)
    labels = result["labels"]
    assert labels[0] == -100  # [CLS]
    assert labels[-1] == -100  # [SEP]


def test_b_label_on_first_word():
    enc = _john_smith_encoding()
    tok = _make_tokenizer(enc)
    bio2id = {"O": 0, "B-NAME": 1, "I-NAME": 2}
    doc = _doc("John Smith was here", [(0, 10, "NAME")])
    result = tokenize_and_align(doc, tok, bio2id, max_length=128)
    labels = result["labels"]
    assert labels[1] == 1  # "John" → B-NAME


def test_i_label_on_continuation_word():
    enc = _john_smith_encoding()
    tok = _make_tokenizer(enc)
    bio2id = {"O": 0, "B-NAME": 1, "I-NAME": 2}
    doc = _doc("John Smith was here", [(0, 10, "NAME")])
    result = tokenize_and_align(doc, tok, bio2id, max_length=128)
    labels = result["labels"]
    assert labels[2] == 2  # "Smith" → I-NAME


def test_outside_words_get_O():
    enc = _john_smith_encoding()
    tok = _make_tokenizer(enc)
    bio2id = {"O": 0, "B-NAME": 1, "I-NAME": 2}
    doc = _doc("John Smith was here", [(0, 10, "NAME")])
    result = tokenize_and_align(doc, tok, bio2id, max_length=128)
    labels = result["labels"]
    assert labels[3] == 0  # "was" → O
    assert labels[4] == 0  # "here" → O


def test_multi_subword_continuation_is_minus100():
    """Test that continuation subwords (same word_id) get -100, not I-label."""
    # "hospitalized" → ["hos", "##pital", "##ized"] all word_id=0
    enc = MockEncoding(
        input_ids=[101, 100, 101, 102, 103],
        attention_mask=[1, 1, 1, 1, 1],
        word_ids=[None, 0, 0, 0, None],
        offset_mapping=[(0, 0), (0, 3), (3, 8), (8, 12), (0, 0)],
    )
    tok = _make_tokenizer(enc)
    bio2id = {"O": 0, "B-DRUG": 1, "I-DRUG": 2}
    # span covers the whole word
    doc = _doc("hospitalized", [(0, 12, "DRUG")])
    result = tokenize_and_align(doc, tok, bio2id, max_length=128)
    labels = result["labels"]
    assert labels[0] == -100   # [CLS]
    assert labels[1] == 1      # "hos" → B-DRUG (first subword of word 0)
    assert labels[2] == -100   # "##pital" → -100 (continuation subword of word 0)
    assert labels[3] == -100   # "##ized" → -100 (continuation subword of word 0)
    assert labels[4] == -100   # [SEP]


def test_slow_tokenizer_raises():
    tok = _make_tokenizer(MagicMock(), is_fast=False)
    bio2id = {"O": 0}
    doc = _doc("text", [])
    with pytest.raises(SlowTokenizerUnsupported):
        tokenize_and_align(doc, tok, bio2id, max_length=128)


def test_no_spans_all_O():
    enc = _john_smith_encoding()
    tok = _make_tokenizer(enc)
    bio2id = {"O": 0, "B-NAME": 1, "I-NAME": 2}
    doc = _doc("John Smith was here", [])
    result = tokenize_and_align(doc, tok, bio2id, max_length=128)
    labels = result["labels"]
    # non-special tokens should all be O (0)
    assert labels[1] == 0
    assert labels[2] == 0
    assert labels[3] == 0


def test_overlapping_spans_longest_wins():
    """When spans overlap, longest span should win."""
    # Span A: [0, 4] NAME, Span B: [0, 10] PATIENT (longer → wins)
    enc = _john_smith_encoding()
    tok = _make_tokenizer(enc)
    bio2id = {"O": 0, "B-NAME": 1, "I-NAME": 2, "B-PATIENT": 3, "I-PATIENT": 4}
    doc = _doc(
        "John Smith was here",
        [(0, 4, "NAME"), (0, 10, "PATIENT")],
    )
    result = tokenize_and_align(doc, tok, bio2id, max_length=128)
    labels = result["labels"]
    assert labels[1] == 3  # "John" → B-PATIENT (longer span wins)
    assert labels[2] == 4  # "Smith" → I-PATIENT


# ---------------------------------------------------------------------------
# derive_label_list → NoLabelsFound guard (tested via build_hf_datasets)
# ---------------------------------------------------------------------------


def test_derive_empty_docs_with_no_override():
    bio = derive_label_list([], override=None)
    assert bio == ["O"]
