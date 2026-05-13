"""Parse ``kind:path`` specs and load annotated corpora."""

from __future__ import annotations

import sys
from pathlib import Path

from pypedeid.domain import AnnotatedDocument
from pypedeid.ingest.sources import load_annotated_corpus


def load_one_source(spec: str) -> list[AnnotatedDocument]:
    """
    Spec format: ``kind:value`` with kind one of
    ``jsonl``, ``brat-dir``, ``brat-corpus``.
    """
    spec = spec.strip()
    if ":" not in spec:
        print(
            f"Invalid --source {spec!r}: expected kind:path (e.g. jsonl:file.jsonl)",
            file=sys.stderr,
        )
        sys.exit(1)
    kind, _, rest = spec.partition(":")
    kind = kind.strip().lower()
    rest = rest.strip()
    if not rest:
        print(f"Invalid --source {spec!r}: missing path after ':'", file=sys.stderr)
        sys.exit(1)

    if kind == "jsonl":
        return load_annotated_corpus(jsonl=Path(rest))
    if kind == "brat-dir":
        return load_annotated_corpus(brat_dir=Path(rest))
    if kind == "brat-corpus":
        return load_annotated_corpus(brat_corpus=Path(rest))
    print(
        f"Unknown source kind {kind!r} in {spec!r}; "
        "use jsonl, brat-dir, or brat-corpus",
        file=sys.stderr,
    )
    sys.exit(1)
