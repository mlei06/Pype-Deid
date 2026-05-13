"""Tests for sentence-level segmentation (training prep + inference remap)."""

from __future__ import annotations

import pytest

from pypedeid.domain import AnnotatedDocument, Document, EntitySpan
from pypedeid.training.segmentation import (
    sentence_offsets,
    split_doc_into_sentences,
)


def _doc(doc_id: str, text: str, spans: list[tuple[int, int, str]]) -> AnnotatedDocument:
    return AnnotatedDocument(
        document=Document(id=doc_id, text=text),
        spans=[EntitySpan(start=s, end=e, label=lbl) for s, e, lbl in spans],
    )


# ---------------------------------------------------------------------------
# sentence_offsets
# ---------------------------------------------------------------------------


def test_empty_text_returns_empty():
    assert sentence_offsets("") == []
    assert sentence_offsets("   \n\n  ") == []


def test_abbreviation_not_split():
    # "Dr." should not end the sentence — the whole thing is one sentence.
    text = "Dr. John Smith was admitted."
    offsets = sentence_offsets(text)
    assert offsets == [(0, len(text))]


def test_single_newline_not_a_boundary():
    # Line wrap mid-entity must not create a sentence boundary.
    text = "John\nSmith was admitted."
    offsets = sentence_offsets(text)
    # Single \n is a soft break — stays one sentence ending at the period.
    assert len(offsets) == 1
    start, end = offsets[0]
    assert text[start:end].replace("\n", " ") == "John Smith was admitted."


def test_paragraph_break_splits_section_header():
    text = "DISCHARGE DIAGNOSIS\n\nHypertension."
    offsets = sentence_offsets(text)
    assert len(offsets) == 2
    assert text[offsets[0][0] : offsets[0][1]] == "DISCHARGE DIAGNOSIS"
    assert text[offsets[1][0] : offsets[1][1]] == "Hypertension."


def test_multiple_sentences_split_on_period_and_capital():
    text = "Visit 1. Patient seen today. Labs are normal."
    offsets = sentence_offsets(text)
    assert len(offsets) == 3
    assert [text[s:e] for s, e in offsets] == [
        "Visit 1.",
        "Patient seen today.",
        "Labs are normal.",
    ]


def test_mg_abbreviation_not_split():
    text = "Gave 40 mg. BID dosing continues."
    offsets = sentence_offsets(text)
    # "mg." is an abbreviation — should not split here.
    assert offsets == [(0, len(text))]


def test_initial_abbreviation_not_split():
    # Middle initial "J." should not split.
    text = "Dr. John J. Smith was on call."
    offsets = sentence_offsets(text)
    assert offsets == [(0, len(text))]


def test_bullet_list_items_are_separate():
    text = "Issues:\n\n- Fever.\n\n- Cough.\n"
    offsets = sentence_offsets(text)
    assert len(offsets) == 3
    segments = [text[s:e] for s, e in offsets]
    assert segments[0] == "Issues:"
    assert segments[1] == "- Fever."
    assert segments[2] == "- Cough."


# ---------------------------------------------------------------------------
# split_doc_into_sentences — span clipping + offset remap
# ---------------------------------------------------------------------------


def test_span_entirely_inside_sentence_preserved():
    # "John Smith" fully inside sentence 1.
    text = "John Smith was admitted. Labs normal."
    doc = _doc("d1", text, [(0, 10, "NAME")])
    subs = split_doc_into_sentences(doc)
    assert len(subs) == 2
    s0 = subs[0]
    assert s0.document.text == "John Smith was admitted."
    assert len(s0.spans) == 1
    assert s0.spans[0].start == 0
    assert s0.spans[0].end == 10
    assert s0.spans[0].label == "NAME"
    # Second sentence has no PHI — no spans.
    assert subs[1].spans == []


def test_boundary_crossing_span_is_clipped():
    # Splitter error: entity spans a false boundary. We clip to each
    # sentence, keeping the label on both sides.
    # Text: "John.\n\nSmith was seen."  The annotation is "John.\n\nSmith" as
    # a single NAME (splitter error case).
    text = "John.\n\nSmith was seen."
    name_start = 0
    name_end = text.index("Smith") + len("Smith")
    doc = _doc("d1", text, [(name_start, name_end, "NAME")])
    subs = split_doc_into_sentences(doc)
    assert len(subs) == 2

    # Sentence 0 = "John." — span clipped to local [0, 5)
    assert subs[0].document.text == "John."
    assert len(subs[0].spans) == 1
    assert subs[0].spans[0].start == 0
    assert subs[0].spans[0].end == 5
    assert subs[0].spans[0].label == "NAME"

    # Sentence 1 = "Smith was seen." — span clipped to local [0, 5)
    assert subs[1].document.text == "Smith was seen."
    assert len(subs[1].spans) == 1
    assert subs[1].spans[0].start == 0
    assert subs[1].spans[0].end == 5
    assert subs[1].spans[0].label == "NAME"


def test_sentence_offset_in_metadata_enables_remap():
    # Regression: sub-doc metadata carries parent id + offset so an inference
    # caller can always reconstruct document-level coordinates.
    text = "Visit 1. Pt was seen."
    doc = _doc("parent-123", text, [])
    subs = split_doc_into_sentences(doc)
    assert len(subs) == 2
    for i, sub in enumerate(subs):
        meta = sub.document.metadata
        assert meta["parent_doc_id"] == "parent-123"
        assert meta["sentence_index"] == i
        # Remap: parent text at [offset, offset+len] must equal the sub text.
        off = meta["sentence_offset"]
        assert text[off : off + len(sub.document.text)] == sub.document.text


def test_span_outside_all_sentences_is_dropped():
    # Corner case: whitespace at end of doc is stripped from sentence bounds;
    # a span purely inside trailing whitespace should be dropped.
    text = "Hello world.   "
    doc = _doc("d1", text, [(12, 15, "OTHER")])
    subs = split_doc_into_sentences(doc)
    assert len(subs) == 1
    assert subs[0].spans == []


def test_zero_overlap_after_clip_is_dropped():
    # Span exactly on a paragraph break (whitespace only) gets dropped.
    text = "First.\n\nSecond."
    # gap is at index 6..8 (the two newlines). Put a span only there.
    doc = _doc("d1", text, [(6, 8, "OTHER")])
    subs = split_doc_into_sentences(doc)
    # Neither sentence overlaps the newline-only span → no spans anywhere.
    assert all(s.spans == [] for s in subs)


def test_empty_doc_produces_no_sentences():
    doc = _doc("d1", "   \n\n ", [])
    assert split_doc_into_sentences(doc) == []


# ---------------------------------------------------------------------------
# TrainingConfig validation
# ---------------------------------------------------------------------------


def test_training_config_segmentation_default_is_truncate():
    from pypedeid.training.config import TrainingConfig

    cfg = TrainingConfig(
        base_model="bert-base",
        train_dataset="ds",
        output_name="out",
    )
    assert cfg.segmentation == "truncate"


def test_training_config_segmentation_sentence_accepted():
    from pypedeid.training.config import TrainingConfig

    cfg = TrainingConfig(
        base_model="bert-base",
        train_dataset="ds",
        output_name="out",
        segmentation="sentence",
    )
    assert cfg.segmentation == "sentence"


def test_training_config_rejects_unknown_segmentation():
    from pypedeid.training.config import TrainingConfig
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TrainingConfig(
            base_model="bert-base",
            train_dataset="ds",
            output_name="out",
            segmentation="paragraph",
        )


# ---------------------------------------------------------------------------
# Inference mode resolution
# ---------------------------------------------------------------------------


def test_resolve_segmentation_auto_keeps_sentence_when_trained():
    from pypedeid.pipes.huggingface_ner.pipe import _resolve_segmentation_mode

    assert _resolve_segmentation_mode("auto", "sentence", "m") == "sentence"


def test_resolve_segmentation_auto_upgrades_truncate_to_chunk():
    """Auto mode never silently drops PHI past the context window — even
    truncate-trained or older manifests get full-document chunked inference."""
    from pypedeid.pipes.huggingface_ner.pipe import _resolve_segmentation_mode

    assert _resolve_segmentation_mode("auto", "truncate", "m") == "chunk"
    assert _resolve_segmentation_mode("auto", None, "m") == "chunk"


def test_resolve_segmentation_mismatch_warns(caplog):
    import logging
    from pypedeid.pipes.huggingface_ner.pipe import _resolve_segmentation_mode

    with caplog.at_level(logging.WARNING, logger="pypedeid.pipes.huggingface_ner.pipe"):
        mode = _resolve_segmentation_mode("sentence", "truncate", "my-model")
    assert mode == "sentence"
    assert any("my-model" in rec.message for rec in caplog.records)
    assert any("segmentation" in rec.message for rec in caplog.records)


def test_resolve_segmentation_match_no_warning(caplog):
    import logging
    from pypedeid.pipes.huggingface_ner.pipe import _resolve_segmentation_mode

    with caplog.at_level(logging.WARNING, logger="pypedeid.pipes.huggingface_ner.pipe"):
        mode = _resolve_segmentation_mode("sentence", "sentence", "m")
    assert mode == "sentence"
    assert not any("segmentation" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# Per-sentence inference offset remap
# ---------------------------------------------------------------------------


class _FakeHFPipeline:
    """Stand-in for transformers.pipeline that emits fixed predictions
    per call, so we can verify sentence-level offset remap."""

    def __init__(self, per_call: list[list[dict]]):
        self._per_call = list(per_call)
        self.calls: list[str] = []

    def __call__(self, text: str):
        self.calls.append(text)
        if not self._per_call:
            return []
        return self._per_call.pop(0)


def test_predict_huggingface_by_sentence_remaps_to_doc_coords():
    from pypedeid.pipes.huggingface_ner.pipe import _predict_by_sentence

    # Two sentences. Predictions are *sentence-local*; we assert they land
    # at the correct *document* offsets after remap.
    text = "Dr. John Smith was admitted.\n\nJane Doe arrived later."
    # sentence bounds (verified separately): first sentence covers "Dr. ...
    # admitted.", second covers "Jane Doe arrived later."
    bounds = sentence_offsets(text)
    assert len(bounds) == 2
    s0, _ = bounds[0]
    s1, _ = bounds[1]

    # Simulate: pipeline finds "John Smith" in sent 0 (local offset 4..14)
    # and "Jane Doe" in sent 1 (local offset 0..8).
    fake = _FakeHFPipeline([
        [{"start": 4, "end": 14, "entity_group": "NAME", "score": 0.99}],
        [{"start": 0, "end": 8, "entity_group": "NAME", "score": 0.95}],
    ])

    spans = _predict_by_sentence(fake, text, source="huggingface_ner:fake", entity_map={})

    assert len(spans) == 2

    # First span: sentence-local 4..14 + s0
    assert spans[0].start == s0 + 4
    assert spans[0].end == s0 + 14
    assert text[spans[0].start : spans[0].end] == "John Smith"
    assert spans[0].label == "NAME"

    # Second span: sentence-local 0..8 + s1
    assert spans[1].start == s1 + 0
    assert spans[1].end == s1 + 8
    assert text[spans[1].start : spans[1].end] == "Jane Doe"

    # Pipeline saw exactly the two sentence texts, not the full doc.
    assert len(fake.calls) == 2
    assert "Dr. John Smith" in fake.calls[0]
    assert fake.calls[1].startswith("Jane Doe")


# ---------------------------------------------------------------------------
# Sliding-window chunked inference
# ---------------------------------------------------------------------------


class _FakeWordTokenizer:
    """Whitespace tokenizer that returns offset_mapping. Lets us drive
    ``_predict_by_chunks`` without pulling in a real Transformers tokenizer."""

    def __init__(self, model_max_length: int):
        self.model_max_length = model_max_length

    def num_special_tokens_to_add(self, pair: bool = False) -> int:
        return 2

    def __call__(self, text: str, **_kwargs):
        offsets: list[tuple[int, int]] = []
        i = 0
        n = len(text)
        while i < n:
            while i < n and text[i].isspace():
                i += 1
            if i >= n:
                break
            j = i
            while j < n and not text[j].isspace():
                j += 1
            offsets.append((i, j))
            i = j
        return {"offset_mapping": offsets}


class _FakeChunkPipeline:
    """Pipeline stub that records each substring it sees and returns
    a per-call list of pre-canned predictions (sub-window-local offsets)."""

    def __init__(self, tokenizer, per_call: list[list[dict]]):
        self.tokenizer = tokenizer
        self._per_call = list(per_call)
        self.calls: list[str] = []

    def __call__(self, text: str):
        self.calls.append(text)
        if not self._per_call:
            return []
        return self._per_call.pop(0)


def test_predict_by_chunks_covers_full_doc_and_remaps_offsets():
    """A doc longer than the model window must be sliced into overlapping
    sub-windows; predictions in *every* sub-window are remapped back to
    document coords."""
    from pypedeid.pipes.huggingface_ner.pipe import (
        CHUNK_STRIDE_TOKENS,
        _predict_by_chunks,
    )

    # Build a doc with many word-tokens so chunking actually triggers.
    # window_tokens = max_tokens - 2 (special) - 2 (margin) = max_tokens - 4.
    # Pick max_tokens so window_tokens > CHUNK_STRIDE_TOKENS (else step <= 0).
    max_tokens = CHUNK_STRIDE_TOKENS + 10  # window_tokens = stride + 6
    n_words = (CHUNK_STRIDE_TOKENS + 6) * 3
    words = [f"w{i:03d}" for i in range(n_words)]
    text = " ".join(words)

    tokenizer = _FakeWordTokenizer(model_max_length=max_tokens)

    # Each sub-window call: pretend we found a NAME at local offsets 0..4
    # (i.e. the first word — words are 4 chars: "w000"). We pre-fill enough
    # call responses to cover all chunks.
    fake = _FakeChunkPipeline(
        tokenizer,
        per_call=[[{"start": 0, "end": 4, "entity_group": "NAME", "score": 0.9}]] * 20,
    )

    spans = _predict_by_chunks(fake, text, source="hf:fake", entity_map={}, max_tokens=max_tokens)

    # We must have seen multiple chunks (full coverage, no truncation).
    assert len(fake.calls) >= 2
    # Last chunk must reach to the end of the document.
    last_chunk = fake.calls[-1]
    assert text.endswith(last_chunk)
    # Every span maps to a real word boundary in the doc text.
    for span in spans:
        assert text[span.start : span.end] in words
        assert span.label == "NAME"


def test_predict_by_chunks_short_doc_runs_one_pass():
    """If the doc fits in one window, only a single pipeline call is made."""
    from pypedeid.pipes.huggingface_ner.pipe import _predict_by_chunks

    text = "Dr. John Smith was admitted today."
    tokenizer = _FakeWordTokenizer(model_max_length=128)
    fake = _FakeChunkPipeline(
        tokenizer,
        per_call=[[{"start": 4, "end": 14, "entity_group": "NAME", "score": 0.99}]],
    )

    spans = _predict_by_chunks(fake, text, source="hf:fake", entity_map={}, max_tokens=128)

    assert len(fake.calls) == 1
    assert len(spans) == 1
    assert text[spans[0].start : spans[0].end] == "John Smith"


