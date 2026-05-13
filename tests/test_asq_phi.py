from __future__ import annotations

from pathlib import Path

from pypedeid.ingest.asq_phi import (
    iter_asq_phi_records,
    records_to_annotated_dicts,
    write_asq_phi_brat_corpus,
    write_asq_phi_brat_flat,
)


def test_parse_sample_block(tmp_path: Path) -> None:
    p = tmp_path / "sample.txt"
    p.write_text(
        """===QUERY===
Hello Anna S. at Methodist Hospital on April 12, 2023.
===PHI_TAGS===
{"identifier_type": "NAME", "value": "Anna S."}
{"identifier_type": "GEOGRAPHIC_LOCATION", "value": "Methodist Hospital"}
{"identifier_type": "DATE", "value": "April 12, 2023"}

===QUERY===
No phi here.
===PHI_TAGS===

""",
        encoding="utf-8",
    )
    recs = iter_asq_phi_records(p)
    assert len(recs) == 2
    assert "Anna S." in recs[0][0]
    assert len(recs[0][1]) == 3
    assert recs[1][1] == []

    objs = records_to_annotated_dicts(recs, single_line_query=False)
    assert objs[0]["document"]["id"] == "asq_1"
    spans = objs[0]["spans"]
    assert spans[0]["label"] == "NAME"
    txt = objs[0]["document"]["text"]
    assert txt[spans[0]["start"] : spans[0]["end"]] == "Anna S."


def test_brat_flat_and_corpus(tmp_path: Path) -> None:
    recs = [(f"line {i}", []) for i in range(12)]
    objs = records_to_annotated_dicts(recs, single_line_query=True)
    flat = tmp_path / "flat"
    write_asq_phi_brat_flat(flat, objs)
    assert len(list(flat.glob("*.txt"))) == 12

    corp = tmp_path / "corpus"
    write_asq_phi_brat_corpus(corp, objs, seed=1, train_ratio=0.5, val_ratio=0.25)
    n_train = len(list((corp / "train").glob("*.txt")))
    n_val = len(list((corp / "valid").glob("*.txt")))
    n_test = len(list((corp / "test").glob("*.txt")))
    assert n_train + n_val + n_test == 12
    assert (corp / "train" / "note_1.txt").is_file()


def test_single_line_normalize(tmp_path: Path) -> None:
    p = tmp_path / "s.txt"
    p.write_text(
        """===QUERY===
A  B   C
===PHI_TAGS===

""",
        encoding="utf-8",
    )
    recs = iter_asq_phi_records(p)
    objs = records_to_annotated_dicts(recs, single_line_query=True)
    assert objs[0]["document"]["text"] == "A B C"
