from __future__ import annotations

from pathlib import Path

from pypedeid.compose import compose_corpora, flatten_annotated_document
from pypedeid.compose.strategies import compose_interleave, compose_proportional
from pypedeid.domain import AnnotatedDocument, Document
from pypedeid.ingest.brat import load_brat_corpus_with_splits
from pypedeid.transform.splits import proportional_integer_counts


def test_proportional_integer_counts_sums() -> None:
    assert sum(proportional_integer_counts(10, [1.0, 1.0])) == 10
    assert proportional_integer_counts(10, [2.0, 1.0]) == [7, 3]
    assert proportional_integer_counts(0, [1.0, 2.0]) == [0, 0]
    assert proportional_integer_counts(5, []) == []


def test_flatten_strips_split_and_provenance() -> None:
    ad = AnnotatedDocument(
        document=Document(id="train__n1", text="hi", metadata={"split": "train", "x": 1}),
        spans=[],
    )
    flat = flatten_annotated_document(
        ad,
        new_id="s0__train__n1",
        source_index=0,
        provenance=True,
    )
    assert "split" not in flat.document.metadata
    assert flat.document.metadata["compose_original_split"] == "train"
    assert flat.document.metadata["compose_original_id"] == "train__n1"


def test_compose_merge_order_and_shuffle() -> None:
    a = [
        AnnotatedDocument(document=Document(id="a1", text="a", metadata={"split": "train"}), spans=[]),
    ]
    b = [
        AnnotatedDocument(document=Document(id="b1", text="b", metadata={"split": "valid"}), spans=[]),
    ]
    m = compose_corpora([a, b], strategy="merge", shuffle=False, id_prefix="p")
    assert [d.document.id for d in m] == ["p0__a1", "p1__b1"]
    assert all("split" not in d.document.metadata for d in m)

    sh = compose_corpora([a, b], strategy="merge", shuffle=True, seed=99, id_prefix="p")
    assert {d.document.id for d in sh} == {"p0__a1", "p1__b1"}


def test_compose_interleave() -> None:
    a = [AnnotatedDocument(document=Document(id=f"a{i}", text="a", metadata={}), spans=[]) for i in range(2)]
    b = [AnnotatedDocument(document=Document(id="b0", text="b", metadata={}), spans=[])]
    flat_a = [flatten_annotated_document(x, new_id=f"x0__{x.document.id}", source_index=0) for x in a]
    flat_b = [flatten_annotated_document(x, new_id=f"x1__{x.document.id}", source_index=1) for x in b]
    out = compose_interleave([flat_a, flat_b])
    assert [d.document.id for d in out] == ["x0__a0", "x1__b0", "x0__a1"]


def test_compose_proportional_counts() -> None:
    a = [AnnotatedDocument(document=Document(id=f"a{i}", text="a", metadata={}), spans=[]) for i in range(10)]
    b = [AnnotatedDocument(document=Document(id=f"b{i}", text="b", metadata={}), spans=[]) for i in range(10)]
    flat = [
        [flatten_annotated_document(x, new_id=f"s0__{x.document.id}", source_index=0) for x in a],
        [flatten_annotated_document(x, new_id=f"s1__{x.document.id}", source_index=1) for x in b],
    ]
    out = compose_proportional(flat, [1.0, 1.0], target_documents=10, seed=0)
    assert len(out) == 10
    from_s0 = sum(1 for d in out if d.document.id.startswith("s0__"))
    from_s1 = sum(1 for d in out if d.document.id.startswith("s1__"))
    assert from_s0 + from_s1 == 10
    assert from_s0 == 5 and from_s1 == 5


def test_brat_corpus_unflattened_via_loader(tmp_path: Path) -> None:
    root = tmp_path / "corp"
    for name in ("train", "valid"):
        d = root / name
        d.mkdir(parents=True)
        (d / f"{name}_1.txt").write_text("hello", encoding="utf-8")
        (d / f"{name}_1.ann").write_text("", encoding="utf-8")
    docs = load_brat_corpus_with_splits(root)
    assert all("split" in d.document.metadata for d in docs)
    out = compose_corpora([docs], strategy="merge", id_prefix="c")
    assert len(out) == 2
    assert all("split" not in d.document.metadata for d in out)
    assert {d.document.metadata.get("compose_original_split") for d in out} == {"train", "valid"}
