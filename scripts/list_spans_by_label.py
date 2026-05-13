#!/usr/bin/env python3
"""Print every span with a given label from a dataset (JSONL, DB id, or BRAT)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from io import StringIO
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="List all spans for one entity label (JSONL or BRAT)"
    )
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--jsonl", type=Path, help="AnnotatedDocument JSONL")
    g.add_argument("--brat-dir", type=Path, help="Single BRAT directory")
    g.add_argument(
        "--brat-corpus",
        type=Path,
        help="BRAT root with train/valid/test (or flat folder)",
    )
    parser.add_argument("--label", required=True, help="Entity label to match (e.g. DATE, PATIENT)")
    parser.add_argument(
        "--ignore-case",
        action="store_true",
        help="Match label case-insensitively",
    )
    parser.add_argument(
        "--format",
        choices=("tsv", "json"),
        default="tsv",
        help="Output format (default: tsv)",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=0,
        help="Stop after N spans (0 = no limit)",
    )
    args = parser.parse_args()

    from pypedeid.ingest.sources import load_annotated_corpus

    docs = load_annotated_corpus(
        jsonl=args.jsonl,
        brat_dir=args.brat_dir,
        brat_corpus=args.brat_corpus,
    )
    if not docs:
        print("No documents loaded.", file=sys.stderr)
        sys.exit(1)

    want = args.label.strip()
    if not want:
        print("--label must be non-empty", file=sys.stderr)
        sys.exit(1)

    def match(lbl: str) -> bool:
        if args.ignore_case:
            return lbl.casefold() == want.casefold()
        return lbl == want

    rows: list[dict[str, str | int | None]] = []
    for ad in docs:
        doc_id = ad.document.id
        split = ad.document.metadata.get("split")
        text = ad.document.text
        for s in ad.spans:
            if not match(s.label):
                continue
            surface = text[s.start : s.end]
            rows.append(
                {
                    "document_id": doc_id,
                    "start": s.start,
                    "end": s.end,
                    "label": s.label,
                    "text": surface,
                    "split": split,
                    "confidence": s.confidence,
                    "source": s.source,
                }
            )
            if args.max and len(rows) >= args.max:
                break
        if args.max and len(rows) >= args.max:
            break

    if args.format == "json":
        for r in rows:
            out = {k: v for k, v in r.items() if v is not None}
            print(json.dumps(out, ensure_ascii=False))
    else:
        buf = StringIO()
        w = csv.writer(buf, delimiter="\t", lineterminator="\n")
        w.writerow(["document_id", "start", "end", "label", "text", "split"])
        for r in rows:
            w.writerow(
                [
                    r["document_id"],
                    r["start"],
                    r["end"],
                    r["label"],
                    r["text"],
                    r.get("split") or "",
                ]
            )
        sys.stdout.write(buf.getvalue())

    print(f"# spans matched: {len(rows)}", file=sys.stderr)


if __name__ == "__main__":
    main()
