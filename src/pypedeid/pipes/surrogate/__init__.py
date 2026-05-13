"""Surrogate text-replacement helpers used by ``output_mode='surrogate'`` (and CLI/exports).

Public entry points:

- :func:`pypedeid.pipes.surrogate.align.surrogate_text_with_spans` — generate
  surrogate text plus aligned spans for a single document.
- :class:`pypedeid.pipes.surrogate.strategies.SurrogateGenerator` — Faker-backed
  per-label surrogate strategies.
- :func:`pypedeid.pipes.surrogate.packs.get_surrogate_pack` — registered
  per-label strategy packs (``clinical_phi``, ``generic_pii``, custom).
"""
