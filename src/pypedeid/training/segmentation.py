"""Sentence segmentation for training and inference.

Provides a dependency-free sentence splitter with clinical-text heuristics
(abbreviation awareness, paragraph breaks) and helpers for splitting an
``AnnotatedDocument`` into per-sentence sub-documents with spans remapped
to sentence-local offsets.

Spans that cross a sentence boundary are *clipped* to the sentence that
contains them — clinical splitter errors lose partial recall, not whole
entities. Clipped spans of length < 1 char are dropped.
"""

from __future__ import annotations

import logging
from typing import Iterable

from pypedeid.domain import AnnotatedDocument, Document, EntitySpan

logger = logging.getLogger(__name__)


# Lowercased tokens that look like sentence-ending `.` but are abbreviations.
# Keep conservative — only truly common clinical / generic abbreviations go here.
_ABBREVIATIONS: frozenset[str] = frozenset({
    "dr", "mr", "mrs", "ms", "pt", "sr", "jr",
    "vs", "etc", "approx", "cf", "e.g", "i.e",
    "mg", "ml", "kg", "mcg", "mm", "cm", "hg",
    "st", "no", "dept", "hosp", "univ", "inc", "co",
    "am", "pm",
})


def _is_abbreviation(text: str, period_idx: int, sentence_start: int) -> bool:
    """Return True if the `.` at period_idx is part of a known abbreviation.

    Looks back from period_idx to the start of the preceding alphabetic word
    (bounded by sentence_start). Single capital letters (initials like "J.")
    are also treated as abbreviations.
    """
    j = period_idx - 1
    while j >= sentence_start and text[j].isalpha():
        j -= 1
    word = text[j + 1 : period_idx]
    if not word:
        return False
    lower = word.lower()
    if lower in _ABBREVIATIONS:
        return True
    # Single capital letter initial (e.g. "J.")
    if len(word) == 1 and word.isalpha():
        return True
    return False


def sentence_offsets(text: str) -> list[tuple[int, int]]:
    """Return ``(start, end)`` character offsets of each sentence in ``text``.

    Boundaries:
    - Blank line (``\\n\\n+``) → hard paragraph break.
    - Sentence-final punctuation ``.!?`` (optionally followed by closing
      quotes/brackets) when the next non-space char is an uppercase letter,
      digit, bullet, or newline — and the preceding word is not a known
      abbreviation.

    Whitespace-only regions between sentences are excluded from the
    returned ranges.
    """
    n = len(text)
    if n == 0:
        return []

    offsets: list[tuple[int, int]] = []
    i = 0
    while i < n:
        # Skip leading whitespace
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            break
        start = i
        end = _find_sentence_end(text, start)
        # Trim trailing whitespace from the sentence extent
        real_end = end
        while real_end > start and text[real_end - 1].isspace():
            real_end -= 1
        if real_end > start:
            offsets.append((start, real_end))
        i = end
    return offsets


def _find_sentence_end(text: str, start: int) -> int:
    """Return the index just past the end of the sentence starting at ``start``.

    ``text[start]`` is assumed to be a non-whitespace character.
    """
    n = len(text)
    i = start
    while i < n:
        ch = text[i]

        if ch == "\n":
            # Count consecutive newlines — 2+ is a paragraph break.
            j = i
            while j < n and text[j] == "\n":
                j += 1
            if j - i >= 2:
                return i  # hard break at the first newline
            # Single newline — treat as soft break, continue within sentence.
            i = j
            continue

        if ch in ".!?":
            if ch == "." and _is_abbreviation(text, i, start):
                i += 1
                continue
            # Consume punctuation cluster + optional closing quotes/brackets.
            j = i + 1
            while j < n and text[j] in ".!?\"')]":
                j += 1
            # Look ahead past spaces/tabs.
            k = j
            while k < n and text[k] in " \t":
                k += 1
            if k >= n:
                return j
            nxt = text[k]
            if nxt == "\n":
                # Newline after punct: if blank line follows, next iter handles.
                return j
            if nxt.isupper() or nxt.isdigit() or nxt in "-*•":
                return j
            # Not a confident boundary — keep scanning.
            i = j
            continue

        i += 1
    return n


def split_doc_into_sentences(doc: AnnotatedDocument) -> list[AnnotatedDocument]:
    """Split ``doc`` into one ``AnnotatedDocument`` per sentence.

    Sentence-local span offsets are produced (0-indexed within each sentence).
    Spans that cross a sentence boundary are clipped to the containing
    sentence; clipped spans of length < 1 char are dropped. Each sub-doc's
    ``document.metadata`` carries ``parent_doc_id`` and ``sentence_offset``
    so predictions can be remapped back to document coordinates.
    """
    text = doc.document.text
    bounds = sentence_offsets(text)

    if not bounds:
        # Entirely whitespace (or empty) — return empty list; callers skip.
        return []

    result: list[AnnotatedDocument] = []
    for sent_idx, (s, e) in enumerate(bounds):
        sub_text = text[s:e]
        sub_spans: list[EntitySpan] = []
        for span in doc.spans:
            # Clip to sentence bounds
            cs = max(span.start, s)
            ce = min(span.end, e)
            if cs >= ce:
                continue  # no overlap or zero-length after clip
            sub_spans.append(
                EntitySpan(
                    start=cs - s,
                    end=ce - s,
                    label=span.label,
                    confidence=span.confidence,
                    source=span.source,
                )
            )
        sub_doc = Document(
            id=f"{doc.document.id}#s{sent_idx}",
            text=sub_text,
            metadata={
                **doc.document.metadata,
                "parent_doc_id": doc.document.id,
                "sentence_offset": s,
                "sentence_index": sent_idx,
            },
        )
        result.append(AnnotatedDocument(document=sub_doc, spans=sub_spans))
    return result


def split_docs(docs: Iterable[AnnotatedDocument]) -> list[AnnotatedDocument]:
    """Flatten an iterable of documents into sentence-level sub-documents."""
    out: list[AnnotatedDocument] = []
    for doc in docs:
        out.extend(split_doc_into_sentences(doc))
    return out
