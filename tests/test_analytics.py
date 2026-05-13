from __future__ import annotations

from pypedeid.analytics.stats import (
    compute_dataset_analytics,
    compute_split_document_counts,
    has_split_metadata,
    UNSPLIT_BUCKET,
)
from pypedeid.domain import AnnotatedDocument, Document, EntitySpan


def test_analytics_two_docs_overlap_and_cooc() -> None:
    a = AnnotatedDocument(
        document=Document(id="1", text="Hello world patient"),
        spans=[
            EntitySpan(start=0, end=5, label="X"),
            EntitySpan(start=3, end=8, label="Y"),  # overlaps first
        ],
    )
    b = AnnotatedDocument(
        document=Document(id="2", text="foo"),
        spans=[EntitySpan(start=0, end=3, label="X"),
               EntitySpan(start=0, end=3, label="Z")],  # same span two labels - overlap
    )
    stats = compute_dataset_analytics([a, b])
    assert stats.document_count == 2
    assert stats.total_spans == 4
    assert stats.documents_by_span_count["2"] == 2  # each doc has 2 spans
    assert stats.label_counts["X"] == 2
    assert stats.documents_with_overlapping_spans >= 1
    assert stats.overlapping_span_pairs >= 1
    assert "X|Y" in stats.label_cooccurrence or "X|Z" in stats.label_cooccurrence


def test_analytics_empty() -> None:
    s = compute_dataset_analytics([])
    assert s.document_count == 0
    assert s.total_spans == 0
    assert s.documents_by_span_count == {}


def test_documents_by_span_count_mixed() -> None:
    docs = [
        AnnotatedDocument(document=Document(id="a", text="x"), spans=[]),
        AnnotatedDocument(
            document=Document(id="b", text="y"),
            spans=[EntitySpan(start=0, end=1, label="L")],
        ),
        AnnotatedDocument(
            document=Document(id="c", text="z z"),
            spans=[
                EntitySpan(start=0, end=1, label="L"),
                EntitySpan(start=2, end=3, label="L"),
            ],
        ),
    ]
    s = compute_dataset_analytics(docs)
    assert s.documents_by_span_count["0"] == 1
    assert s.documents_by_span_count["1"] == 1
    assert s.documents_by_span_count["2"] == 1


def test_split_counts_and_flags() -> None:
    a = AnnotatedDocument(
        document=Document(id="1", text="a", metadata={"split": "train"}),
        spans=[],
    )
    b = AnnotatedDocument(
        document=Document(id="2", text="b", metadata={}),
        spans=[],
    )
    c = AnnotatedDocument(
        document=Document(id="3", text="c", metadata={"split": "  test  "}),
        spans=[],
    )
    d = [a, b, c]
    assert has_split_metadata(d) is True
    counts = compute_split_document_counts(d)
    assert counts.get("train") == 1
    assert counts.get("test") == 1
    assert counts[UNSPLIT_BUCKET] == 1
