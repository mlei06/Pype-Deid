"""Aggregate statistics over a collection of annotated documents."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from itertools import combinations
from typing import Any

from pydantic import BaseModel, Field

from pypedeid.domain import AnnotatedDocument, EntitySpan


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _stdev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _summary_numeric(xs: list[float]) -> dict[str, float]:
    if not xs:
        return {"mean": 0.0, "min": 0.0, "max": 0.0, "std": 0.0}
    return {
        "mean": round(_mean(xs), 4),
        "min": round(min(xs), 4),
        "max": round(max(xs), 4),
        "std": round(_stdev(xs), 4),
    }


def _documents_by_span_count(spd_ints: list[int]) -> dict[str, int]:
    """How many documents have exactly k spans (k=0..20), or 21+ for the tail."""
    raw: Counter[str] = Counter()
    for n in spd_ints:
        if n <= 20:
            raw[str(n)] += 1
        else:
            raw["21+"] += 1
    out: dict[str, int] = {}
    for i in range(21):
        k = str(i)
        if k in raw:
            out[k] = raw[k]
    if "21+" in raw:
        out["21+"] = raw["21+"]
    return out


def _span_length_histogram(lengths: list[int]) -> dict[str, int]:
    out: Counter[str] = Counter()
    for L in lengths:
        if L <= 0:
            out["0"] += 1
        elif L <= 10:
            out["1-10"] += 1
        elif L <= 20:
            out["11-20"] += 1
        elif L <= 50:
            out["21-50"] += 1
        elif L <= 100:
            out["51-100"] += 1
        else:
            out["101+"] += 1
    return dict(out)


def rough_token_count(text: str) -> int:
    return len(text.split())


def spans_overlap(a: EntitySpan, b: EntitySpan) -> bool:
    return max(a.start, b.start) < min(a.end, b.end)


class DatasetAnalytics(BaseModel):
    """Summary analytics for one dataset (or any list of annotated documents)."""

    document_count: int
    total_spans: int
    unique_label_count: int
    label_counts: dict[str, int] = Field(description="Span counts per entity label")
    character_length: dict[str, Any] = Field(description="Per-document text length (characters)")
    token_count_estimate: dict[str, Any] = Field(
        description="Whitespace token counts per document (rough, not clinical tokenizer)"
    )
    spans_per_document: dict[str, Any]
    documents_by_span_count: dict[str, int] = Field(
        description="Document counts by number of spans (keys '0'..'20', plus '21+' for longer notes)"
    )
    span_character_length: dict[str, Any] = Field(description="Per-span length in characters")
    span_length_histogram: dict[str, int]
    documents_with_overlapping_spans: int
    overlapping_span_pairs: int
    label_cooccurrence: dict[str, int] = Field(
        description="Unordered label pairs co-occurring in the same document (key 'A|B' with A<=B)"
    )


def compute_dataset_analytics(docs: list[AnnotatedDocument]) -> DatasetAnalytics:
    char_lens: list[float] = []
    token_lens: list[float] = []
    spd: list[float] = []
    span_char_lens: list[float] = []

    label_counter: Counter[str] = Counter()
    docs_with_overlap = 0
    overlap_pairs = 0
    cooc: defaultdict[str, int] = defaultdict(int)
    total_spans = 0

    for ad in docs:
        text = ad.document.text
        char_lens.append(float(len(text)))
        token_lens.append(float(rough_token_count(text)))
        spans = ad.spans
        n_spans = len(spans)
        spd.append(float(n_spans))
        total_spans += n_spans

        for s in spans:
            label_counter[s.label] += 1
            span_char_lens.append(float(s.end - s.start))

        local_overlap = False
        for i, a in enumerate(spans):
            for b in spans[i + 1 :]:
                if spans_overlap(a, b):
                    overlap_pairs += 1
                    local_overlap = True
        if local_overlap:
            docs_with_overlap += 1

        labels_in_doc = sorted(set(s.label for s in spans))
        for a, b in combinations(labels_in_doc, 2):
            cooc[f"{a}|{b}"] += 1

    span_len_ints = [int(x) for x in span_char_lens]
    spd_ints = [int(x) for x in spd]

    return DatasetAnalytics(
        document_count=len(docs),
        total_spans=total_spans,
        unique_label_count=len(label_counter),
        label_counts=dict(sorted(label_counter.items(), key=lambda x: (-x[1], x[0]))),
        character_length=_summary_numeric(char_lens),
        token_count_estimate=_summary_numeric(token_lens),
        spans_per_document=_summary_numeric(spd),
        documents_by_span_count=_documents_by_span_count(spd_ints),
        span_character_length=_summary_numeric(span_char_lens),
        span_length_histogram=_span_length_histogram(span_len_ints),
        documents_with_overlapping_spans=docs_with_overlap,
        overlapping_span_pairs=overlap_pairs,
        label_cooccurrence=dict(sorted(cooc.items(), key=lambda x: (-x[1], x[0]))),
    )


#: Metadata bucket for documents without a non-empty string ``metadata["split"]``.
#: Matches filter/query conventions in :func:`filter_documents_by_split_query`.
UNSPLIT_BUCKET = "(none)"


def _order_split_count_keys(counts: dict[str, int]) -> dict[str, int]:
    """Stable display order: known splits first, then other names, ``(none)`` last."""
    preferred = ("train", "valid", "dev", "test", "deploy")
    out: dict[str, int] = {}
    for k in preferred:
        if k in counts:
            out[k] = counts[k]
    for k in sorted(x for x in counts if x not in preferred and x != UNSPLIT_BUCKET):
        out[k] = counts[k]
    if UNSPLIT_BUCKET in counts:
        out[UNSPLIT_BUCKET] = counts[UNSPLIT_BUCKET]
    return out


def compute_split_document_counts(docs: list[AnnotatedDocument]) -> dict[str, int]:
    """Count documents per ``metadata['split']``; invalid/missing split → ``(none)``."""
    raw: Counter[str] = Counter()
    for ad in docs:
        sp = ad.document.metadata.get("split")
        if isinstance(sp, str) and sp.strip():
            raw[sp.strip()] += 1
        else:
            raw[UNSPLIT_BUCKET] += 1
    return _order_split_count_keys(dict(raw))


def has_split_metadata(docs: list[AnnotatedDocument]) -> bool:
    """True if at least one document has a non-empty string ``metadata['split']``."""
    return any(
        isinstance(ad.document.metadata.get("split"), str) and ad.document.metadata.get("split", "").strip()
        for ad in docs
    )
