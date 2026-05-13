"""User-editable prompt templates with slots for injected components."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SynthesizerPromptTemplate(BaseModel):
    """
    String templates for chat messages. Use placeholders:

    - ``{phi_types_block}``: where allowed labels / instructions go
    - ``{examples_block}``: few-shot exemplars (may be empty)
    - ``{special_rules}``: extra instructions (e.g. PERSON “Dr.” handling)

    Any other ``{key}`` must be supplied via ``render_system(..., **kwargs)``.
    """

    system_template: str
    user_template: str = Field(
        default=(
            "Please generate one simulated clinical note along with a dictionary that "
            "contains all Protected Health Information (PHI) entities within the note, "
            "using the required output format."
        )
    )

    def render_system(
        self,
        *,
        phi_types_block: str,
        examples_block: str,
        special_rules: str = "",
        **extra: str,
    ) -> str:
        ctx = {
            "phi_types_block": phi_types_block,
            "examples_block": examples_block,
            "special_rules": special_rules,
            **extra,
        }
        return self.system_template.format(**ctx)

    def render_user(self, **extra: str) -> str:
        return self.user_template.format(**extra)


def default_clinical_note_synthesis_template() -> SynthesizerPromptTemplate:
    """Prompt shaped like the user’s example (customize PHI types / examples via components)."""
    system = """Act as an experienced doctor. Your goal is to generate simulated clinical notes. A clinical note contains {phi_types_block}

You are asked to generate simulated clinical notes with PHI information and then extract all PHI entities within the simulated clinical notes and store them in a dictionary.

The expected output format is: Clinical Note: Simulated_Note, PHI: Note_PHI, where Simulated_Note is the simulated note text, and Note_PHI is a dictionary containing all PHI elements within the corresponding simulated note. Use clear delimiters so the note can be parsed: put the clinical note in double quotes after `Clinical Note:` like Clinical Note: "..." .

Dictionary Note_PHI should only include keys from the PHI types listed above; use empty lists for types with no mentions.

{special_rules}

{examples_block}
""".strip()
    return SynthesizerPromptTemplate(system_template=system)
