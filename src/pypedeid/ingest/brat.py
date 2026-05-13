"""Load paired BRAT ``.txt`` / ``.ann`` files into ``AnnotatedDocument``."""

from __future__ import annotations

from pathlib import Path

from pypedeid.domain import AnnotatedDocument, Document, EntitySpan


def _parse_brat_ann(ann_path: Path) -> list[EntitySpan]:
    spans: list[EntitySpan] = []
    text = ann_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("T") or "\t" not in line:
            continue
        parts = line.split("\t", 2)
        if len(parts) < 2:
            continue
        ann_body = parts[1].strip()
        if ";" in ann_body:
            continue  # discontinuous; not supported here
        bits = ann_body.split()
        if len(bits) < 3:
            continue
        label = bits[0]
        try:
            start = int(bits[1])
            end = int(bits[2])
        except ValueError:
            continue
        spans.append(EntitySpan(start=start, end=end, label=label, source="brat"))
    return spans


def load_brat_directory(
    directory: Path,
    *,
    split: str | None = None,
    doc_id_prefix: str = "",
) -> list[AnnotatedDocument]:
    """
    One BRAT corpus directory: for each ``*.txt``, load text and sibling ``*.ann``.

    ``split`` is optional metadata (e.g. ``train``).
    ``doc_id_prefix`` avoids clashes when merging multiple dirs (e.g. ``train__``).
    """
    directory = directory.resolve()
    out: list[AnnotatedDocument] = []
    for txt_path in sorted(directory.glob("*.txt")):
        ann_path = txt_path.with_suffix(".ann")
        if not ann_path.is_file():
            continue
        text = txt_path.read_text(encoding="utf-8")
        spans = _parse_brat_ann(ann_path)
        meta: dict = {}
        if split:
            meta["split"] = split
        doc_id = f"{doc_id_prefix}{txt_path.stem}"
        out.append(
            AnnotatedDocument(
                document=Document(id=doc_id, text=text, metadata=meta),
                spans=spans,
            )
        )
    return out


def load_brat_corpus_with_splits(corpus_root: Path) -> list[AnnotatedDocument]:
    """
    If ``corpus_root`` has ``train`` / ``valid`` / ``test`` subdirs, load each and tag ``metadata.split``.

    Otherwise load ``corpus_root`` as a flat BRAT folder.
    """
    corpus_root = corpus_root.resolve()
    split_names = ("train", "valid", "test", "dev", "deploy")
    subdirs = [corpus_root / name for name in split_names if (corpus_root / name).is_dir()]
    if not subdirs:
        return load_brat_directory(corpus_root)

    docs: list[AnnotatedDocument] = []
    for d in subdirs:
        split = d.name
        for ad in load_brat_directory(d, split=split, doc_id_prefix=f"{split}__"):
            docs.append(ad)
    return docs
