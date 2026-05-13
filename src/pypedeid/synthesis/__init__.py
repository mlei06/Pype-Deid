from pypedeid.synthesis.align import drop_overlapping_spans, phi_dict_to_spans
from pypedeid.synthesis.document import synthesis_result_to_annotated_document
from pypedeid.synthesis.client import LLMClient, OpenAICompatibleChatClient, StaticResponseClient
from pypedeid.synthesis.components import (
    CompositePromptParts,
    DefaultFewShotFormatter,
    DefaultPhiTypesFormatter,
    FewShotFormatter,
    PhiTypesFormatter,
)
from pypedeid.synthesis.parse import parse_synthesis_response
from pypedeid.synthesis.synthesizer import LLMSynthesizer
from pypedeid.synthesis.presets import person_title_fewshot_rules
from pypedeid.synthesis.template import SynthesizerPromptTemplate, default_clinical_note_synthesis_template
from pypedeid.synthesis.types import ChatMessage, FewShotExample, SynthesisResult

__all__ = [
    "ChatMessage",
    "CompositePromptParts",
    "DefaultFewShotFormatter",
    "DefaultPhiTypesFormatter",
    "FewShotExample",
    "FewShotFormatter",
    "LLMClient",
    "LLMSynthesizer",
    "OpenAICompatibleChatClient",
    "PhiTypesFormatter",
    "person_title_fewshot_rules",
    "phi_dict_to_spans",
    "SynthesisResult",
    "SynthesizerPromptTemplate",
    "StaticResponseClient",
    "default_clinical_note_synthesis_template",
    "drop_overlapping_spans",
    "parse_synthesis_response",
    "synthesis_result_to_annotated_document",
]
