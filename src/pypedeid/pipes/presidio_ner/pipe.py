from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

from pypedeid.domain import AnnotatedDocument, EntitySpan
from pypedeid.pipes.base import ConfigurablePipe
from pypedeid.pipes.detector_label_mapping import (
    accumulate_spans,
    apply_detector_label_mapping,
    detector_label_mapping_field,
    effective_detector_labels,
)
from pypedeid.pipes.ui_schema import field_ui


# Presidio entity → our PHI label mapping
DEFAULT_ENTITY_MAP: dict[str, str] = {
    "PERSON": "NAME",
    "DATE_TIME": "DATE",
    "PHONE_NUMBER": "PHONE",
    "EMAIL_ADDRESS": "EMAIL",
    "LOCATION": "LOCATION",
    "MEDICAL_LICENSE": "ID",
    "US_SSN": "ID",
    "IP_ADDRESS": "ID",
}

# Default NER-label → Presidio entity mapping used by spaCy / stanza / transformers engines
DEFAULT_MODEL_TO_PRESIDIO: dict[str, str] = {
    "PER": "PERSON",
    "PERSON": "PERSON",
    "NORP": "NRP",
    "FAC": "FACILITY",
    "LOC": "LOCATION",
    "GPE": "LOCATION",
    "LOCATION": "LOCATION",
    "ORG": "ORGANIZATION",
    "ORGANIZATION": "ORGANIZATION",
    "DATE": "DATE_TIME",
    "TIME": "DATE_TIME",
    # Clinical de-id models (e.g. obi/deid_roberta_i2b2, StanfordAIMI)
    "AGE": "AGE",
    "ID": "ID",
    "EMAIL": "EMAIL",
    "PATIENT": "PERSON",
    "STAFF": "PERSON",
    "HCW": "PERSON",
    "HOSP": "ORGANIZATION",
    "HOSPITAL": "ORGANIZATION",
    "PATORG": "ORGANIZATION",
    "FACILITY": "LOCATION",
    "PHONE": "PHONE_NUMBER",
}

SUPPORTED_MODEL_FAMILIES = ("spacy", "stanza", "huggingface", "flair")

KNOWN_MODELS = Literal[
    "spacy/en_core_web_sm",
    "spacy/en_core_web_md",
    "spacy/en_core_web_lg",
    "spacy/en_core_web_trf",
    "huggingface/obi/deid_roberta_i2b2",
    "huggingface/StanfordAIMI/stanford-deidentifier-base",
    "stanza/en",
    "flair/ner-english-large",
]

_MODEL_DESCRIPTIONS: dict[str, str] = {
    "spacy/en_core_web_sm": "spaCy small — fast, lower accuracy. Good for prototyping.",
    "spacy/en_core_web_md": "spaCy medium — balanced speed and accuracy.",
    "spacy/en_core_web_lg": "spaCy large — good general-purpose NER.",
    "spacy/en_core_web_trf": "spaCy transformer — highest accuracy, slower (requires GPU for speed).",
    "huggingface/obi/deid_roberta_i2b2": "RoBERTa fine-tuned on i2b2 clinical de-identification data.",
    "huggingface/StanfordAIMI/stanford-deidentifier-base": "Stanford AIMI clinical de-identifier (BERT-based).",
    "stanza/en": "Stanza English — Stanford NLP pipeline with BiLSTM NER.",
    "flair/ner-english-large": "Flair large NER — high accuracy, stacked embeddings.",
}

# ── Model-dependent label metadata ─────────────────────────────────────
# Raw NER labels each model family / specific model produces (before
# ``model_to_presidio`` mapping).  Used by ``base_labels`` so the label
# mapping widget shows only labels the selected model can detect.

_FAMILY_NER_LABELS: dict[str, list[str]] = {
    # spaCy / Stanza use OntoNotes entity types
    "spacy": [
        "PER", "PERSON", "NORP", "FAC", "LOC", "GPE", "LOCATION",
        "ORG", "ORGANIZATION", "DATE", "TIME",
    ],
    "stanza": [
        "PER", "PERSON", "NORP", "FAC", "LOC", "GPE", "LOCATION",
        "ORG", "ORGANIZATION", "DATE", "TIME",
    ],
    "flair": ["PER", "LOC", "ORG", "MISC"],
}

_SPECIFIC_MODEL_NER_LABELS: dict[str, list[str]] = {
    "obi/deid_roberta_i2b2": [
        "PATIENT", "STAFF", "AGE", "DATE", "PHONE", "ID", "EMAIL",
        "PATORG", "LOC", "HOSP", "OTHERPHI",
    ],
    "StanfordAIMI/stanford-deidentifier-base": [
        "AGE", "CONTACT", "DATE", "ID", "LOCATION", "NAME", "PROFESSION",
    ],
}

# When Presidio cannot be imported or the English NLP engine cannot be built, we
# still need a *superset* of entity_type strings that ``load_predefined_recognizers`` +
# ``analyze(..., entities=None)`` can emit from pattern/regex recognizers.  The
# short historical list (PHONE, EMAIL, …) hid US_BANK_NUMBER, CREDIT_CARD, etc.
# from the label-space UI even though they were detected at runtime.
_PRESIDIO_EN_ENTITY_TYPES_FALLBACK: frozenset[str] = frozenset(
    {
        "PHONE_NUMBER",
        "EMAIL_ADDRESS",
        "US_SSN",
        "IP_ADDRESS",
        "MEDICAL_LICENSE",
        "US_BANK_NUMBER",
        "US_DRIVER_LICENSE",
        "US_ITIN",
        "US_PASSPORT",
        "US_MBI",
        "US_NPI",
        "US_DEA",
        "CREDIT_CARD",
        "CRYPTO",
        "IBAN_CODE",
        "URL",
        "DATE_TIME",
        "NRP",
        "UK_NHS",
    }
)


@lru_cache(maxsize=1)
def _presidio_all_predefined_entity_types_en() -> frozenset[str]:
    """All ``entity_type`` values Presidio's default English registry can return.

    Mirrors ``RecognizerRegistry`` + ``load_predefined_recognizers`` the same way
    as :func:`_build_analyzer` (spaCy ``en`` engine + global recognizers).  This
    must cover pattern-based hits (e.g. ``US_BANK_NUMBER``) and any NER head labels
    the bundled spaCy/Transformers recognizer exposes so the Playground
    label-mapping list matches :meth:`PresidioNerPipe.forward` with ``entities=None``.

    If Presidio or ``en_core_web_sm`` is unavailable, returns
    :data:`_PRESIDIO_EN_ENTITY_TYPES_FALLBACK`.
    """
    try:
        from presidio_analyzer import RecognizerRegistry
        from presidio_analyzer.nlp_engine import NlpEngineProvider
    except ImportError:
        return _PRESIDIO_EN_ENTITY_TYPES_FALLBACK

    nlp_configuration: dict[str, Any] = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
    }
    try:
        nlp_engine = NlpEngineProvider(nlp_configuration=nlp_configuration).create_engine()
    except Exception:
        return _PRESIDIO_EN_ENTITY_TYPES_FALLBACK

    registry = RecognizerRegistry()
    try:
        registry.load_predefined_recognizers(nlp_engine=nlp_engine)
    except Exception:
        return _PRESIDIO_EN_ENTITY_TYPES_FALLBACK

    out: set[str] = set()
    try:
        for rec in registry.get_recognizers(language="en", all_fields=True):
            for e in rec.supported_entities:
                out.add(e)
    except Exception:
        return _PRESIDIO_EN_ENTITY_TYPES_FALLBACK
    if not out:
        return _PRESIDIO_EN_ENTITY_TYPES_FALLBACK
    return frozenset(out)


def _ner_labels_for_model(model: str) -> list[str]:
    """Return expected raw NER labels for *model* (before ``model_to_presidio``)."""
    family, model_path = _parse_model_spec(model)
    if family == "huggingface" and model_path in _SPECIFIC_MODEL_NER_LABELS:
        return _SPECIFIC_MODEL_NER_LABELS[model_path]
    return _FAMILY_NER_LABELS.get(family, [])


def _model_entity_map_keys(
    model: str,
    model_to_presidio: dict[str, str] | None = None,
) -> list[str]:
    """Presidio entity names produced for *model* (inputs to ``entity_map``), before PHI renaming."""
    m2p = model_to_presidio or DEFAULT_MODEL_TO_PRESIDIO
    keys: set[str] = set()
    for ner_label in _ner_labels_for_model(model):
        keys.add(m2p.get(ner_label, ner_label))
    keys.update(_presidio_all_predefined_entity_types_en())
    return sorted(keys)


def _model_base_labels(
    model: str,
    model_to_presidio: dict[str, str] | None,
    entity_map: dict[str, str],
) -> set[str]:
    """Compute the effective label space for *model*.

    Flows raw NER labels through ``model_to_presidio`` → ``entity_map``,
    then adds labels from all Presidio entity types the default English registry
    can emit (pattern recognizers + NER head; see
    :func:`_presidio_all_predefined_entity_types_en`), remapped through
    ``entity_map``.
    """
    m2p = model_to_presidio or DEFAULT_MODEL_TO_PRESIDIO
    labels: set[str] = set()
    for ner_label in _ner_labels_for_model(model):
        presidio_entity = m2p.get(ner_label, ner_label)
        labels.add(entity_map.get(presidio_entity, presidio_entity))
    for entity in _presidio_all_predefined_entity_types_en():
        labels.add(entity_map.get(entity, entity))
    return labels


def default_base_labels() -> list[str]:
    """Default label space for the presidio_ner detector."""
    return sorted(_model_base_labels("spacy/en_core_web_lg", None, dict(DEFAULT_ENTITY_MAP)))


def _parse_model_spec(model: str) -> tuple[str, str]:
    """Parse a ``'family/model_path'`` string into ``(family, model_path)``.

    Examples::

        "spacy/en_core_web_lg"                        → ("spacy", "en_core_web_lg")
        "HuggingFace/obi/deid_roberta_i2b2"           → ("huggingface", "obi/deid_roberta_i2b2")
        "stanza/en"                                    → ("stanza", "en")
        "en_core_web_lg"                               → ("spacy", "en_core_web_lg")
    """
    parts = model.split("/", 1)
    if len(parts) == 2 and parts[0].lower() in SUPPORTED_MODEL_FAMILIES:
        return parts[0].lower(), parts[1]
    # No recognised prefix → default to spacy
    return "spacy", model


def _build_analyzer(
    model_family: str,
    model_path: str,
    model_to_presidio: dict[str, str] | None = None,
) -> Any:
    """Build a ``presidio_analyzer.AnalyzerEngine`` for the given model backend."""
    from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    ner_mapping = model_to_presidio or DEFAULT_MODEL_TO_PRESIDIO

    if model_family == "spacy":
        nlp_configuration: dict[str, Any] = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": model_path}],
            "ner_model_configuration": {
                "model_to_presidio_entity_mapping": ner_mapping,
                "low_confidence_score_multiplier": 0.4,
                "low_score_entity_names": ["ORG", "ORGANIZATION"],
            },
        }
    elif model_family == "stanza":
        nlp_configuration = {
            "nlp_engine_name": "stanza",
            "models": [{"lang_code": "en", "model_name": model_path}],
            "ner_model_configuration": {
                "model_to_presidio_entity_mapping": ner_mapping,
            },
        }
    elif model_family == "huggingface":
        nlp_configuration = {
            "nlp_engine_name": "transformers",
            "models": [
                {
                    "lang_code": "en",
                    "model_name": {
                        "spacy": "en_core_web_sm",
                        "transformers": model_path,
                    },
                }
            ],
            "ner_model_configuration": {
                "model_to_presidio_entity_mapping": ner_mapping,
                "low_confidence_score_multiplier": 0.4,
                "low_score_entity_names": ["ID"],
                "labels_to_ignore": [
                    "CARDINAL",
                    "EVENT",
                    "LANGUAGE",
                    "LAW",
                    "MONEY",
                    "ORDINAL",
                    "PERCENT",
                    "PRODUCT",
                    "QUANTITY",
                    "WORK_OF_ART",
                ],
            },
        }
    elif model_family == "flair":
        import spacy as _spacy

        if not _spacy.util.is_package("en_core_web_sm"):
            _spacy.cli.download("en_core_web_sm")

        from flair_recognizer import FlairRecognizer  # type: ignore[import-untyped]

        nlp_configuration = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
        }
        nlp_engine = NlpEngineProvider(nlp_configuration=nlp_configuration).create_engine()
        registry = RecognizerRegistry()
        registry.load_predefined_recognizers(nlp_engine=nlp_engine)
        flair_recognizer = FlairRecognizer(model_path=model_path)
        registry.add_recognizer(flair_recognizer)
        registry.remove_recognizer("SpacyRecognizer")
        return AnalyzerEngine(nlp_engine=nlp_engine, registry=registry)
    else:
        raise ValueError(
            f"Unsupported model family {model_family!r}. "
            f"Supported: {', '.join(SUPPORTED_MODEL_FAMILIES)}"
        )

    nlp_engine = NlpEngineProvider(nlp_configuration=nlp_configuration).create_engine()
    registry = RecognizerRegistry()
    registry.load_predefined_recognizers(nlp_engine=nlp_engine)
    return AnalyzerEngine(nlp_engine=nlp_engine, registry=registry)


class PresidioNerConfig(BaseModel):
    """Configuration for the Presidio-based NER pipe."""

    model_config = ConfigDict(protected_namespaces=())

    model: KNOWN_MODELS = Field(
        default="spacy/en_core_web_lg",
        description="NLP model to use for NER.",
        json_schema_extra=field_ui(
            ui_group="Model",
            ui_order=1,
            ui_widget="described_select",
            ui_enum_descriptions=_MODEL_DESCRIPTIONS,
        ),
    )

    entities: list[str] | None = Field(
        default=None,
        description="Presidio entity types to detect. ``None`` means all supported entities.",
        json_schema_extra=field_ui(
            ui_group="Advanced",
            ui_order=1,
            ui_widget="multiselect",
            ui_advanced=True,
        ),
    )

    language: str = Field(
        default="en",
        json_schema_extra=field_ui(
            ui_group="Advanced",
            ui_order=2,
            ui_widget="text",
            ui_advanced=True,
        ),
    )

    model_to_presidio: dict[str, str] | None = Field(
        default=None,
        description="Override the NER label → Presidio entity mapping. ``None`` uses the default.",
        json_schema_extra=field_ui(
            ui_group="Advanced",
            ui_order=3,
            ui_widget="key_value",
            ui_advanced=True,
        ),
    )

    entity_map: dict[str, str] = Field(
        default_factory=lambda: dict(DEFAULT_ENTITY_MAP),
        description=(
            "Map Presidio entity names to project PHI labels. Unmapped entities pass through as-is."
        ),
        json_schema_extra=field_ui(
            ui_group="Advanced",
            ui_order=4,
            ui_widget="key_value",
            ui_advanced=True,
        ),
    )

    source_name: str = Field(
        default="presidio_ner",
        json_schema_extra=field_ui(
            ui_group="Advanced",
            ui_order=5,
            ui_widget="text",
            ui_advanced=True,
        ),
    )

    label_mapping: dict[str, str | None] = detector_label_mapping_field()

    skip_overlapping: bool = Field(
        default=False,
        description="Drop new spans that overlap any existing span in the document.",
        json_schema_extra=field_ui(
            ui_group="General",
            ui_order=99,
            ui_widget="switch",
        ),
    )


class PresidioNerPipe(ConfigurablePipe):
    def __init__(self, config: PresidioNerConfig | None = None) -> None:
        try:
            import presidio_analyzer  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "presidio-analyzer is required for PresidioNerPipe. "
                "Install it with:  pip install 'pypedeid[presidio]'"
            ) from exc

        self._config = config or PresidioNerConfig()
        model_family, model_path = _parse_model_spec(self._config.model)
        self._analyzer = _build_analyzer(
            model_family, model_path, self._config.model_to_presidio
        )

    @property
    def base_labels(self) -> set[str]:
        return _model_base_labels(
            self._config.model,
            self._config.model_to_presidio,
            self._config.entity_map,
        )

    @property
    def label_mapping(self) -> dict[str, str | None]:
        return dict(self._config.label_mapping)

    @property
    def labels(self) -> set[str]:
        return effective_detector_labels(self.base_labels, self._config.label_mapping)

    def forward(self, doc: AnnotatedDocument) -> AnnotatedDocument:
        text = doc.document.text
        results = self._analyzer.analyze(
            text=text,
            entities=self._config.entities,
            language=self._config.language,
        )

        found: list[EntitySpan] = []
        for r in results:
            label = self._config.entity_map.get(r.entity_type, r.entity_type)
            found.append(
                EntitySpan(
                    start=r.start,
                    end=r.end,
                    label=label,
                    confidence=r.score,
                    source=self._config.source_name,
                )
            )

        found.sort(key=lambda s: (s.start, s.end, s.label))
        found = apply_detector_label_mapping(found, self._config.label_mapping)
        return accumulate_spans(doc, found, skip_overlapping=self._config.skip_overlapping)


def build_presidio_label_space_bundle() -> dict[str, Any]:
    """Payload for ``GET …/presidio_ner/label-space-bundle`` (same JSON shape as NeuroNER bundle).

    ``labels_by_model`` holds **Presidio entity names** (``entity_map`` keys) per selectable
    model, using default ``model_to_presidio`` and the same predefined-recognizer
    superset as :func:`_presidio_all_predefined_entity_types_en` (so pattern hits like
    ``US_BANK_NUMBER`` are listed, not only a short legacy subset). The client merges
    ``default_entity_map`` with ``config.entity_map``, then maps each key to canonical
    PHI labels.
    """
    labels_by_model: dict[str, list[str]] = {}
    for model in get_args(KNOWN_MODELS):
        labels_by_model[model] = _model_entity_map_keys(model, None)
    cfg = PresidioNerConfig()
    return {
        "labels_by_model": labels_by_model,
        "default_entity_map": dict(DEFAULT_ENTITY_MAP),
        "default_model": cfg.model,
    }
