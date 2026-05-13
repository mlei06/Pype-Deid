#!/usr/bin/env python3
"""
Build a synthetic BRAT corpus from MIMIC NOTEEVENTS.csv by replacing [**...**] placeholders.

Ported from ``neuroner-cspmc/scripts/Mimic_Dataset_Generation`` (extract placeholders,
Faker replacements, adjacent-PATIENT merge, train/valid/test split).

Requires: ``pip install pypedeid[scripts]`` (pandas + faker).

Example:
  python scripts/process_mimic_noteevents.py \\
    --input NOTEEVENTS.csv --output data/corpora/mimic_brat \\
    --max-notes 5000
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from pypedeid.ingest.mimic.pipeline import run_noteevents_pipeline


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description="NOTEEVENTS CSV → BRAT (placeholder synthesis + optional split)",
    )
    parser.add_argument("--input", type=Path, required=True, help="Path to NOTEEVENTS.csv")
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output directory (flat BRAT, then merged; optionally split subfolders)",
    )
    parser.add_argument("--max-notes", type=int, default=None)
    parser.add_argument("--chunksize", type=int, default=1000)
    parser.add_argument("--train-ratio", type=float, default=0.75)
    parser.add_argument("--valid-ratio", type=float, default=0.05)
    parser.add_argument("--test-ratio", type=float, default=0.20)
    parser.add_argument("--split-seed", type=int, default=42)
    parser.add_argument(
        "--no-merge-adjacent",
        action="store_true",
        help="Skip merging adjacent PATIENT spans separated by a single space",
    )
    parser.add_argument(
        "--no-split",
        action="store_true",
        help="Keep a single flat BRAT directory (no train/valid/test moves)",
    )
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"Input not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    run_noteevents_pipeline(
        args.input,
        args.output,
        chunksize=args.chunksize,
        max_notes=args.max_notes,
        merge_adjacent_patient=not args.no_merge_adjacent,
        split_into_subdirs=not args.no_split,
        train_ratio=args.train_ratio,
        valid_ratio=args.valid_ratio,
        test_ratio=args.test_ratio,
        split_seed=args.split_seed,
    )
    print(f"Done → {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
