#!/usr/bin/env python3
"""
Convert ASQ-PHI ``synthetic_clinical_queries.txt`` into AnnotatedDocument JSONL (and optional BRAT).

See ``pypedeid.ingest.asq_phi`` for the parser.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pypedeid.ingest.asq_phi import (
    iter_asq_phi_records,
    records_to_annotated_dicts,
    write_asq_phi_brat_corpus,
    write_asq_phi_brat_flat,
    write_asq_phi_jsonl,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="ASQ-PHI synthetic queries → JSONL / BRAT")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/raw/asq-phi/synthetic_clinical_queries.txt"),
    )
    parser.add_argument(
        "--output-jsonl",
        type=Path,
        default=Path("data/corpora/asq_phi/jsonl/asq_phi.jsonl"),
    )
    parser.add_argument(
        "--output-brat-dir",
        type=Path,
        default=None,
        help="Optional flat BRAT directory (all notes in one folder)",
    )
    parser.add_argument(
        "--output-brat-corpus",
        type=Path,
        default=None,
        help="BRAT root with train/valid/test/ subfolders (same layout as PhysioNet export)",
    )
    parser.add_argument("--brat-seed", type=int, default=42, help="Shuffle seed for --output-brat-corpus")
    parser.add_argument(
        "--brat-train",
        type=float,
        default=0.7,
        help="Train fraction for --output-brat-corpus",
    )
    parser.add_argument(
        "--brat-valid",
        type=float,
        default=0.15,
        help="Validation fraction for --output-brat-corpus",
    )
    parser.add_argument(
        "--single-line",
        action="store_true",
        help="Collapse query whitespace to single spaces",
    )
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"Input not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    records = iter_asq_phi_records(args.input)
    objs = records_to_annotated_dicts(records, single_line_query=args.single_line)
    write_asq_phi_jsonl(args.output_jsonl, objs)
    print(f"Wrote {len(objs)} documents → {args.output_jsonl}", file=sys.stderr)

    if args.output_brat_dir is not None:
        write_asq_phi_brat_flat(args.output_brat_dir, objs)
        print(f"Wrote BRAT flat dir → {args.output_brat_dir}", file=sys.stderr)

    if args.output_brat_corpus is not None:
        write_asq_phi_brat_corpus(
            args.output_brat_corpus,
            objs,
            seed=args.brat_seed,
            train_ratio=args.brat_train,
            val_ratio=args.brat_valid,
        )
        print(f"Wrote BRAT corpus (train/valid/test) → {args.output_brat_corpus}", file=sys.stderr)


if __name__ == "__main__":
    main()
