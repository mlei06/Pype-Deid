"""High-level LLM clinical-note synthesizer (model + prompt + injectable components)."""

from __future__ import annotations

from typing import Any

from pypedeid.synthesis.client import LLMClient
from pypedeid.synthesis.components import CompositePromptParts
from pypedeid.synthesis.parse import parse_synthesis_response
from pypedeid.synthesis.template import SynthesizerPromptTemplate, default_clinical_note_synthesis_template
from pypedeid.synthesis.types import ChatMessage, FewShotExample, SynthesisResult


class LLMSynthesizer:
    """
    Composed of:

    - ``llm``: anything implementing :class:`LLMClient`
    - ``phi_types``: label strings (dictionary keys / entity types)
    - ``examples``: :class:`FewShotExample` list for one/few-shot
    - ``prompt_template``: system/user strings with ``{phi_types_block}``, ``{examples_block}``, ``{special_rules}``
    - ``parts``: formatters that turn types/examples into those blocks (:class:`CompositePromptParts`)

    Subclass or swap ``parts`` / ``prompt_template`` for full control over wording; swap ``llm`` for
    provider, model name, etc. (model lives on the client, e.g. :class:`OpenAICompatibleChatClient`).
    """

    def __init__(
        self,
        llm: LLMClient,
        *,
        phi_types: list[str],
        examples: list[FewShotExample],
        prompt_template: SynthesizerPromptTemplate | None = None,
        parts: CompositePromptParts | None = None,
        special_rules: str = "",
    ) -> None:
        self.llm = llm
        self.phi_types = list(phi_types)
        self.examples = list(examples)
        self.prompt_template = prompt_template or default_clinical_note_synthesis_template()
        self.parts = parts or CompositePromptParts()
        self.special_rules = special_rules

    def build_messages(
        self,
        *,
        user_extra: str | None = None,
        system_extra: dict[str, str] | None = None,
    ) -> list[ChatMessage]:
        phi_block = self.parts.phi_types_block(self.phi_types)
        ex_block = self.parts.examples_block(self.examples)
        merge_system = {**(system_extra or {})}
        for k, v in self.parts.extra_system_injections.items():
            if isinstance(v, str):
                merge_system.setdefault(k, v)
        system = self.prompt_template.render_system(
            phi_types_block=phi_block,
            examples_block=ex_block,
            special_rules=self.special_rules,
            **merge_system,
        )
        user = self.prompt_template.render_user()
        if user_extra:
            user = f"{user}\n\n{user_extra}"
        return [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=user),
        ]

    def generate_one(
        self,
        *,
        user_extra: str | None = None,
        system_extra: dict[str, str] | None = None,
        **llm_kwargs: Any,
    ) -> SynthesisResult:
        messages = self.build_messages(user_extra=user_extra, system_extra=system_extra)
        raw = self.llm.complete(messages, **llm_kwargs)
        return parse_synthesis_response(raw)
