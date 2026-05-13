#!/usr/bin/env python3
"""Print dataset analytics from JSONL or BRAT directories."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dataset analytics: JSONL, BRAT folder, or BRAT corpus root"
    )
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--jsonl", type=Path, help="AnnotatedDocument JSONL")
    g.add_argument(
        "--brat-dir",
        type=Path,
        help="Single BRAT directory (paired .txt/.ann)",
    )
    g.add_argument(
        "--brat-corpus",
        type=Path,
        help="Root with train/valid/test subdirs (e.g. data/corpora/physionet/brat), or flat BRAT dir",
    )
    args = parser.parse_args()

    from pypedeid.analytics.stats import compute_dataset_analytics
    from pypedeid.ingest.sources import load_annotated_corpus

    docs = load_annotated_corpus(
        jsonl=args.jsonl,
        brat_dir=args.brat_dir,
        brat_corpus=args.brat_corpus,
    )
    if not docs:
        print("No documents loaded.", file=sys.stderr)
        sys.exit(1)

    out = compute_dataset_analytics(docs)
    print(json.dumps(out.model_dump(), indent=2))


if __name__ == "__main__":
    main()
