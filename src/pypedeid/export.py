"""Output format serializers for CLI results."""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

_SAFE_DOC_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


@dataclass
class ProcessedResult:
    """One processed document for export."""

    doc_id: str
    original_text: str
    output_text: str
    spans: list[dict[str, Any]]
    metadata: dict[str, Any]


def to_text(results: list[ProcessedResult]) -> str:
    """Plain text: one ``output_text`` per result, separated by newlines."""
    return "\n".join(r.output_text for r in results)


def to_json(results: list[ProcessedResult]) -> str:
    """Single JSON array of result objects."""
    return json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False)


def to_jsonl(results: list[ProcessedResult]) -> str:
    """One JSON object per line."""
    return "\n".join(
        json.dumps(asdict(r), ensure_ascii=False) for r in results
    )


def to_csv(results: list[ProcessedResult]) -> str:
    """CSV with columns: doc_id, original_text, output_text, span_count."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["doc_id", "original_text", "output_text", "span_count"])
    for r in results:
        writer.writerow([r.doc_id, r.original_text, r.output_text, len(r.spans)])
    return buf.getvalue()


def to_parquet(results: list[ProcessedResult], path: Path) -> None:
    """Write results to a Parquet file.  Requires ``pyarrow``."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise ImportError(
            "pyarrow is required for Parquet export. "
            "Install with: pip install 'pypedeid[parquet]'"
        ) from exc

    table = pa.table(
        {
            "doc_id": [r.doc_id for r in results],
            "original_text": [r.original_text for r in results],
            "output_text": [r.output_text for r in results],
            "spans_json": [json.dumps(r.spans) for r in results],
            "span_count": [len(r.spans) for r in results],
        }
    )
    pq.write_table(table, str(path))


def write_results(
    results: list[ProcessedResult],
    output_dir: Path,
    fmt: str,
) -> None:
    """Write results to *output_dir* in the specified format."""
    output_dir.mkdir(parents=True, exist_ok=True)

    if fmt == "text":
        for r in results:
            safe_id = re.sub(r"[^\w.-]", "_", r.doc_id)
            (output_dir / f"{safe_id}.txt").write_text(
                r.output_text, encoding="utf-8"
            )
    elif fmt == "jsonl":
        (output_dir / "results.jsonl").write_text(
            to_jsonl(results) + "\n", encoding="utf-8"
        )
    elif fmt == "json":
        (output_dir / "results.json").write_text(
            to_json(results) + "\n", encoding="utf-8"
        )
    elif fmt == "csv":
        (output_dir / "results.csv").write_text(
            to_csv(results), encoding="utf-8"
        )
    elif fmt == "parquet":
        to_parquet(results, output_dir / "results.parquet")
    else:
        raise ValueError(f"Unknown format: {fmt}")
