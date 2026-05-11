"""Surrogate text-replacement helpers used by ``output_mode='surrogate'`` (and CLI/exports).

Public entry points:

- :func:`clinical_deid.pipes.surrogate.align.surrogate_text_with_spans` — generate
  surrogate text plus aligned spans for a single document.
- :class:`clinical_deid.pipes.surrogate.strategies.SurrogateGenerator` — Faker-backed
  per-label surrogate strategies.
- :func:`clinical_deid.pipes.surrogate.packs.get_surrogate_pack` — registered
  per-label strategy packs (``clinical_phi``, ``generic_pii``, custom).
"""
