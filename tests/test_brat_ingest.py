from __future__ import annotations

from pathlib import Path

from pypedeid.ingest.brat import load_brat_directory


def test_load_brat_directory(tmp_path: Path) -> None:
    d = tmp_path / "brat"
    d.mkdir()
    (d / "n1.txt").write_text("CALVERT HOSPITAL here", encoding="utf-8")
    (d / "n1.ann").write_text("T1\tHOSPITAL 0 16\tCALVERT HOSPITAL\n", encoding="utf-8")

    docs = load_brat_directory(d)
    assert len(docs) == 1
    assert docs[0].document.text == "CALVERT HOSPITAL here"
    assert len(docs[0].spans) == 1
    assert docs[0].spans[0].label == "HOSPITAL"
    assert docs[0].spans[0].start == 0
    assert docs[0].spans[0].end == 16
