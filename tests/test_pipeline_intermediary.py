"""Pipeline intermediate tracing (Pipeline.run with trace=True)."""

from __future__ import annotations

from pypedeid.domain import AnnotatedDocument, Document
from pypedeid.pipes.registry import dump_pipeline, load_pipeline
def _doc(text: str) -> AnnotatedDocument:
    return AnnotatedDocument(document=Document(id="d", text=text), spans=[])


def test_forward_returns_annotated_document() -> None:
    """forward() conforms to the Pipe protocol — returns AnnotatedDocument."""
    cfg = {"pipes": [{"type": "regex_ner"}]}
    p = load_pipeline(cfg)
    result = p.forward(_doc("Call 555-123-4567."))
    assert isinstance(result, AnnotatedDocument)
    assert len(result.spans) >= 1


def test_run_without_trace_returns_empty_trace() -> None:
    cfg = {"pipes": [{"type": "regex_ner"}]}
    p = load_pipeline(cfg)
    run = p.run(_doc("Call 555-123-4567."))
    assert run.trace == []
    assert len(run.final.spans) >= 1


def test_run_with_trace_captures_all_steps() -> None:
    cfg = {
        "pipes": [
            {"type": "regex_ner"},
            {
                "type": "whitelist",
                "config": {
                    "labels": {
                        "HOSPITAL": {
                            "terms": ["Zed Clinic"],
                        },
                    },
                },
            },
        ],
    }
    p = load_pipeline(cfg)
    doc = _doc("Contact a@b.co at Zed Clinic.")
    run = p.run(doc, trace=True)
    assert len(run.trace) == 2  # one frame per pipe
    assert all(f.stage == "sequential" for f in run.trace)
    assert run.trace[0].path == "step_0"
    assert run.trace[1].path == "step_1"


def test_dump_load_roundtrip() -> None:
    cfg = {
        "pipes": [
            {"type": "regex_ner"},
            {"type": "whitelist"},
        ],
    }
    p0 = load_pipeline(cfg)
    p1 = load_pipeline(dump_pipeline(p0))
    run = p1.run(_doc("x@y.co"), trace=True)
    assert len(run.trace) == 2


def test_run_with_timing_records_elapsed() -> None:
    cfg = {"pipes": [{"type": "regex_ner"}, {"type": "whitelist"}]}
    p = load_pipeline(cfg)
    run = p.run(_doc("Call 555-123-4567."), timing=True)
    assert run.total_elapsed_ms is not None
    assert run.total_elapsed_ms > 0
    assert len(run.trace) == 2
    assert all(f.elapsed_ms is not None and f.elapsed_ms >= 0 for f in run.trace)
    # No document snapshots when only timing is enabled
    assert all(f.document is None for f in run.trace)


def test_run_with_trace_and_timing() -> None:
    cfg = {"pipes": [{"type": "regex_ner"}]}
    p = load_pipeline(cfg)
    run = p.run(_doc("Call 555-123-4567."), trace=True, timing=True)
    assert run.total_elapsed_ms is not None
    assert len(run.trace) == 1
    assert run.trace[0].document is not None
    assert run.trace[0].elapsed_ms is not None


