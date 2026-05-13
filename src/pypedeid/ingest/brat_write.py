"""Write ``AnnotatedDocument`` instances to BRAT ``.txt`` / ``.ann`` pairs."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pypedeid.domain import AnnotatedDocument, EntitySpan
from pypedeid.ids import BratWriteStemStrategy, default_brat_write_stem

# Must match reader subfolder names in :func:`load_brat_corpus_with_splits`.
CORPUS_SPLIT_NAMES = frozenset({"train", "valid", "test", "dev", "deploy"})


def format_ann_lines(spans: list[EntitySpan], text: str) -> str:
    """BRAT text-bound annotations; surfaces taken from ``text`` for consistency."""
    lines: list[str] = []
    for i, span in enumerate(spans, 1):
        surface = text[span.start : span.end].replace("\n", " ").replace("\r", " ")
        lines.append(f"T{i}\t{span.label} {span.start} {span.end}\t{surface}\n")
    return "".join(lines)


def write_brat_pair(
    output_dir: Path,
    stem: str,
    text: str,
    spans: list[EntitySpan],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    txt_path = output_dir / f"{stem}.txt"
    ann_path = output_dir / f"{stem}.ann"
    txt_path.write_text(text, encoding="utf-8")
    ann_path.write_text(format_ann_lines(spans, text) if spans else "", encoding="utf-8")


def _allocate_unique_stems(
    docs: list[AnnotatedDocument],
    stem_fn: BratWriteStemStrategy,
) -> list[str]:
    used: dict[str, int] = {}
    out: list[str] = []
    for ad in docs:
        base = stem_fn(ad)
        n = used.get(base, 0)
        used[base] = n + 1
        out.append(base if n == 0 else f"{base}__{n + 1}")
    return out


def write_annotated_corpus_brat_flat(
    docs: list[AnnotatedDocument],
    directory: Path,
    *,
    stem_fn: Callable[[AnnotatedDocument], str] | None = None,
) -> None:
    """Write all documents into a single flat BRAT directory (unique stems if ids collide)."""
    fn: BratWriteStemStrategy = stem_fn or default_brat_write_stem
    stems = _allocate_unique_stems(docs, fn)
    directory = directory.resolve()
    for ad, stem in zip(docs, stems):
        write_brat_pair(directory, stem, ad.document.text, list(ad.spans))


def write_annotated_corpus_brat_split(
    docs: list[AnnotatedDocument],
    corpus_root: Path,
    *,
    stem_fn: Callable[[AnnotatedDocument], str] | None = None,
) -> None:
    """
    Route each document to ``corpus_root/{split}/`` when ``metadata['split']`` is a known split name;
    otherwise write to ``corpus_root`` (flat).
    """
    fn: BratWriteStemStrategy = stem_fn or default_brat_write_stem
    corpus_root = corpus_root.resolve()
    corpus_root.mkdir(parents=True, exist_ok=True)

    by_dir: dict[Path, list[AnnotatedDocument]] = {}
    for ad in docs:
        sp = ad.document.metadata.get("split")
        if isinstance(sp, str) and sp in CORPUS_SPLIT_NAMES:
            d = corpus_root / sp
        else:
            d = corpus_root
        by_dir.setdefault(d, []).append(ad)

    for d, ad_list in by_dir.items():
        stems = _allocate_unique_stems(ad_list, fn)
        for ad, stem in zip(ad_list, stems):
            write_brat_pair(d, stem, ad.document.text, list(ad.spans))
