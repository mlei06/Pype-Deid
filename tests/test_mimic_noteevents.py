from __future__ import annotations

from pathlib import Path

import pytest

from pypedeid.ingest.mimic.brat_merge import merge_adjacent_names
from pypedeid.ingest.mimic.placeholders import extract_placeholders
from pypedeid.ingest.mimic.replacement import get_placeholder_entity
from pypedeid.ingest.mimic.split import split_brat_directory_to_corpus

pytest.importorskip("faker")
from pypedeid.ingest.mimic.pipeline import (  # noqa: E402
    process_note_text,
    process_noteevents_to_brat_flat,
)


def test_extract_placeholders() -> None:
    text = "a [**Known lastname 1**] b"
    spans = extract_placeholders(text)
    assert len(spans) == 1
    assert spans[0]["content"] == "Known lastname 1"
    assert spans[0]["start"] == 2


def test_placeholder_entity_glossary() -> None:
    assert get_placeholder_entity("Known firstname 123") == "first name"
    assert get_placeholder_entity("month/year 2/2020") == "month year"


def test_process_note_text_replaces_brackets() -> None:
    text, spans = process_note_text(
        "See [**Female First Name (un) 5742**] [**Known lastname 355**] today.",
        note_id="n1",
    )
    assert "[**" not in text
    assert spans
    assert all(isinstance(s[2], str) for s in spans)


def test_merge_adjacent_patient_single_space() -> None:
    text = "Pt John Smith ok"
    anns = [(3, 7, "PATIENT", "John"), (8, 12, "PATIENT", "Smith")]
    merged = merge_adjacent_names(anns, text)
    assert len(merged) == 1
    assert merged[0][2] == "PATIENT"
    assert merged[0][3] == "John Smith"


def test_split_brat_moves_to_subdirs(tmp_path: Path) -> None:
    d = tmp_path / "flat"
    d.mkdir()
    (d / "a.txt").write_text("hello", encoding="utf-8")
    (d / "a.ann").write_text("", encoding="utf-8")
    (d / "b.txt").write_text("world", encoding="utf-8")
    (d / "b.ann").write_text("", encoding="utf-8")
    out = tmp_path / "out"
    split_brat_directory_to_corpus(
        d,
        out,
        train_ratio=0.5,
        valid_ratio=0.25,
        test_ratio=0.25,
        seed=0,
    )
    assert (out / "train").is_dir()
    moved = list((out / "train").glob("*.txt")) + list((out / "valid").glob("*.txt")) + list(
        (out / "test").glob("*.txt")
    )
    assert len(moved) == 2


def test_process_noteevents_csv_minimal(tmp_path: Path) -> None:
    pd = pytest.importorskip("pandas")
    csv_path = tmp_path / "ne.csv"
    pd.DataFrame({"ROW_ID": [1], "TEXT": ["[**Known lastname 1**] visit"]}).to_csv(
        csv_path,
        index=False,
    )
    out = tmp_path / "brat"
    n = process_noteevents_to_brat_flat(csv_path, out, chunksize=10, max_notes=1)
    assert n == 1
    txts = list(out.glob("*.txt"))
    assert len(txts) == 1
    assert "[**" not in txts[0].read_text(encoding="utf-8")
