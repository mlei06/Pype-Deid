"""Core types for LLM-driven clinical note synthesis."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class FewShotExample(BaseModel):
    """One labeled example: full note text and PHI as label → surface strings (no spans)."""

    clinical_note: str
    phi: dict[str, list[str]] = Field(default_factory=dict)


class SynthesisResult(BaseModel):
    """Parsed model output: generated note and entity lists per label."""

    clinical_note: str
    phi_entities: dict[str, list[str]] = Field(default_factory=dict)
    raw_completion: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
