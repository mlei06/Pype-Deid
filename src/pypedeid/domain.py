from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class Document(BaseModel):
    id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class EntitySpan(BaseModel):
    """A labeled character span produced by a detector or stored as gold annotation."""

    start: int
    end: int
    label: str
    confidence: float | None = None
    source: str | None = None

    @model_validator(mode="after")
    def span_order(self) -> EntitySpan:
        if self.start < 0 or self.end < 0 or self.start >= self.end:
            raise ValueError(f"invalid span bounds: start={self.start}, end={self.end}")
        return self


class AnnotatedDocument(BaseModel):
    document: Document
    spans: list[EntitySpan] = Field(default_factory=list)

    @model_validator(mode="after")
    def spans_match_text(self) -> AnnotatedDocument:
        n = len(self.document.text)
        for s in self.spans:
            if s.end > n:
                raise ValueError(
                    f"span [{s.start}:{s.end}) exceeds text length {n} for doc {self.document.id!r}"
                )
        return self

    def with_spans(self, spans: list[EntitySpan]) -> AnnotatedDocument:
        return AnnotatedDocument(document=self.document, spans=spans)


def tag_replace(text: str, spans: list[EntitySpan]) -> str:
    """Replace spans with ``[LABEL]`` tags, handling overlaps.

    When spans overlap, the longest span wins.  Ties are broken by earliest
    start, then alphabetical label.  Fully or partially covered spans are
    dropped so replacements never corrupt each other.
    """
    if not spans:
        return text

    sorted_spans = sorted(
        spans,
        key=lambda s: (-(s.end - s.start), s.start, s.label),
    )

    selected: list[EntitySpan] = []
    for s in sorted_spans:
        if any(s.start < sel.end and s.end > sel.start for sel in selected):
            continue
        selected.append(s)

    selected.sort(key=lambda s: s.start, reverse=True)
    result = text
    for s in selected:
        result = result[: s.start] + f"[{s.label}]" + result[s.end :]
    return result
