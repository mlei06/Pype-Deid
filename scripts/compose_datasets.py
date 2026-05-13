#!/usr/bin/env python3
"""
Compose multiple annotated corpora into one flat dataset (JSONL and/or SQLite).

Each --source is loaded (BRAT corpus folder layout is ignored for merging: splits are
flattened). Document ids are namespaced (default prefix ``s0__``, ``s1__``, …).

Examples:
  python scripts/compose_datasets.py \\
    --source jsonl:a.jsonl --source jsonl:b.jsonl \\
    --strategy merge --output-jsonl merged.jsonl

  python scripts/compose_datasets.py \\
    --source brat-corpus:corp1 --source brat-corpus:corp2 \\
    --strategy proportional --weights 2,1 --target-documents 300 --seed 42 \\
    --output-jsonl mix.jsonl

  python scripts/compose_datasets.py \\
    --source jsonl:a.jsonl --source brat-corpus:corp3 \\
    --strategy interleave --shuffle --seed 1 \\
    --output-jsonl combo.jsonl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pypedeid.compose import CompositionStrategy, compose_corpora, load_one_source


def _write_jsonl(path: Path, docs: list) -> None:
    from pypedeid.domain import AnnotatedDocument

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for d in docs:
            if not isinstance(d, AnnotatedDocument):
                raise TypeError("expected AnnotatedDocument")
            f.write(d.model_dump_json() + "\n")


def _parse_weights(spec: str | None, n_sources: int) -> list[float] | None:
    if spec is None:
        return None
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    if len(parts) != n_sources:
        print(
            f"--weights: expected {n_sources} comma-separated values, got {len(parts)}",
            file=sys.stderr,
        )
        sys.exit(1)
    out: list[float] = []
    for p in parts:
        try:
            out.append(float(p))
        except ValueError:
            print(f"--weights: bad number {p!r}", file=sys.stderr)
            sys.exit(1)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Compose multiple datasets into one flat corpus")
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        metavar="KIND:PATH",
        required=True,
        help="Repeatable: jsonl:PATH, brat-dir:PATH, brat-corpus:PATH",
    )
    parser.add_argument(
        "--strategy",
        choices=("merge", "proportional", "interleave"),
        default="merge",
        help="merge=concat, interleave=round-robin, proportional=weighted sample wo replacement",
    )
    parser.add_argument(
        "--weights",
        default=None,
        metavar="W,W,...",
        help="For proportional: weights matching --source count (default: equal)",
    )
    parser.add_argument(
        "--target-documents",
        type=int,
        default=None,
        help="For proportional: total size after sampling (default: all available)",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--shuffle",
        action="store_true",
        help="For merge/interleave: shuffle the combined order (after concat/interleave)",
    )
    parser.add_argument(
        "--id-prefix",
        default="s",
        help="Document id prefix: {prefix}{i}__{original_id}",
    )
    parser.add_argument(
        "--no-provenance",
        action="store_true",
        help="Do not add compose_* metadata fields",
    )
    parser.add_argument("--output-jsonl", type=Path, default=None)

    args = parser.parse_args()
    if len(args.sources) < 1:
        print("Provide at least one --source", file=sys.stderr)
        sys.exit(1)

    blocks = [load_one_source(s) for s in args.sources]
    if not any(blocks):
        print("All sources empty.", file=sys.stderr)
        sys.exit(1)

    weights = _parse_weights(args.weights, len(args.sources))
    if args.strategy == "proportional" and args.shuffle:
        print("Note: --shuffle ignored for proportional (output is already shuffled)", file=sys.stderr)

    strat: CompositionStrategy = args.strategy  # type: ignore[assignment]
    out_docs = compose_corpora(
        blocks,
        strategy=strat,
        weights=weights,
        target_documents=args.target_documents,
        seed=args.seed,
        shuffle=args.shuffle if args.strategy != "proportional" else False,
        id_prefix=args.id_prefix,
        provenance=not args.no_provenance,
    )

    if args.output_jsonl is not None:
        _write_jsonl(args.output_jsonl, out_docs)
        print(f"Wrote {len(out_docs)} documents → {args.output_jsonl}", file=sys.stderr)
    else:
        print("No output: specify --output-jsonl", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
