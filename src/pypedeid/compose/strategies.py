"""Merge, proportional, and interleave strategies over pre-flattened document lists."""

from __future__ import annotations

import random
from typing import Literal

from pypedeid.domain import AnnotatedDocument
from pypedeid.transform.splits import proportional_integer_counts

CompositionStrategy = Literal["merge", "proportional", "interleave"]


def _allocate_counts_with_caps(
    n_target: int, weights: list[float], caps: list[int]
) -> list[int]:
    """Target counts per bucket summing to at most ``n_target``, each <= cap."""
    if len(weights) != len(caps):
        raise ValueError("weights and caps must have the same length")
    if n_target <= 0:
        return [0] * len(caps)
    max_possible = sum(caps)
    t = min(n_target, max_possible)
    raw = proportional_integer_counts(t, weights)
    take = [min(raw[i], caps[i]) for i in range(len(caps))]
    deficit = t - sum(take)
    while deficit > 0:
        candidates = [i for i in range(len(caps)) if take[i] < caps[i]]
        if not candidates:
            break
        best = max(candidates, key=lambda i: (weights[i], -i))
        take[best] += 1
        deficit -= 1
    return take


def compose_merge(
    flat_sources: list[list[AnnotatedDocument]],
    *,
    seed: int | None = None,
    shuffle: bool = False,
) -> list[AnnotatedDocument]:
    out: list[AnnotatedDocument] = []
    for block in flat_sources:
        out.extend(block)
    if shuffle and out:
        rng = random.Random(seed)
        rng.shuffle(out)
    return out


def compose_interleave(
    flat_sources: list[list[AnnotatedDocument]],
    *,
    seed: int | None = None,
    shuffle: bool = False,
) -> list[AnnotatedDocument]:
    """Round-robin across sources until all are exhausted."""
    out: list[AnnotatedDocument] = []
    ptrs = [0] * len(flat_sources)
    lens = [len(b) for b in flat_sources]
    while True:
        moved = False
        for i, block in enumerate(flat_sources):
            p = ptrs[i]
            if p < lens[i]:
                out.append(block[p])
                ptrs[i] += 1
                moved = True
        if not moved:
            break
    if shuffle and out:
        rng = random.Random(seed)
        rng.shuffle(out)
    return out


def compose_proportional(
    flat_sources: list[list[AnnotatedDocument]],
    weights: list[float],
    *,
    target_documents: int | None = None,
    seed: int = 42,
) -> list[AnnotatedDocument]:
    """
    Without replacement: choose per-source sample sizes matching normalized weights,
    capped by each source size. If ``target_documents`` is None, uses the total
    number of input documents (after caps, the realized total may be lower only if
    allocation is impossible — here we cap ``target_documents`` by total size).
    """
    if len(weights) != len(flat_sources):
        raise ValueError("weights length must match number of sources")
    caps = [len(b) for b in flat_sources]
    total_available = sum(caps)
    if total_available == 0:
        return []
    t = target_documents if target_documents is not None else total_available
    t = max(0, min(t, total_available))
    counts = _allocate_counts_with_caps(t, weights, caps)

    rng = random.Random(seed)
    out: list[AnnotatedDocument] = []
    for block, k in zip(flat_sources, counts):
        if k <= 0:
            continue
        idxs = list(range(len(block)))
        rng.shuffle(idxs)
        for j in idxs[:k]:
            out.append(block[j])
    rng.shuffle(out)
    return out


def run_composition_strategy(
    flat_sources: list[list[AnnotatedDocument]],
    strategy: CompositionStrategy,
    *,
    weights: list[float] | None = None,
    target_documents: int | None = None,
    seed: int = 42,
    shuffle: bool = False,
) -> list[AnnotatedDocument]:
    if strategy == "merge":
        return compose_merge(flat_sources, seed=seed, shuffle=shuffle)
    if strategy == "interleave":
        return compose_interleave(flat_sources, seed=seed, shuffle=shuffle)
    if strategy == "proportional":
        w = weights if weights is not None else [1.0] * len(flat_sources)
        return compose_proportional(
            flat_sources, w, target_documents=target_documents, seed=seed
        )
    raise ValueError(f"unknown strategy: {strategy!r}")
