"""Train / validation / test / deploy assignment via ``document.metadata[\"split\"]``."""

from __future__ import annotations

import random

from pypedeid.domain import AnnotatedDocument, Document


def proportional_integer_counts(n_total: int, weights: list[float]) -> list[int]:
    """
    Split ``n_total`` items across ``len(weights)`` buckets using normalized weights.
    Uses largest-remainder so counts sum exactly to ``n_total``.
    Zero or negative weights are skipped; if none are positive, splits evenly.
    """
    if n_total < 0:
        raise ValueError("n_total must be non-negative")
    if not weights:
        return []
    positive = [(i, float(w)) for i, w in enumerate(weights) if w > 0]
    if not positive:
        n = len(weights)
        if n == 0:
            return []
        props = [1.0 / n] * n
        return _largest_remainder_allocation(n_total, props)
    idxs = [i for i, _ in positive]
    wsum = sum(w for _, w in positive)
    proportions = [w / wsum for _, w in positive]
    counts_pos = _largest_remainder_allocation(n_total, proportions)
    out = [0] * len(weights)
    for j, c in zip(idxs, counts_pos):
        out[j] = c
    return out


def _largest_remainder_allocation(n: int, proportions: list[float]) -> list[int]:
    """
    Given ``n`` items and positive ``proportions`` summing to 1, return integer counts
    per bucket that sum exactly to ``n`` (Hamilton / largest remainder method).
    """
    if n == 0:
        return [0] * len(proportions)
    exact = [n * p for p in proportions]
    floors = [int(x) for x in exact]
    rem = n - sum(floors)
    remainders = sorted(
        range(len(proportions)),
        key=lambda i: (exact[i] - floors[i], i),
        reverse=True,
    )
    for j in range(rem):
        floors[remainders[j]] += 1
    return floors


def _with_split(ad: AnnotatedDocument, split: str) -> AnnotatedDocument:
    meta = dict(ad.document.metadata)
    meta["split"] = split
    doc = Document(id=ad.document.id, text=ad.document.text, metadata=meta)
    return AnnotatedDocument(document=doc, spans=list(ad.spans))


def reassign_splits(
    docs: list[AnnotatedDocument],
    split_fractions: dict[str, float],
    *,
    seed: int = 42,
    shuffle: bool = True,
) -> list[AnnotatedDocument]:
    """
    Recompute document-level splits stored in ``metadata[\"split\"]``.

    ``split_fractions`` maps split name → non-negative weight (need not sum to 1; normalized).
    When ``shuffle`` is True, assignment order is random but reproducible with ``seed``;
    when False, document order is sorted by id before the same proportional allocation
    (deterministic).

    Common names: ``train``, ``valid``, ``test``, ``deploy`` (any string keys are allowed).
    """
    if not split_fractions:
        return list(docs)
    if not docs:
        return []

    names = [k for k, w in split_fractions.items() if w > 0]
    weights = [float(split_fractions[k]) for k in names]
    if not names:
        return list(docs)

    total_w = sum(weights)
    proportions = [w / total_w for w in weights]
    n = len(docs)
    counts = _largest_remainder_allocation(n, proportions)

    rng = random.Random(seed)
    indices = list(range(n))
    if shuffle:
        rng.shuffle(indices)
    else:
        indices.sort(key=lambda i: docs[i].document.id)

    split_by_index: dict[int, str] = {}
    pos = 0
    for split_name, cnt in zip(names, counts):
        for _ in range(cnt):
            split_by_index[indices[pos]] = split_name
            pos += 1

    return [_with_split(docs[i], split_by_index[i]) for i in range(n)]
