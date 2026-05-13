"""Surrogate text + span alignment.

Given ``original_text`` and a list of character-offset ``EntitySpan`` annotations,
produce a new string where each span's substring is replaced with a realistic
surrogate (via :class:`SurrogateGenerator`), plus a new list of
``EntitySpan``\\s whose offsets point into the *surrogate* string.

Algorithm: single left-to-right pass with a cumulative-offset counter. Spans
are required to be non-overlapping (callers should pre-resolve via
``resolve_spans``); overlapping input raises ``ValueError``.
"""

from __future__ import annotations

from pypedeid.domain import EntitySpan


def _check_non_overlapping(spans: list[EntitySpan]) -> None:
    prev_end = -1
    for s in spans:
        if s.start < prev_end:
            raise ValueError(
                f"Overlapping span [{s.start}:{s.end}] conflicts with previous end {prev_end}; "
                "resolve overlaps (e.g. via resolve_spans) before calling surrogate_text_with_spans."
            )
        prev_end = s.end


def surrogate_text_with_spans(
    original_text: str,
    spans: list[EntitySpan],
    *,
    seed: int | None = None,
    consistency: bool = True,
) -> tuple[str, list[EntitySpan]]:
    """Return ``(surrogate_text, surrogate_spans)``.

    - ``surrogate_spans[i]`` points at the replacement substring for
      ``spans[i]`` in the output.
    - Preserves ordering and per-span metadata (label, confidence, source).
    - Deterministic when ``seed`` is set and ``consistency`` is unchanged.
    """
    if not spans:
        return original_text, []

    # Import here so this module is importable without ``faker``.
    from pypedeid.pipes.surrogate.strategies import SurrogateGenerator

    ordered = sorted(spans, key=lambda s: (s.start, s.end))
    _check_non_overlapping(ordered)

    gen = SurrogateGenerator(seed=seed, consistency=consistency)

    out_parts: list[str] = []
    out_spans: list[EntitySpan] = []
    cursor = 0  # next index in original_text to copy from
    offset = 0  # cumulative delta (len surrogate - len original) so far

    for s in ordered:
        if s.start > cursor:
            out_parts.append(original_text[cursor:s.start])
        original = original_text[s.start:s.end]
        replacement = gen.replace(s.label, original)
        new_start = s.start + offset
        out_parts.append(replacement)
        new_end = new_start + len(replacement)
        out_spans.append(
            EntitySpan(
                start=new_start,
                end=new_end,
                label=s.label,
                confidence=s.confidence,
                source=s.source,
            )
        )
        offset += len(replacement) - (s.end - s.start)
        cursor = s.end

    if cursor < len(original_text):
        out_parts.append(original_text[cursor:])

    return "".join(out_parts), out_spans
