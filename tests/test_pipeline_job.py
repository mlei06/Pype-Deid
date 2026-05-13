from __future__ import annotations

from pathlib import Path

from pypedeid.domain import AnnotatedDocument
from pypedeid.ingest.sink import write_annotated_corpus
from pypedeid.ingest.sources import load_annotated_corpus
from pypedeid.pipeline.job import DatasetJob
from pypedeid.transform.ops import run_transform_pipeline


def test_dataset_job_load_transform_sink(tmp_path: Path) -> None:
    inp = tmp_path / "in.jsonl"
    inp.write_text(
        '{"document": {"id": "a", "text": "x", "metadata": {"split": "train"}}, "spans": []}\n',
        encoding="utf-8",
    )
    outp = tmp_path / "out.jsonl"

    def load():
        return load_annotated_corpus(jsonl=inp)

    def step(docs: list[AnnotatedDocument]):
        return run_transform_pipeline(docs, strip_splits=True)

    def sink(docs: list[AnnotatedDocument]):
        write_annotated_corpus(docs, jsonl=outp)

    r = DatasetJob(load=load, steps=[step], sinks=[sink]).run()
    assert len(r.documents) == 1
    assert "split" not in r.documents[0].document.metadata
    back = load_annotated_corpus(jsonl=outp)
    assert "split" not in back[0].document.metadata
