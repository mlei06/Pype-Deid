"""Shuffle and split flat BRAT files into ``train/`` ``valid/`` ``test/`` subfolders."""

from __future__ import annotations

import random
import shutil
from pathlib import Path


def split_brat_directory_to_corpus(
    flat_dir: Path,
    output_root: Path,
    *,
    train_ratio: float = 0.75,
    valid_ratio: float = 0.05,
    test_ratio: float = 0.20,
    seed: int = 42,
) -> None:
    """
    Move ``*.txt`` / ``*.ann`` from ``flat_dir`` into ``output_root/{train,valid,test}/``.

    Ratios need not sum to 1.0; they are renormalized. The remainder after ``train`` and
    ``valid`` assignments goes to ``test``.
    """
    flat_dir = flat_dir.resolve()
    output_root = output_root.resolve()

    total_r = train_ratio + valid_ratio + test_ratio
    if total_r <= 0:
        raise ValueError("sum of split ratios must be positive")
    tr = train_ratio / total_r
    vr = valid_ratio / total_r

    rng = random.Random(seed)
    note_ids = sorted(p.stem for p in flat_dir.glob("*.txt"))
    rng.shuffle(note_ids)

    n = len(note_ids)
    n_train = int(n * tr)
    n_valid = int(n * vr)
    split_map = {
        "train": note_ids[:n_train],
        "valid": note_ids[n_train : n_train + n_valid],
        "test": note_ids[n_train + n_valid :],
    }

    for split in split_map:
        (output_root / split).mkdir(parents=True, exist_ok=True)

    for split, ids in split_map.items():
        for note_id in ids:
            for ext in (".txt", ".ann"):
                src = flat_dir / f"{note_id}{ext}"
                if src.is_file():
                    shutil.move(str(src), str(output_root / split / f"{note_id}{ext}"))
