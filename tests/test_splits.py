from __future__ import annotations

from pypedeid.domain import AnnotatedDocument, Document, EntitySpan
from pypedeid.transform.ops import run_transform_pipeline, strip_split_metadata
from pypedeid.transform.splits import reassign_splits


def test_reassign_splits_counts_and_order() -> None:
    docs = [
        AnnotatedDocument(document=Document(id=str(i), text="x", metadata={"split": "old"}), spans=[])
        for i in range(10)
    ]
    out = reassign_splits(
        docs,
        {"train": 0.7, "valid": 0.15, "test": 0.15},
        seed=0,
    )
    assert len(out) == 10
    assert [d.document.id for d in out] == [str(i) for i in range(10)]
    by_split: dict[str, int] = {}
    for d in out:
        by_split[d.document.metadata["split"]] = by_split.get(d.document.metadata["split"], 0) + 1
    assert by_split["train"] == 7
    # Remainder from 0.15×10 goes to one of valid/test by tie-break
    assert by_split["valid"] + by_split["test"] == 3
    assert sorted((by_split["valid"], by_split["test"])) == [1, 2]


def test_reassign_deploy_four_way() -> None:
    docs = [
        AnnotatedDocument(document=Document(id=str(i), text="x", metadata={}), spans=[])
        for i in range(100)
    ]
    out = reassign_splits(
        docs,
        {"train": 0.7, "valid": 0.1, "test": 0.1, "deploy": 0.1},
        seed=1,
    )
    assert len({d.document.metadata["split"] for d in out}) == 4
    assert sum(1 for d in out if d.document.metadata["split"] == "deploy") == 10


def test_pipeline_resplit_last() -> None:
    docs = [
        AnnotatedDocument(
            document=Document(id="a", text="x", metadata={"split": "train"}),
            spans=[EntitySpan(start=0, end=1, label="NAME")],
        )
    ]
    out = run_transform_pipeline(
        docs,
        boost_label="NAME",
        boost_extra_copies=1,
        resplit={"train": 1.0},
        seed=0,
    )
    assert len(out) == 2
    assert all(d.document.metadata.get("split") == "train" for d in out)


def test_strip_split_metadata() -> None:
    docs = [
        AnnotatedDocument(document=Document(id="1", text="x", metadata={"split": "train", "k": 1}), spans=[]),
    ]
    out = strip_split_metadata(docs)
    assert "split" not in out[0].document.metadata
    assert out[0].document.metadata.get("k") == 1


def test_pipeline_resplit_then_drop_split() -> None:
    docs = [
        AnnotatedDocument(document=Document(id="a", text="x", metadata={}), spans=[]),
    ]
    out = run_transform_pipeline(
        docs,
        resplit={"train": 0.5, "valid": 0.5},
        strip_splits=True,
        seed=0,
    )
    assert len(out) == 1
    assert "split" not in out[0].document.metadata
