"""Pluggable pieces injected into synthesizer prompts (PHI types + few-shot formatting)."""

from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

from pypedeid.synthesis.types import FewShotExample


@runtime_checkable
class PhiTypesFormatter(Protocol):
    def format_phi_types(self, types: list[str]) -> str:
        """Return text describing which PHI labels the model should generate and extract."""


@runtime_checkable
class FewShotFormatter(Protocol):
    def format_examples(self, examples: list[FewShotExample]) -> str:
        """Return text embedding one/few-shot answer exemplars."""


class DefaultPhiTypesFormatter:
    """Comma-separated quoted labels, suitable for listing allowed dictionary keys."""

    def __init__(self, *, preamble: str | None = None) -> None:
        self.preamble = preamble or (
            "Protected Health Information (PHI) includes the following entity types"
        )

    def format_phi_types(self, types: list[str]) -> str:
        inner = ", ".join(f"'{t}'" for t in types)
        return f"{self.preamble}: {inner}."


class DefaultFewShotFormatter:
    """
    Formats examples like::

        Clinical Note: \"...\", PHI: \"PERSON\": [...], \"ORGANIZATION\": [...]
    """

    def __init__(self, *, header: str | None = None, phi_key_style: str = "quoted") -> None:
        self.header = header or "Here are some sample answers I want:"
        self.phi_key_style = phi_key_style  # "quoted" or "bare"

    def _format_phi_dict(self, phi: dict[str, list[str]]) -> str:
        parts: list[str] = []
        for k, values in phi.items():
            key = json.dumps(k) if self.phi_key_style == "quoted" else k
            parts.append(f"{key}:{json.dumps(values)}")
        return ", ".join(parts)

    def format_examples(self, examples: list[FewShotExample]) -> str:
        blocks: list[str] = []
        if self.header:
            blocks.append(self.header)
        for ex in examples:
            note_esc = json.dumps(ex.clinical_note)
            phi_part = self._format_phi_dict(ex.phi)
            blocks.append(f"Clinical Note: {note_esc}, PHI: {phi_part}")
        return "\n".join(blocks)


class CompositePromptParts:
    """
    Bundles optional helpers so users can swap only the PHI block, only examples, or both.

    Pass callables or objects implementing the small protocols; defaults match typical usage.
    """

    def __init__(
        self,
        phi_types_formatter: PhiTypesFormatter | None = None,
        few_shot_formatter: FewShotFormatter | None = None,
        *,
        extra_system_injections: dict[str, Any] | None = None,
    ) -> None:
        self.phi_types_formatter = phi_types_formatter or DefaultPhiTypesFormatter()
        self.few_shot_formatter = few_shot_formatter or DefaultFewShotFormatter()
        self.extra_system_injections = extra_system_injections or {}

    def phi_types_block(self, types: list[str]) -> str:
        return self.phi_types_formatter.format_phi_types(types)

    def examples_block(self, examples: list[FewShotExample]) -> str:
        if not examples:
            return ""
        return self.few_shot_formatter.format_examples(examples)
