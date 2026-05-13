from __future__ import annotations

from pathlib import Path

from pypedeid.ingest.sources import load_annotated_corpus


def test_load_annotated_corpus_jsonl(tmp_path: Path) -> None:
    p = tmp_path / "d.jsonl"
    p.write_text(
        '{"document": {"id": "a", "text": "hi", "metadata": {}}, '
        '"spans": [{"start": 0, "end": 2, "label": "X"}]}\n',
        encoding="utf-8",
    )
    docs = load_annotated_corpus(jsonl=p)
    assert len(docs) == 1
    assert docs[0].spans[0].label == "X"


def test_load_annotated_corpus_requires_one_source() -> None:
    try:
        load_annotated_corpus()
    except ValueError:
        return
    raise AssertionError("expected ValueError")
