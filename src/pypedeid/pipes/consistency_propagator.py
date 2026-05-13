"""ConsistencyPropagator — document-level span propagation.

If "John Smith" is detected as PATIENT once with high confidence, every other
occurrence of "John Smith" in the same document should also be flagged — even
if the detector missed it in a different context.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from pypedeid.domain import AnnotatedDocument, EntitySpan
from pypedeid.pipes.base import ConfigurablePipe


class ConsistencyPropagatorConfig(BaseModel):
    """Configuration for :class:`ConsistencyPropagatorPipe`."""

    min_confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Only propagate spans with confidence at or above this threshold.",
    )
    case_sensitive: bool = Field(
        default=False,
        description="Whether text matching is case-sensitive.",
    )
    labels: list[str] | None = Field(
        default=None,
        description="Restrict propagation to these labels; None = all labels.",
    )
    source_name: str = Field(
        default="propagated",
        description="Source tag for newly propagated spans.",
    )


def _find_all_occurrences(text: str, substring: str, *, case_sensitive: bool) -> list[int]:
    """Return all start positions of *substring* in *text*."""
    if not substring:
        return []
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.escape(substring)
    return [m.start() for m in re.finditer(pattern, text, flags)]


class ConsistencyPropagatorPipe(ConfigurablePipe):
    """SpanTransformer that finds all occurrences of detected span text in the document."""

    def __init__(self, config: ConsistencyPropagatorConfig | None = None) -> None:
        self._config = config or ConsistencyPropagatorConfig()

    def forward(self, doc: AnnotatedDocument) -> AnnotatedDocument:
        if not doc.spans:
            return doc

        text = doc.document.text
        cfg = self._config
        allowed_labels = set(cfg.labels) if cfg.labels else None

        # Collect high-confidence spans eligible for propagation.
        # Spans with confidence=None are treated as 1.0 (deterministic match),
        # so rule-based detector spans are always eligible as seeds.
        seed_spans: list[EntitySpan] = []
        for s in doc.spans:
            effective = s.confidence if s.confidence is not None else 1.0
            if effective < cfg.min_confidence:
                continue
            if allowed_labels and s.label not in allowed_labels:
                continue
            seed_spans.append(s)

        # Build set of existing span boundaries for dedup
        existing = {(s.start, s.end, s.label) for s in doc.spans}

        # Deduplicate seed surface texts per label
        seen_texts: dict[tuple[str, str], EntitySpan] = {}
        for s in seed_spans:
            surface = text[s.start : s.end]
            key = (surface.lower() if not cfg.case_sensitive else surface, s.label)
            if key not in seen_texts:
                seen_texts[key] = s

        # Find all occurrences and create new spans
        new_spans: list[EntitySpan] = []
        for (surface_key, label), seed in seen_texts.items():
            original_surface = text[seed.start : seed.end]
            positions = _find_all_occurrences(text, original_surface, case_sensitive=cfg.case_sensitive)
            for pos in positions:
                end = pos + len(original_surface)
                if (pos, end, label) not in existing:
                    new_spans.append(
                        EntitySpan(
                            start=pos,
                            end=end,
                            label=label,
                            confidence=seed.confidence,
                            source=cfg.source_name,
                        )
                    )
                    existing.add((pos, end, label))

        all_spans = list(doc.spans) + new_spans
        all_spans.sort(key=lambda s: (s.start, s.end))
        return doc.with_spans(all_spans)
