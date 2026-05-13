"""AnnotatedDocument → HF Dataset + label alignment."""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from pypedeid.domain import AnnotatedDocument, EntitySpan
from pypedeid.pipes.detector_label_mapping import remap_span_labels

if TYPE_CHECKING:
    import datasets as hf_datasets
    from transformers import PreTrainedTokenizerFast

    from pypedeid.training.config import TrainingConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Label derivation
# ---------------------------------------------------------------------------


def derive_label_list(
    docs: Iterable[AnnotatedDocument],
    override: list[str] | None,
) -> list[str]:
    """Return ordered BIO list [O, B-L1, I-L1, B-L2, I-L2, ...].

    O is always index 0. Labels are sorted for determinism.
    """
    if override is not None:
        canonical = sorted(override)
    else:
        found: set[str] = set()
        for doc in docs:
            for span in doc.spans:
                found.add(span.label)
        canonical = sorted(found)

    bio: list[str] = ["O"]
    for label in canonical:
        bio.append(f"B-{label}")
        bio.append(f"I-{label}")
    return bio


# ---------------------------------------------------------------------------
# Subword alignment
# ---------------------------------------------------------------------------


def _find_covering_span(tok_start: int, spans: list[EntitySpan]) -> EntitySpan | None:
    """Return the longest span that covers tok_start, or None."""
    best: EntitySpan | None = None
    for span in spans:
        if span.start <= tok_start < span.end:
            if best is None or (span.end - span.start) > (best.end - best.start):
                best = span
    return best


def tokenize_and_align(
    doc: AnnotatedDocument,
    tokenizer: "PreTrainedTokenizerFast",
    bio_label_to_id: dict[str, int],
    max_length: int,
) -> dict[str, list[int]]:
    """Return {input_ids, attention_mask, labels} with subword-aligned labels.

    Algorithm (word-level, using fast tokenizer word_ids()):
    - Special tokens (word_id is None) → -100
    - Continuation subwords (same word_id as previous token) → -100
    - First subword of each word:
        - No span covers the word → O
        - Span covers the word and word starts at/before span.start → B-<label>
        - Span covers the word and word starts after span.start → I-<label>
    """
    from pypedeid.training.errors import SlowTokenizerUnsupported

    if not tokenizer.is_fast:
        raise SlowTokenizerUnsupported(
            f"{tokenizer.__class__.__name__} is not a fast tokenizer. "
            "Only fast tokenizers (which expose word_ids()) are supported."
        )

    text = doc.document.text
    spans = sorted(doc.spans, key=lambda s: (s.start, -(s.end - s.start)))

    enc = tokenizer(
        text,
        truncation=True,
        max_length=max_length,
        return_offsets_mapping=True,
    )

    word_ids: list[int | None] = enc.word_ids()
    offset_mapping: list[tuple[int, int]] = enc["offset_mapping"]

    if len(enc["input_ids"]) == max_length:
        meta = doc.document.metadata or {}
        if meta.get("sentence_index") is not None:
            logger.warning(
                "Sentence unit %r exceeded max_length=%d after tokenization; tail was "
                "truncated and entity labels beyond the cut may be lost. "
                "Raise hyperparams.max_length or split very long sentences separately.",
                doc.document.id,
                max_length,
            )
        else:
            logger.warning(
                "Document %r was truncated at %d tokens; tail may have lost entity labels.",
                doc.document.id,
                max_length,
            )

    label_ids: list[int] = []
    prev_word_id: int | None = None
    o_id = bio_label_to_id.get("O", 0)

    for i, word_id in enumerate(word_ids):
        if word_id is None:
            label_ids.append(-100)
        elif word_id == prev_word_id:
            # Continuation subword of the same original word → loss ignored
            label_ids.append(-100)
        else:
            # First subword of a new original word
            tok_start, _tok_end = offset_mapping[i]
            covering = _find_covering_span(tok_start, spans)

            if covering is None:
                label_ids.append(o_id)
            elif tok_start <= covering.start:
                # This word starts at or before the span start → first word of span
                label_ids.append(bio_label_to_id.get(f"B-{covering.label}", o_id))
            else:
                # This word is inside the span but not the first word
                label_ids.append(bio_label_to_id.get(f"I-{covering.label}", o_id))

        prev_word_id = word_id

    return {
        "input_ids": enc["input_ids"],
        "attention_mask": enc["attention_mask"],
        "labels": label_ids,
    }


# ---------------------------------------------------------------------------
# Label remapping
# ---------------------------------------------------------------------------


def _remap_doc(doc: AnnotatedDocument, remap: dict[str, str]) -> AnnotatedDocument:
    """Return a new AnnotatedDocument with span labels rewritten via remap."""
    return AnnotatedDocument(
        document=doc.document,
        spans=remap_span_labels(list(doc.spans), remap),
    )


# ---------------------------------------------------------------------------
# Dataset builder
# ---------------------------------------------------------------------------


def build_hf_datasets(
    cfg: "TrainingConfig",
    corpora_dir: Path,
    tokenizer: "PreTrainedTokenizerFast",
) -> "tuple[hf_datasets.Dataset, hf_datasets.Dataset | None, list[str]]":
    """Return (train_ds, eval_ds_or_None, bio_labels).

    Loads documents, derives label space, tokenizes everything.
    """
    import datasets as hf_datasets

    from pypedeid.dataset_store import load_dataset_documents
    from pypedeid.training.errors import EmptyDataset, NoLabelsFound

    # Load documents
    train_docs = load_dataset_documents(corpora_dir, cfg.train_dataset)
    if not train_docs:
        raise EmptyDataset(f"Dataset {cfg.train_dataset!r} has no documents.")

    for extra_name in cfg.extra_train_datasets:
        extra = load_dataset_documents(corpora_dir, extra_name)
        if not extra:
            logger.warning("Extra train dataset %r has no documents; skipping.", extra_name)
        else:
            train_docs = list(train_docs) + extra
            logger.info("Merged %d docs from extra train dataset %r.", len(extra), extra_name)

    eval_docs: list[AnnotatedDocument] | None = None

    if cfg.eval_dataset is not None:
        eval_docs = load_dataset_documents(corpora_dir, cfg.eval_dataset)
        if cfg.eval_fraction is not None:
            logger.warning(
                "Both eval_dataset and eval_fraction are set; using eval_dataset and ignoring eval_fraction."
            )
    elif cfg.eval_fraction is not None:
        rng = random.Random(cfg.hyperparams.seed)
        shuffled = list(train_docs)
        rng.shuffle(shuffled)
        split = int(len(shuffled) * (1.0 - cfg.eval_fraction))
        train_docs = shuffled[:split]
        eval_docs = shuffled[split:]
        if not train_docs:
            raise EmptyDataset("After eval_fraction split, train set is empty.")

    # Apply label remap to all docs before deriving label space
    if cfg.label_remap:
        train_docs = [_remap_doc(doc, cfg.label_remap) for doc in train_docs]
        if eval_docs:
            eval_docs = [_remap_doc(doc, cfg.label_remap) for doc in eval_docs]

    # Derive label space from all available documents
    all_docs: list[AnnotatedDocument] = list(train_docs)
    if eval_docs:
        all_docs.extend(eval_docs)

    bio_labels = derive_label_list(all_docs, cfg.labels)
    if bio_labels == ["O"]:
        raise NoLabelsFound(
            "No PHI labels found in the dataset. "
            "Ensure the dataset has annotated spans before training."
        )

    bio_label_to_id: dict[str, int] = {label: i for i, label in enumerate(bio_labels)}
    max_length = cfg.hyperparams.max_length

    def _encode(docs: list[AnnotatedDocument]) -> list[dict[str, Any]]:
        examples = _prepare_training_units(docs, cfg.segmentation)
        return [tokenize_and_align(d, tokenizer, bio_label_to_id, max_length) for d in examples]

    train_ds = hf_datasets.Dataset.from_list(_encode(train_docs))
    eval_ds = hf_datasets.Dataset.from_list(_encode(eval_docs)) if eval_docs else None

    return train_ds, eval_ds, bio_labels


def _prepare_training_units(
    docs: list[AnnotatedDocument],
    segmentation: str,
) -> list[AnnotatedDocument]:
    """Return the per-example AnnotatedDocuments to feed the tokenizer.

    ``truncate`` passes documents through untouched (Trainer sees one example
    per document; the tokenizer truncates at max_length).
    ``sentence`` splits each document into per-sentence sub-documents via
    pypedeid.training.segmentation.split_doc_into_sentences; each
    sentence becomes its own training example.
    """
    if segmentation == "truncate":
        return list(docs)
    if segmentation == "sentence":
        from pypedeid.training.segmentation import split_doc_into_sentences

        units: list[AnnotatedDocument] = []
        for doc in docs:
            sub = split_doc_into_sentences(doc)
            if not sub:
                logger.warning(
                    "Document %r produced no sentences; skipping.", doc.document.id
                )
                continue
            units.extend(sub)
        if not units:
            from pypedeid.training.errors import EmptyDataset

            raise EmptyDataset(
                "Sentence segmentation produced zero examples. "
                "All documents may be whitespace-only."
            )
        return units
    raise ValueError(f"Unknown segmentation mode: {segmentation!r}")
