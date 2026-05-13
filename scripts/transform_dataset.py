#!/usr/bin/env python3
"""
Transform annotated corpora: label filtering, label remapping, random resize,
boost documents by label. Write JSONL and/or BRAT output.

Examples:
  python scripts/transform_dataset.py --jsonl data.jsonl --target-documents 500 \
    --output-jsonl out.jsonl

  python scripts/transform_dataset.py --jsonl data.jsonl --label-map map.json \
    --boost-label NAME --boost-extra-copies 2 --output-jsonl aug.jsonl

  python scripts/transform_dataset.py --brat-corpus data/brat \
    --drop-labels DATE AGE --output-jsonl filtered.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _parse_resplit(spec: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            sys.exit(f"--resplit: expected name=fraction, got {part!r}")
        k, v = part.split("=", 1)
        try:
            out[k.strip()] = float(v.strip())
        except ValueError as e:
            raise SystemExit(f"--resplit: bad fraction in {part!r}") from e
    return out


def _load_label_map(path: Path) -> dict[str, str]:
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        sys.exit("label map JSON must be an object")
    out: dict[str, str] = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not isinstance(v, str):
            sys.exit("label map must be string → string")
        out[k] = v
    return out


def _write_jsonl(path: Path, docs: list) -> None:
    from pypedeid.domain import AnnotatedDocument

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for d in docs:
            if not isinstance(d, AnnotatedDocument):
                raise TypeError("expected AnnotatedDocument")
            f.write(d.model_dump_json() + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dataset transforms + JSONL / BRAT output")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--jsonl", type=Path)
    src.add_argument("--brat-dir", type=Path)
    src.add_argument("--brat-corpus", type=Path)

    parser.add_argument("--drop-labels", nargs="+", default=None, help="Remove spans with these labels")
    parser.add_argument("--keep-labels", nargs="+", default=None, help="Keep only spans with these labels")
    parser.add_argument("--label-map", type=Path, default=None)
    parser.add_argument("--target-documents", type=int, default=None)
    parser.add_argument("--boost-label", type=str, default=None)
    parser.add_argument("--boost-extra-copies", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--resplit",
        type=str,
        default=None,
        metavar="SPECS",
        help='Reassign metadata["split"], last pipeline step. e.g. '
        '"train=0.7,valid=0.15,test=0.15" or add deploy=0.1 (weights normalized to 1)',
    )
    parser.add_argument(
        "--drop-split",
        action="store_true",
        help='After other steps, remove metadata["split"] from all documents (flat corpus)',
    )

    parser.add_argument("--output-jsonl", type=Path, default=None)
    parser.add_argument(
        "--output-brat-dir",
        type=Path,
        default=None,
        help="Write flat BRAT .txt/.ann pairs to this directory",
    )
    parser.add_argument(
        "--output-brat-corpus",
        type=Path,
        default=None,
        help="Write BRAT under split subfolders when metadata['split'] is set (train/valid/...)",
    )

    args = parser.parse_args()

    from pypedeid.ingest.sink import write_annotated_corpus
    from pypedeid.ingest.sources import load_annotated_corpus
    from pypedeid.transform.ops import run_transform_pipeline

    docs = load_annotated_corpus(
        jsonl=args.jsonl,
        brat_dir=args.brat_dir,
        brat_corpus=args.brat_corpus,
    )
    if not docs:
        print("No documents loaded.", file=sys.stderr)
        sys.exit(1)

    mapping = _load_label_map(args.label_map) if args.label_map else None
    resplit = _parse_resplit(args.resplit) if args.resplit else None

    out_docs = run_transform_pipeline(
        docs,
        drop_labels=args.drop_labels,
        keep_labels=args.keep_labels,
        label_mapping=mapping,
        target_documents=args.target_documents,
        boost_label=args.boost_label,
        boost_extra_copies=args.boost_extra_copies,
        resplit=resplit,
        strip_splits=args.drop_split,
        seed=args.seed,
    )

    if args.output_jsonl is not None:
        _write_jsonl(args.output_jsonl, out_docs)
        print(f"Wrote {len(out_docs)} documents → {args.output_jsonl}", file=sys.stderr)

    if args.output_brat_dir is not None:
        write_annotated_corpus(out_docs, brat_dir=args.output_brat_dir)
        print(f"Wrote {len(out_docs)} BRAT pairs → {args.output_brat_dir}", file=sys.stderr)

    if args.output_brat_corpus is not None:
        write_annotated_corpus(out_docs, brat_corpus=args.output_brat_corpus)
        print(f"Wrote {len(out_docs)} BRAT pairs → {args.output_brat_corpus}", file=sys.stderr)

    if not args.output_jsonl and not args.output_brat_dir and not args.output_brat_corpus:
        print(
            "No output: specify --output-jsonl, --output-brat-dir, or --output-brat-corpus",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
