from __future__ import annotations

import json
from collections.abc import Iterator

from pypedeid.domain import AnnotatedDocument


def iter_annotated_documents_from_jsonl_bytes(data: bytes) -> Iterator[AnnotatedDocument]:
    line_no = 0
    for raw_line in data.splitlines():
        line_no += 1
        line = raw_line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"line {line_no}: invalid JSON: {e}") from e
        try:
            yield AnnotatedDocument.model_validate(obj)
        except Exception as e:
            raise ValueError(f"line {line_no}: not a valid AnnotatedDocument: {e}") from e


def load_annotated_documents_from_jsonl_bytes(data: bytes) -> list[AnnotatedDocument]:
    return list(iter_annotated_documents_from_jsonl_bytes(data))
