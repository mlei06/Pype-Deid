"""Optional: turn label → string lists into character spans via naive phrase search."""

from __future__ import annotations

from pypedeid.domain import EntitySpan


def phi_dict_to_spans(
    text: str,
    phi_entities: dict[str, list[str]],
    *,
    source: str = "llm_phi_dict",
) -> list[EntitySpan]:
    """
    For each surface string (in arbitrary key order), take the first unseen occurrence
    in ``text`` starting from the previous match end. Best-effort only; overlapping or
    repeated entities may need manual or model-level span output.
    """
    spans: list[EntitySpan] = []
    cursor = 0
    for label, surfaces in sorted(phi_entities.items()):
        for surface in surfaces:
            s = surface.strip()
            if not s:
                continue
            pos = text.find(s, cursor)
            if pos == -1:
                pos = text.find(s)
            if pos == -1:
                continue
            start, end = pos, pos + len(s)
            spans.append(
                EntitySpan(start=start, end=end, label=label, source=source)
            )
            cursor = max(cursor, end)
    spans.sort(key=lambda sp: (sp.start, sp.end))
    return spans


def drop_overlapping_spans(spans: list[EntitySpan]) -> list[EntitySpan]:
    """
    Keep a non-overlapping subset in start order (greedy: earlier span wins; later overlaps dropped).
    """
    ordered = sorted(spans, key=lambda s: (s.start, s.end))
    out: list[EntitySpan] = []
    last_end = -1
    for s in ordered:
        if s.start >= last_end:
            out.append(s)
            last_end = s.end
    return out
