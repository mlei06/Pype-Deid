from __future__ import annotations

from pypedeid.domain import AnnotatedDocument, Document
from pypedeid.synthesis import (
    CompositePromptParts,
    FewShotExample,
    LLMSynthesizer,
    StaticResponseClient,
    SynthesizerPromptTemplate,
    SynthesisResult,
    default_clinical_note_synthesis_template,
    parse_synthesis_response,
    person_title_fewshot_rules,
    phi_dict_to_spans,
    synthesis_result_to_annotated_document,
)
from pypedeid.synthesis.align import drop_overlapping_spans


def test_parse_response_user_style() -> None:
    raw = (
        'Clinical Note: "Chief Complaint: Fall", PHI: '
        '"PERSON":["Jimmy Chen"], "AGE":["30"], "DATE_TIME":["3/22/2023"]'
    )
    r = parse_synthesis_response(raw)
    assert "Fall" in r.clinical_note
    assert r.phi_entities["PERSON"] == ["Jimmy Chen"]
    assert r.phi_entities["DATE_TIME"] == ["3/22/2023"]


def test_parse_json_phi_object() -> None:
    raw = (
        'Clinical Note: "Hello", PHI: {"PERSON": ["A B"], "AGE": ["40"]}'
    )
    r = parse_synthesis_response(raw)
    assert r.phi_entities["PERSON"] == ["A B"]


def test_synthesizer_build_messages_injection() -> None:
    class CustomPhi:
        def format_phi_types(self, types: list[str]) -> str:
            return "TYPES:" + "|".join(types)

    ex = FewShotExample(clinical_note="n1", phi={"PERSON": ["x"]})
    llm = StaticResponseClient('"stub"')
    syn = LLMSynthesizer(
        llm,
        phi_types=["PERSON", "AGE"],
        examples=[ex],
        parts=CompositePromptParts(phi_types_formatter=CustomPhi()),
        special_rules="RULES HERE",
    )
    msgs = syn.build_messages()
    assert msgs[0].role == "system"
    assert "TYPES:PERSON|AGE" in msgs[0].content
    assert "RULES HERE" in msgs[0].content
    assert "n1" in msgs[0].content
    assert "Clinical Note" in msgs[0].content


def test_generate_one_uses_parser() -> None:
    completion = (
        'Clinical Note: "Pt stable", PHI: {"ZIP": ["12345"]}'
    )
    syn = LLMSynthesizer(
        StaticResponseClient(completion),
        phi_types=["ZIP"],
        examples=[],
        prompt_template=default_clinical_note_synthesis_template(),
    )
    out = syn.generate_one()
    assert out.clinical_note == "Pt stable"
    assert out.phi_entities["ZIP"] == ["12345"]


def test_custom_user_template() -> None:
    t = SynthesizerPromptTemplate(
        system_template="SYS {phi_types_block} {examples_block} {special_rules}",
        user_template="CUSTOM USER",
    )
    syn = LLMSynthesizer(
        StaticResponseClient("x"),
        phi_types=["A"],
        examples=[],
        prompt_template=t,
    )
    assert syn.build_messages()[1].content == "CUSTOM USER"


def test_phi_dict_to_spans_ordered() -> None:
    text = "Jimmy Chen is 30 years old."
    spans = phi_dict_to_spans(
        text,
        {"PERSON": ["Jimmy Chen"], "AGE": ["30"]},
    )
    ad = AnnotatedDocument(document=Document(id="1", text=text), spans=spans)
    assert len(ad.spans) == 2
    assert ad.document.text[ad.spans[0].start : ad.spans[0].end] == "Jimmy Chen"


def test_person_title_preset_non_empty() -> None:
    assert "Dr." in person_title_fewshot_rules()


def test_synthesis_result_to_annotated_document() -> None:
    r = SynthesisResult(
        clinical_note="John is 40 years old.",
        phi_entities={"PERSON": ["John"], "AGE": ["40"]},
        raw_completion="x",
    )
    ad = synthesis_result_to_annotated_document(r, document_id="doc1")
    assert ad.document.id == "doc1"
    assert ad.document.metadata["phi_entities"]["PERSON"] == ["John"]
    assert len(ad.spans) >= 1


def test_drop_overlapping_spans() -> None:
    from pypedeid.domain import EntitySpan

    s = [
        EntitySpan(start=0, end=3, label="A"),
        EntitySpan(start=1, end=4, label="B"),
    ]
    kept = drop_overlapping_spans(s)
    assert len(kept) == 1
    assert kept[0].start == 0
