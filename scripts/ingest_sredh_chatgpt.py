"""Ingest SREDH AI-Cup 2023 ChatGPT-generated synthetic PHI examples.

Parses the files in ``rule_projects/SREDH-AI-Cup-2023/Resources-Used/chatgpt_generate/``
and produces a list of ``AnnotatedDocument`` with character-offset PHI spans.

Usage::

    python scripts/ingest_sredh_chatgpt.py [--out-dir data/corpora/sredh_chatgpt]

Each source file has lines like::

    45yo man with suspected lung mass.\\tAGE: 45
    Phone: 9876 5432\\tPHONE: 9876 5432
    Result to Dr Burck by Dr A. Smith...\\tDOCTOR: Burck\\nDOCTOR: A. Smith\\nTIME: 9:45am...

Annotations are tab-separated from the sentence. Multiple annotations on one
line are separated by ``\\n`` (literal backslash-n inside the field).
Normalizations use ``=>`` (e.g. ``DATE: 3/15/22=>2022-03-15``).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pypedeid.domain import AnnotatedDocument, Document, EntitySpan

CHATGPT_DIR = (
    Path(__file__).resolve().parents[1]
    / "rule_projects"
    / "SREDH-AI-Cup-2023"
    / "Resources-Used"
    / "chatgpt_generate"
)

# Regex to parse one annotation: "LABEL: value" or "LABEL:value" with optional "=>norm"
_ANNO_RE = re.compile(r"^([A-Z][A-Z0-9_-]*)\s*:\s*(.+?)(?:=>.*)?$")


def _parse_annotations(raw: str) -> list[tuple[str, str]]:
    """Parse the annotation field into (label, entity_text) pairs."""
    # Annotations are separated by literal \n characters within the field
    parts = raw.split("\\n") if "\\n" in raw else raw.split("\n")
    out: list[tuple[str, str]] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = _ANNO_RE.match(part)
        if m:
            label, entity_text = m.group(1), m.group(2).strip()
            out.append((label, entity_text))
    return out


def _find_span(text: str, entity_text: str, search_from: int = 0) -> tuple[int, int] | None:
    """Find character offsets of entity_text in text."""
    idx = text.find(entity_text, search_from)
    if idx == -1:
        return None
    return (idx, idx + len(entity_text))


def parse_file(path: Path) -> list[AnnotatedDocument]:
    """Parse one chatgpt_generate .txt file into AnnotatedDocuments."""
    docs: list[AnnotatedDocument] = []
    raw = path.read_text(encoding="utf-8-sig")

    # Some files (DOCTOR.txt) are wrapped in quotes as one big block;
    # split on actual newlines and strip surrounding quotes
    lines = raw.splitlines()

    file_label = path.stem  # e.g. "AGE", "PHONE"
    line_no = 0

    for line in lines:
        line = line.strip().strip('"')
        if not line:
            continue
        line_no += 1

        # Split on literal \t (backslash-t, not actual tab)
        parts = line.split("\\t", 1)
        if len(parts) < 2:
            continue

        sentence = parts[0].strip()
        anno_raw = parts[1].strip()

        if not sentence or not anno_raw:
            continue

        # Some files (IDNUM.txt) have multiple \t-separated annotations
        # Re-join with \n so _parse_annotations handles them uniformly
        anno_raw = "\n".join(p.strip() for p in line.split("\\t")[1:])

        annotations = _parse_annotations(anno_raw)
        if not annotations:
            continue

        # Build spans by finding each entity in the sentence text
        spans: list[EntitySpan] = []
        used_positions: set[tuple[int, int]] = set()

        for label, entity_text in annotations:
            # Search for each occurrence, avoiding duplicate spans at same position
            search_from = 0
            while True:
                result = _find_span(sentence, entity_text, search_from)
                if result is None:
                    break
                if result not in used_positions:
                    used_positions.add(result)
                    spans.append(
                        EntitySpan(
                            start=result[0],
                            end=result[1],
                            label=label,
                            source="sredh_chatgpt",
                        )
                    )
                    break
                # Same position already used by same label, search further
                search_from = result[0] + 1

        if not spans:
            continue

        spans.sort(key=lambda s: (s.start, s.end))

        doc_id = f"sredh_chatgpt_{file_label}_{line_no:05d}"
        docs.append(
            AnnotatedDocument(
                document=Document(id=doc_id, text=sentence, metadata={"source_file": path.name}),
                spans=spans,
            )
        )

    return docs


def load_all(directory: Path | None = None) -> list[AnnotatedDocument]:
    """Load all chatgpt_generate files and return AnnotatedDocuments."""
    directory = directory or CHATGPT_DIR
    all_docs: list[AnnotatedDocument] = []
    for txt_file in sorted(directory.glob("*.txt")):
        if txt_file.name.lower().startswith("readme"):
            continue
        docs = parse_file(txt_file)
        all_docs.extend(docs)
        print(f"  {txt_file.name:25s} → {len(docs):5d} documents")
    return all_docs


def save_jsonl(docs: list[AnnotatedDocument], path: Path) -> None:
    """Write documents to JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for doc in docs:
            f.write(doc.model_dump_json() + "\n")


def save_brat(docs: list[AnnotatedDocument], out_dir: Path) -> None:
    """Write documents as brat standoff format (.txt + .ann pairs)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for doc in docs:
        doc_id = doc.document.id
        txt_path = out_dir / f"{doc_id}.txt"
        ann_path = out_dir / f"{doc_id}.ann"

        txt_path.write_text(doc.document.text, encoding="utf-8")

        ann_lines: list[str] = []
        for i, span in enumerate(doc.spans, start=1):
            entity_text = doc.document.text[span.start : span.end]
            ann_lines.append(f"T{i}\t{span.label} {span.start} {span.end}\t{entity_text}")
        ann_path.write_text("\n".join(ann_lines) + "\n" if ann_lines else "", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest SREDH AI-Cup ChatGPT synthetic data")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=CHATGPT_DIR,
        help="Path to chatgpt_generate directory",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/corpora/sredh_chatgpt"),
        help="Output directory (will contain brat/ and json/ subdirs)",
    )
    args = parser.parse_args()

    print(f"Loading from {args.input_dir}")
    docs = load_all(args.input_dir)

    # Print summary
    label_counts: dict[str, int] = {}
    for doc in docs:
        for span in doc.spans:
            label_counts[span.label] = label_counts.get(span.label, 0) + 1

    print(f"\n{'Label':25s} {'Count':>6s}")
    print("-" * 33)
    for label, count in sorted(label_counts.items(), key=lambda x: -x[1]):
        print(f"  {label:23s} {count:6d}")
    print(f"\nTotal: {len(docs)} documents, {sum(label_counts.values())} spans")

    # Save JSON
    json_dir = args.out_dir / "jsonl"
    save_jsonl(docs, json_dir / "sredh_chatgpt.jsonl")
    print(f"\nSaved JSONL to {json_dir / 'sredh_chatgpt.jsonl'}")

    # Save brat
    brat_dir = args.out_dir / "brat"
    save_brat(docs, brat_dir)
    print(f"Saved {len(docs)} brat document pairs to {brat_dir}/")


if __name__ == "__main__":
    main()
