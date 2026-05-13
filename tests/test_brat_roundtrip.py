from __future__ import annotations

from pathlib import Path

from pypedeid.domain import AnnotatedDocument, Document, EntitySpan
from pypedeid.ingest.brat import load_brat_directory
from pypedeid.ingest.sink import write_annotated_corpus


def test_brat_flat_roundtrip_text_and_spans(tmp_path: Path) -> None:
    docs = [
        AnnotatedDocument(
            document=Document(id="n1", text="CALVERT HOSPITAL here", metadata={}),
            spans=[EntitySpan(start=0, end=16, label="HOSPITAL", source="brat")],
        )
    ]
    out = tmp_path / "brat"
    write_annotated_corpus(docs, brat_dir=out)
    back = load_brat_directory(out)
    assert len(back) == 1
    assert back[0].document.text == docs[0].document.text
    assert len(back[0].spans) == 1
    assert back[0].spans[0].label == "HOSPITAL"
    assert back[0].spans[0].start == 0
    assert back[0].spans[0].end == 16


def test_brat_corpus_split_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "corp"
    docs = [
        AnnotatedDocument(
            document=Document(id="train__a", text="aa", metadata={"split": "train"}),
            spans=[],
        ),
        AnnotatedDocument(
            document=Document(id="valid__b", text="bb", metadata={"split": "valid"}),
            spans=[],
        ),
    ]
    write_annotated_corpus(docs, brat_corpus=root)
    assert (root / "train" / "a.txt").read_text() == "aa"
    assert (root / "valid" / "b.txt").read_text() == "bb"
    from pypedeid.ingest.brat import load_brat_corpus_with_splits

    loaded = load_brat_corpus_with_splits(root)
    assert {d.document.text for d in loaded} == {"aa", "bb"}
    by_id = {d.document.id: d for d in loaded}
    assert by_id["train__a"].document.metadata.get("split") == "train"
