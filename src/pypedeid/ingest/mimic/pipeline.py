"""NOTEEVENTS CSV → synthetic BRAT corpus (placeholder fill, merge, optional split)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from pathlib import Path

from pypedeid.ingest.mimic.brat_merge import BratT, merge_brat_directory_flat
from pypedeid.ingest.mimic.faker_providers import getrandformat
from pypedeid.ingest.mimic.placeholders import extract_placeholders
from pypedeid.ingest.mimic.profile import NoteProfile, make_note_profile
from pypedeid.ingest.mimic.replacement import get_placeholder_entity, get_replaced_text
from pypedeid.ingest.mimic.split import split_brat_directory_to_corpus

logger = logging.getLogger(__name__)


def _parse_chartdate(value: object) -> date | None:
    """Try to parse NOTEEVENTS CHARTDATE to a date; return None on failure."""
    if value is None:
        return None
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        from datetime import datetime

        s = str(value).strip()
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
    except Exception:
        pass
    return None


def process_note_text(
    note_text: str,
    *,
    note_id: str | None = None,
    profile: NoteProfile | None = None,
) -> tuple[str, list[BratT]]:
    """Replace ``[**...**]`` placeholders with synthetic spans.

    Returns (deidentified_text, brat_tuples).

    If ``profile`` is None a fresh one is generated, giving each note a
    consistent synthetic identity (same patient name/MRN/dates throughout).
    """
    if profile is None:
        profile = make_note_profile()

    placeholders = extract_placeholders(note_text)
    placeholders.sort(key=lambda x: x["start"])

    replacements: list[BratT] = []
    processed_text = note_text
    offset = 0
    randformat_dict = getrandformat()

    for p in placeholders:
        entity_type = get_placeholder_entity(p["content"])

        adj_start = p["start"] + offset
        adj_end = p["end"] + offset
        orig_length = p["end"] - p["start"]

        output = get_replaced_text(entity_type, randformat_dict, profile)

        if output is None:
            # Unrecognised placeholder: strip the bracket entirely, no BRAT span
            replacement = ""
            brat_entity_type = None
            logger.debug("stripped unrecognised placeholder %r in %s", p["content"], note_id)
        else:
            replacement, brat_entity_type = output

        processed_text = processed_text[:adj_start] + replacement + processed_text[adj_end:]
        repl_length = len(replacement)
        offset += repl_length - orig_length

        # Skip BLANK and empty replacements
        if brat_entity_type and brat_entity_type != "BLANK" and replacement:
            replacements.append((adj_start, adj_start + repl_length, brat_entity_type, replacement))

    # Collapse newlines to spaces (1:1 char mapping keeps span offsets valid)
    final_text = processed_text.replace("\n", " ")
    return final_text, replacements


def write_brat_note(output_dir: Path, note_id: str, text: str, spans: list[BratT]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{note_id}.txt").write_text(text, encoding="utf-8")
    lines = [
        f"T{i}\t{etype} {start} {end}\t{surface}\n"
        for i, (start, end, etype, surface) in enumerate(spans, 1)
    ]
    (output_dir / f"{note_id}.ann").write_text("".join(lines), encoding="utf-8")


def process_noteevents_to_brat_flat(
    csv_path: Path,
    output_dir: Path,
    *,
    chunksize: int = 1000,
    max_notes: int | None = None,
    text_column: str = "TEXT",
    id_formatter: Callable[[int, object], str] | None = None,
    progress_every: int = 1000,
) -> int:
    """Stream ``csv_path`` and write paired BRAT files into flat ``output_dir``.

    Uses CHARTDATE column (if present) to anchor synthetic dates per note.
    Returns number of notes written.
    """
    try:
        import pandas as pd
    except ImportError as e:
        raise ImportError(
            "processing MIMIC NOTEEVENTS requires pandas; "
            "install with: pip install pypedeid[scripts]"
        ) from e

    output_dir.mkdir(parents=True, exist_ok=True)
    notes_written = 0

    def default_id(chunk_num: int, row_index: object) -> str:
        return f"note_{chunk_num}_{row_index}"

    fmt = id_formatter or default_id

    for chunk_num, chunk in enumerate(
        pd.read_csv(csv_path, chunksize=chunksize, low_memory=False)
    ):
        for idx, row in chunk.iterrows():
            raw = row.get(text_column)
            if pd.isna(raw):
                continue
            note_text = str(raw)
            note_id = fmt(chunk_num, idx)

            admit_date = _parse_chartdate(row.get("CHARTDATE"))
            profile = make_note_profile(admit_date=admit_date)

            processed_text, replacements = process_note_text(
                note_text, note_id=note_id, profile=profile
            )
            write_brat_note(output_dir, note_id, processed_text, replacements)
            notes_written += 1
            if progress_every and notes_written % progress_every == 0:
                logger.info("Processed %s notes", notes_written)
            if max_notes is not None and notes_written >= max_notes:
                logger.info("Stopped after %s notes (max_notes)", max_notes)
                return notes_written

    return notes_written


def run_noteevents_pipeline(
    csv_path: Path,
    output_root: Path,
    *,
    chunksize: int = 1000,
    max_notes: int | None = None,
    merge_adjacent_patient: bool = True,
    split_into_subdirs: bool = True,
    train_ratio: float = 0.75,
    valid_ratio: float = 0.05,
    test_ratio: float = 0.20,
    split_seed: int = 42,
) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    process_noteevents_to_brat_flat(
        csv_path,
        output_root,
        chunksize=chunksize,
        max_notes=max_notes,
    )
    if merge_adjacent_patient:
        merge_brat_directory_flat(output_root, output_root)
    if split_into_subdirs:
        split_brat_directory_to_corpus(
            output_root,
            output_root,
            train_ratio=train_ratio,
            valid_ratio=valid_ratio,
            test_ratio=test_ratio,
            seed=split_seed,
        )
