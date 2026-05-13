"""Convert Production UI JSONL export lines into :class:`AnnotatedDocument` rows.

The Production export schema (``schema_version: 1``) is a custom object per line; the
rest of the platform stores gold data as Pydantic :class:`AnnotatedDocument` lines in
``corpus.jsonl``. Upload handlers call :func:`production_export_bytes_to_annotated_jsonl`
so :func:`pypedeid.dataset_store.import_jsonl_dataset` can ingest the file.
"""

from __future__ import annotations

import json
from typing import Any

from pypedeid.domain import AnnotatedDocument, Document, EntitySpan

PRODUCTION_SCHEMA_VERSION = 1


def _span_from_dict(s: object, i: int) -> EntitySpan:
    if not isinstance(s, dict):
        raise ValueError(f"spans[{i}] must be a JSON object")
    try:
        start = s["start"]
        end = s["end"]
        label = s["label"]
    except (KeyError, TypeError) as e:
        raise ValueError(f"spans[{i}] needs start, end, and label: {e}") from e
    conf = s.get("confidence", None)
    if conf is not None:
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = None
    src = s.get("source", None)
    if src is not None and not isinstance(src, str):
        src = str(src)
    return EntitySpan(
        start=int(start),
        end=int(end),
        label=str(label),
        confidence=conf,
        source=src,
    )


def production_line_to_annotated_document(obj: object) -> AnnotatedDocument:
    """Map one Production ``JsonlLine``-shaped dict to a single :class:`AnnotatedDocument`."""
    if not isinstance(obj, dict):
        raise ValueError("line is not a JSON object")

    sv = obj.get("schema_version")
    if sv != PRODUCTION_SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version {sv!r} (expected {PRODUCTION_SCHEMA_VERSION})")

    doc_id = str(obj.get("id", "")).strip() or "doc"
    text = str(obj.get("text", ""))

    raw_spans = obj.get("spans", [])
    if raw_spans is None:
        raw_spans = []
    if not isinstance(raw_spans, list):
        raise ValueError("spans must be a list or null")
    spans = [_span_from_dict(s, i) for i, s in enumerate(raw_spans)]

    base_meta: dict[str, Any] = {}
    m = obj.get("metadata")
    if isinstance(m, dict):
        base_meta.update(m)
    for key, val in (
        ("source_label", obj.get("source_label")),
        ("export_output_type", obj.get("output_type")),
        ("export_resolved", obj.get("resolved")),
    ):
        if val is not None:
            base_meta[key] = val

    return AnnotatedDocument(
        document=Document(id=doc_id, text=text, metadata=base_meta),
        spans=spans,
    )


def production_export_bytes_to_annotated_jsonl_bytes(data: bytes) -> bytes:
    """Transform a Production export JSONL byte string into AnnotatedDocument JSONL bytes."""
    out_lines: list[str] = []
    line_no = 0
    for raw in data.splitlines():
        line_no += 1
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"line {line_no}: invalid JSON: {e}") from e
        try:
            doc = production_line_to_annotated_document(obj)
        except Exception as e:
            raise ValueError(f"line {line_no}: {e}") from e
        out_lines.append(doc.model_dump_json())
    if not out_lines:
        raise ValueError("no non-empty production export lines in upload")
    return ("\n".join(out_lines) + "\n").encode("utf-8")
