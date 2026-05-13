"""Export AnnotatedDocument collections to training formats.

Supported formats:
- **conll**: CoNLL-2003 style (token per line, BIO tags), widely used for NER evaluation
- **spacy**: spaCy v3 DocBin binary, ready for ``spacy train``
- **huggingface**: HuggingFace token-classification JSONL (tokens + ner_tags)
- **jsonl**: Annotated JSONL — one ``AnnotatedDocument`` per line; round-trips
  through ``POST /datasets`` for re-registration.

All exporters accept ``list[AnnotatedDocument]`` and write to a directory.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pypedeid.domain import AnnotatedDocument, EntitySpan


# ---------------------------------------------------------------------------
# Tokenisation (whitespace-based, preserves offsets)
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"\S+")


def _tokenize(text: str) -> list[tuple[str, int, int]]:
    """Split *text* on whitespace, returning ``(token, start, end)`` triples."""
    return [(m.group(), m.start(), m.end()) for m in _TOKEN_RE.finditer(text)]


# ---------------------------------------------------------------------------
# BIO tagging
# ---------------------------------------------------------------------------


def _bio_tags(
    tokens: list[tuple[str, int, int]],
    spans: list[EntitySpan],
) -> list[str]:
    """Assign BIO tags to tokens based on character-level spans.

    A token is tagged B-<label> if it starts inside a span, I-<label> if it
    continues a previous B/I of the same label, otherwise O.
    """
    tags = ["O"] * len(tokens)
    if not spans:
        return tags

    sorted_spans = sorted(spans, key=lambda s: (s.start, -(s.end - s.start)))

    for span in sorted_spans:
        in_span = False
        for i, (_, t_start, t_end) in enumerate(tokens):
            if tags[i] != "O":
                continue
            # Token overlaps span if token starts before span ends and ends after span starts
            if t_start < span.end and t_end > span.start:
                if not in_span:
                    tags[i] = f"B-{span.label}"
                    in_span = True
                else:
                    tags[i] = f"I-{span.label}"
            else:
                if in_span:
                    break  # past the span

    return tags


# ---------------------------------------------------------------------------
# CoNLL export
# ---------------------------------------------------------------------------


def to_conll(docs: list[AnnotatedDocument]) -> str:
    """Convert documents to CoNLL-2003 format string.

    Each document is separated by ``-DOCSTART- -X- O O`` + blank line.
    Within a document, sentences are separated by blank lines (we treat the
    whole document as one sentence since clinical text doesn't always have
    clean sentence boundaries).
    """
    lines: list[str] = []
    for doc in docs:
        lines.append("-DOCSTART- -X- O O")
        lines.append("")
        tokens = _tokenize(doc.document.text)
        tags = _bio_tags(tokens, list(doc.spans))
        for (tok, _, _), tag in zip(tokens, tags):
            lines.append(f"{tok} {tag}")
        lines.append("")
    return "\n".join(lines)


def write_conll(
    docs: list[AnnotatedDocument],
    output_dir: Path,
    *,
    filename: str = "train.conll",
) -> Path:
    """Write documents to a CoNLL file in *output_dir*."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(to_conll(docs), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# spaCy DocBin export
# ---------------------------------------------------------------------------


def to_spacy_docbin(docs: list[AnnotatedDocument]) -> Any:
    """Convert documents to a spaCy ``DocBin``. Requires ``spacy``."""
    try:
        import spacy
        from spacy.tokens import DocBin
    except ImportError as exc:
        raise ImportError(
            "spaCy is required for DocBin export. "
            "Install with: pip install '.[ner]'"
        ) from exc

    nlp = spacy.blank("en")
    doc_bin = DocBin()

    for adoc in docs:
        spacy_doc = nlp.make_doc(adoc.document.text)
        ents = []
        for span in adoc.spans:
            sp = spacy_doc.char_span(span.start, span.end, label=span.label)
            if sp is not None:
                ents.append(sp)
        # Filter overlapping spans — spaCy doesn't allow them in .ents
        ents.sort(key=lambda e: (e.start_char, -(e.end_char - e.start_char)))
        filtered: list[Any] = []
        last_end = 0
        for ent in ents:
            if ent.start_char >= last_end:
                filtered.append(ent)
                last_end = ent.end_char
        spacy_doc.ents = filtered
        doc_bin.add(spacy_doc)

    return doc_bin


def write_spacy(
    docs: list[AnnotatedDocument],
    output_dir: Path,
    *,
    filename: str = "train.spacy",
) -> Path:
    """Write documents to a spaCy DocBin file in *output_dir*."""
    output_dir.mkdir(parents=True, exist_ok=True)
    doc_bin = to_spacy_docbin(docs)
    path = output_dir / filename
    doc_bin.to_disk(path)
    return path


# ---------------------------------------------------------------------------
# HuggingFace JSONL export
# ---------------------------------------------------------------------------


def _doc_to_hf_record(doc: AnnotatedDocument) -> dict[str, Any]:
    """Convert one document to a HuggingFace token-classification record."""
    tokens = _tokenize(doc.document.text)
    tags = _bio_tags(tokens, list(doc.spans))
    return {
        "id": doc.document.id,
        "tokens": [t for t, _, _ in tokens],
        "ner_tags": tags,
    }


def to_huggingface_jsonl(docs: list[AnnotatedDocument]) -> str:
    """Convert documents to HuggingFace JSONL (one JSON object per line)."""
    return "\n".join(
        json.dumps(_doc_to_hf_record(doc), ensure_ascii=False)
        for doc in docs
    )


def write_huggingface(
    docs: list[AnnotatedDocument],
    output_dir: Path,
    *,
    filename: str = "train.jsonl",
) -> Path:
    """Write documents to a HuggingFace JSONL file in *output_dir*."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(to_huggingface_jsonl(docs) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Annotated JSONL export (round-trips through POST /datasets)
# ---------------------------------------------------------------------------


def to_annotated_jsonl(docs: list[AnnotatedDocument]) -> str:
    """Serialize documents as one ``AnnotatedDocument`` JSON object per line."""
    return "\n".join(d.model_dump_json() for d in docs)


def export_annotated_jsonl(
    docs: list[AnnotatedDocument],
    output_dir: Path,
    *,
    filename: str = "train.jsonl",
) -> Path:
    """Write documents to an annotated JSONL file in *output_dir*."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(to_annotated_jsonl(docs) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Unified export interface
# ---------------------------------------------------------------------------

FORMATS = ("conll", "spacy", "huggingface", "jsonl")

_WRITERS = {
    "conll": write_conll,
    "spacy": write_spacy,
    "huggingface": write_huggingface,
    "jsonl": export_annotated_jsonl,
}


def export_training_data(
    docs: list[AnnotatedDocument],
    output_dir: Path,
    fmt: str,
    *,
    filename: str | None = None,
) -> Path:
    """Export documents to the specified training format.

    Returns the path to the written file.
    """
    if fmt not in _WRITERS:
        raise ValueError(f"Unknown format {fmt!r}. Supported: {', '.join(FORMATS)}")
    kwargs: dict[str, Any] = {}
    if filename:
        kwargs["filename"] = filename
    return _WRITERS[fmt](docs, output_dir, **kwargs)
