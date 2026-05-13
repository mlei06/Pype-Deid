from __future__ import annotations

from pypedeid.domain import AnnotatedDocument, Document, EntitySpan
from pypedeid.transform.ops import (
    apply_label_mapping,
    boost_docs_with_label,
    clone_annotated_document,
    filter_labels,
    get_work_and_rest,
    merge_rest_work,
    random_resize,
    run_transform_by_mode,
    run_transform_pipeline,
)


def test_clone_new_id() -> None:
    a = AnnotatedDocument(
        document=Document(id="1", text="ab", metadata={"k": 1}),
        spans=[EntitySpan(start=0, end=1, label="X")],
    )
    b = clone_annotated_document(a, "2")
    assert b.document.id == "2"
    assert b.document.text == "ab"
    assert b.spans[0].label == "X"


def test_filter_labels_drop() -> None:
    a = AnnotatedDocument(
        document=Document(id="1", text="xyz", metadata={}),
        spans=[
            EntitySpan(start=0, end=1, label="NAME"),
            EntitySpan(start=1, end=2, label="DATE"),
            EntitySpan(start=2, end=3, label="PHONE"),
        ],
    )
    out = filter_labels([a], drop=["DATE"])
    assert len(out[0].spans) == 2
    assert {s.label for s in out[0].spans} == {"NAME", "PHONE"}


def test_filter_labels_keep() -> None:
    a = AnnotatedDocument(
        document=Document(id="1", text="xyz", metadata={}),
        spans=[
            EntitySpan(start=0, end=1, label="NAME"),
            EntitySpan(start=1, end=2, label="DATE"),
            EntitySpan(start=2, end=3, label="PHONE"),
        ],
    )
    out = filter_labels([a], keep=["NAME"])
    assert len(out[0].spans) == 1
    assert out[0].spans[0].label == "NAME"


def test_filter_labels_noop() -> None:
    a = AnnotatedDocument(
        document=Document(id="1", text="x", metadata={}),
        spans=[EntitySpan(start=0, end=1, label="NAME")],
    )
    out = filter_labels([a])
    assert len(out[0].spans) == 1


def test_apply_label_mapping() -> None:
    a = AnnotatedDocument(
        document=Document(id="1", text="xy", metadata={}),
        spans=[EntitySpan(start=0, end=1, label="NAME"), EntitySpan(start=1, end=2, label="DATE")],
    )
    out = apply_label_mapping([a], {"NAME": "PATIENT"})
    assert out[0].spans[0].label == "PATIENT"
    assert out[0].spans[1].label == "DATE"


def test_random_resize_down_up() -> None:
    docs = [
        AnnotatedDocument(document=Document(id=str(i), text="x", metadata={}), spans=[])
        for i in range(10)
    ]
    d5 = random_resize(docs, 5, seed=1)
    assert len(d5) == 5
    ids = {x.document.id for x in d5}
    assert len(ids) == 5
    d15 = random_resize(docs, 15, seed=1)
    assert len(d15) == 15
    assert len({x.document.id for x in d15}) == 15


def test_boost_docs_with_label() -> None:
    a = AnnotatedDocument(
        document=Document(id="a", text="x", metadata={}),
        spans=[EntitySpan(start=0, end=1, label="NAME")],
    )
    b = AnnotatedDocument(document=Document(id="b", text="y", metadata={}), spans=[])
    out = boost_docs_with_label([a, b], "NAME", 1, id_prefix="z")
    assert len(out) == 3
    assert out[2].document.id.startswith("a__z")


def test_run_transform_pipeline_order() -> None:
    docs = [
        AnnotatedDocument(
            document=Document(id="1", text="x", metadata={}),
            spans=[EntitySpan(start=0, end=1, label="NAME")],
        )
    ]
    out = run_transform_pipeline(
        docs,
        label_mapping={"NAME": "P"},
        target_documents=1,
        boost_label="P",
        boost_extra_copies=1,
        seed=0,
    )
    assert len(out) == 2
    assert all(s.label == "P" for d in out for s in d.spans)


def test_get_work_and_rest_merge() -> None:
    docs = [
        AnnotatedDocument(
            document=Document(id="a", text="x", metadata={"split": "train"}),
            spans=[],
        ),
        AnnotatedDocument(
            document=Document(id="b", text="x", metadata={"split": "test"}),
            spans=[],
        ),
    ]
    work, rest = get_work_and_rest(docs, ["test"])
    assert [d.document.id for d in work] == ["b"]
    assert [d.document.id for d in rest] == ["a"]
    out = merge_rest_work(rest, work)
    assert [d.document.id for d in out] == ["a", "b"]


def test_run_transform_by_mode_schema_isolation() -> None:
    docs = [
        AnnotatedDocument(
            document=Document(id="1", text="ab", metadata={}),
            spans=[
                EntitySpan(start=0, end=1, label="X"),
                EntitySpan(start=1, end=2, label="Y"),
            ],
        ),
    ]
    out = run_transform_by_mode(
        docs,
        "schema",
        drop_labels=["X"],
    )
    assert len(out) == 1
    assert len(out[0].spans) == 1
    assert out[0].spans[0].label == "Y"


def test_run_transform_pipeline_drop_labels() -> None:
    docs = [
        AnnotatedDocument(
            document=Document(id="1", text="xy", metadata={}),
            spans=[
                EntitySpan(start=0, end=1, label="NAME"),
                EntitySpan(start=1, end=2, label="DATE"),
            ],
        )
    ]
    out = run_transform_pipeline(docs, drop_labels=["DATE"])
    assert len(out[0].spans) == 1
    assert out[0].spans[0].label == "NAME"
