"""Load-normalize-compose entrypoint for multiple corpora."""

from __future__ import annotations

from pypedeid.compose.flatten import flatten_corpus
from pypedeid.compose.strategies import CompositionStrategy, run_composition_strategy
from pypedeid.domain import AnnotatedDocument


def compose_corpora(
    source_documents: list[list[AnnotatedDocument]],
    *,
    strategy: CompositionStrategy = "merge",
    weights: list[float] | None = None,
    target_documents: int | None = None,
    seed: int = 42,
    shuffle: bool = False,
    id_prefix: str = "s",
    provenance: bool = True,
) -> list[AnnotatedDocument]:
    """
    Composition over any number of sources.

    Each source is first *flattened*: BRAT-style ``metadata[\"split\"]`` from folder layout
    is cleared (and optionally recorded as provenance). Document ids are namespaced as
    ``{id_prefix}{i}__{original_id}`` to avoid collisions.

    Strategies:
    - ``merge``: concatenate sources in order; optional ``shuffle``.
    - ``interleave``: round-robin; optional ``shuffle`` after interleave.
    - ``proportional``: sample without replacement to match ``weights``; optional
      ``target_documents`` (default: use all available docs).
    """
    if not source_documents:
        return []
    flat = [
        flatten_corpus(block, i, id_prefix=id_prefix, provenance=provenance)
        for i, block in enumerate(source_documents)
    ]
    return run_composition_strategy(
        flat,
        strategy,
        weights=weights,
        target_documents=target_documents,
        seed=seed,
        shuffle=shuffle,
    )
