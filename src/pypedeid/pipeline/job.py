"""Composable load → transform steps → optional sinks."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from pypedeid.domain import AnnotatedDocument


@dataclass
class DatasetJobResult:
    documents: list[AnnotatedDocument]


@dataclass
class DatasetJob:
    """
    Run a linear pipeline: ``load`` produces documents, each ``step`` maps list→list,
    then each ``sink`` consumes the final list (e.g. :func:`~pypedeid.ingest.sink.write_annotated_corpus`).

    Example::

        job = DatasetJob(
            load=lambda: load_annotated_corpus(jsonl=Path("in.jsonl")),
            steps=[
                lambda docs: run_transform_pipeline(docs, resplit={"train": 1.0}),
                strip_split_metadata,
            ],
            sinks=[
                lambda docs: write_annotated_corpus(docs, jsonl=Path("out.jsonl")),
            ],
        )
        result = job.run()
    """

    load: Callable[[], list[AnnotatedDocument]]
    steps: Sequence[Callable[[list[AnnotatedDocument]], list[AnnotatedDocument]]] = field(
        default_factory=tuple
    )
    sinks: Sequence[Callable[[list[AnnotatedDocument]], None]] = field(default_factory=tuple)

    def run(self) -> DatasetJobResult:
        docs = self.load()
        for step in self.steps:
            docs = step(docs)
        for sink in self.sinks:
            sink(docs)
        return DatasetJobResult(documents=docs)
