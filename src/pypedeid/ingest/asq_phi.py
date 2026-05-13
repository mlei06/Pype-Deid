"""Parse ASQ-PHI synthetic clinical queries export into ``AnnotatedDocument``-shaped dicts."""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any


def _normalize_query_whitespace(text: str, *, single_line: bool) -> str:
    if single_line:
        return re.sub(r"\s+", " ", text.strip())
    return text.strip()


def _tags_to_spans(text: str, tags: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    search_from = 0
    for t in tags:
        typ = str(t.get("identifier_type", "UNKNOWN"))
        val = t.get("value")
        if val is None:
            continue
        val_s = str(val)
        if not val_s:
            continue
        idx = text.find(val_s, search_from)
        if idx < 0:
            idx = text.find(val_s)
        if idx < 0:
            continue
        spans.append(
            {
                "start": idx,
                "end": idx + len(val_s),
                "label": typ,
                "source": source,
            }
        )
        search_from = idx + len(val_s)
    return spans


def iter_asq_phi_records(path: Path) -> list[tuple[str, list[dict[str, Any]]]]:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=False)
    records: list[tuple[str, list[dict[str, Any]]]] = []
    i = 0
    n = len(lines)

    while i < n:
        if lines[i].strip() != "===QUERY===":
            i += 1
            continue
        i += 1
        q_lines: list[str] = []
        while i < n and lines[i].strip() != "===PHI_TAGS===":
            q_lines.append(lines[i])
            i += 1
        if i >= n:
            break
        i += 1
        raw_q = "\n".join(q_lines)
        tags: list[dict[str, Any]] = []
        while i < n:
            s = lines[i].strip()
            if s == "":
                i += 1
                break
            if s == "===QUERY===":
                break
            if s.startswith("{"):
                try:
                    obj = json.loads(s)
                except json.JSONDecodeError:
                    i += 1
                    continue
                if isinstance(obj, dict):
                    tags.append(obj)
                i += 1
            else:
                i += 1
        records.append((raw_q, tags))
    return records


def records_to_annotated_dicts(
    records: list[tuple[str, list[dict[str, Any]]]],
    *,
    id_prefix: str = "asq",
    span_source: str = "asq_phi_gold",
    single_line_query: bool = False,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, (raw_q, tags) in enumerate(records):
        q = _normalize_query_whitespace(raw_q, single_line=single_line_query)
        span_dicts = _tags_to_spans(q, tags, span_source)
        doc_id = f"{id_prefix}_{idx + 1}"
        out.append(
            {
                "document": {
                    "id": doc_id,
                    "text": q,
                    "metadata": {"source": "ASQ-PHI", "corpus": "synthetic_clinical_queries"},
                },
                "spans": span_dicts,
            }
        )
    return out


def write_asq_phi_jsonl(path: Path, objs: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for o in objs:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")


def write_brat_note(
    directory: Path,
    stem: str,
    *,
    text: str,
    spans: list[dict[str, Any]],
) -> None:
    """Write one ``{stem}.txt`` / ``{stem}.ann`` pair under ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{stem}.txt").write_text(text, encoding="utf-8")
    ann_lines: list[str] = []
    for j, s in enumerate(spans):
        lbl = s["label"]
        a, b = s["start"], s["end"]
        mention = text[a:b]
        ann_lines.append(f"T{j + 1}\t{lbl} {a} {b}\t{mention}\n")
    (directory / f"{stem}.ann").write_text("".join(ann_lines), encoding="utf-8")


def write_asq_phi_brat_flat(output_dir: Path, objs: list[dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for i, o in enumerate(objs, start=1):
        doc = o["document"]
        write_brat_note(
            output_dir,
            f"note_{i}",
            text=doc["text"],
            spans=o.get("spans", []),
        )


def write_asq_phi_brat_corpus(
    output_root: Path,
    objs: list[dict[str, Any]],
    *,
    seed: int = 42,
    train_ratio: float = 0.7,
    val_ratio: float = 0.15,
) -> None:
    """
    BRAT layout compatible with ``load_brat_corpus_with_splits``: ``train/``, ``valid``, ``test/``
    subfolders with paired ``note_k.txt`` / ``note_k.ann`` (``k`` per split).
    """
    if not objs:
        return
    rng = random.Random(seed)
    order = list(range(len(objs)))
    rng.shuffle(order)
    n = len(order)
    train_cutoff = int(n * train_ratio)
    val_cutoff = train_cutoff + int(n * val_ratio)
    splits: list[tuple[str, list[int]]] = [
        ("train", order[:train_cutoff]),
        ("valid", order[train_cutoff:val_cutoff]),
        ("test", order[val_cutoff:]),
    ]
    for split_name, idxs in splits:
        sub = output_root / split_name
        sub.mkdir(parents=True, exist_ok=True)
        for k, idx in enumerate(idxs, start=1):
            o = objs[idx]
            doc = o["document"]
            write_brat_note(
                sub,
                f"note_{k}",
                text=doc["text"],
                spans=o.get("spans", []),
            )
