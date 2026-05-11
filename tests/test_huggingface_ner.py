"""Tests for the huggingface_ner detector pipe."""

from __future__ import annotations

import json

import pytest

from clinical_deid.domain import AnnotatedDocument, Document
from clinical_deid.pipes.huggingface_ner.pipe import (
    HuggingfaceNerConfig,
    HuggingfaceNerPipe,
    build_huggingface_label_space_bundle,
    huggingface_ner_dependencies,
    list_huggingface_model_names,
)


@pytest.fixture
def hf_models_dir(tmp_path, monkeypatch):
    """Register two HF model manifests so registry-backed lookups work."""
    models_dir = tmp_path / "models"
    a = models_dir / "huggingface" / "phi-a"
    b = models_dir / "huggingface" / "phi-b"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    (a / "model_manifest.json").write_text(json.dumps({
        "name": "phi-a",
        "framework": "huggingface",
        "labels": ["NAME", "DATE"],
        "training": {"segmentation": "sentence"},
    }))
    (b / "model_manifest.json").write_text(json.dumps({
        "name": "phi-b",
        "framework": "huggingface",
        "labels": ["NAME", "DATE", "PHONE"],
    }))
    monkeypatch.setenv("CLINICAL_DEID_MODELS_DIR", str(models_dir))
    from clinical_deid.config import reset_settings
    reset_settings()
    return models_dir


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_config_defaults():
    cfg = HuggingfaceNerConfig(model="phi-a")
    assert cfg.model == "phi-a"
    assert cfg.segmentation == "auto"
    assert cfg.entity_map == {}
    assert cfg.label_mapping == {}
    dumped = cfg.model_dump()
    # No ``device`` field — picked at runtime.
    assert "device" not in dumped
    # No ``confidence_threshold`` — argmax over the model's classes is the only filter.
    assert "confidence_threshold" not in dumped


def test_config_rejects_unknown_segmentation():
    with pytest.raises(ValueError):
        HuggingfaceNerConfig(model="phi-a", segmentation="paragraph")


# ---------------------------------------------------------------------------
# Catalog wiring
# ---------------------------------------------------------------------------


def test_huggingface_ner_in_catalog():
    from clinical_deid.pipes.registry import pipe_catalog

    entry = next((e for e in pipe_catalog() if e.name == "huggingface_ner"), None)
    assert entry is not None
    assert entry.label_source == "bundle"
    assert entry.bundle_key_semantics == "ner_raw"
    assert "huggingface_models" in entry.dynamic_options_fns


def test_huggingface_ner_registered():
    from clinical_deid.pipes.registry import registered_pipes

    assert "huggingface_ner" in registered_pipes()


def test_old_custom_ner_removed():
    """The legacy ``custom_ner`` entry should be gone — no two HF entry points."""
    from clinical_deid.pipes.registry import pipe_catalog, registered_pipes

    names = {e.name for e in pipe_catalog()}
    assert "custom_ner" not in names
    assert "custom_ner" not in registered_pipes()


# ---------------------------------------------------------------------------
# Dynamic options + label-space bundle
# ---------------------------------------------------------------------------


def test_list_huggingface_model_names(hf_models_dir):
    names = list_huggingface_model_names()
    assert names == ["phi-a", "phi-b"]


def test_label_space_bundle(hf_models_dir):
    bundle = build_huggingface_label_space_bundle()
    assert bundle["labels_by_model"] == {
        "phi-a": ["DATE", "NAME"],
        "phi-b": ["DATE", "NAME", "PHONE"],
    }
    assert bundle["default_entity_map"] == {}
    assert bundle["default_model"] == "phi-a"
    # model_info entries exist for every model (values may be None when
    # training_config / config.json aren't recorded in the test fixtures).
    assert set(bundle["model_info"].keys()) == {"phi-a", "phi-b"}
    assert bundle["model_info"]["phi-a"]["segmentation"] == "sentence"


def test_label_space_bundle_empty_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("CLINICAL_DEID_MODELS_DIR", str(tmp_path / "models"))
    from clinical_deid.config import reset_settings
    reset_settings()

    bundle = build_huggingface_label_space_bundle()
    assert bundle == {
        "labels_by_model": {},
        "entity_maps_by_model": {},
        "default_entity_map": {},
        "default_model": "",
        "model_info": {},
    }


def test_label_space_bundle_model_info_reads_training_max_length(tmp_path, monkeypatch):
    """When the manifest stores training_config.hyperparams.max_length and the
    model dir has a config.json with max_position_embeddings, both surface
    in the bundle so the UI can show training and architectural limits."""
    models_dir = tmp_path / "models"
    model_dir = models_dir / "huggingface" / "phi-trained"
    model_dir.mkdir(parents=True)
    (model_dir / "model_manifest.json").write_text(json.dumps({
        "name": "phi-trained",
        "framework": "huggingface",
        "labels": ["NAME"],
        "base_model": "emilyalsentzer/Bio_ClinicalBERT",
        "training_config": {"hyperparams": {"max_length": 256}},
        "training": {"segmentation": "chunk", "train_documents": 42},
    }))
    (model_dir / "config.json").write_text(json.dumps({"max_position_embeddings": 512}))

    monkeypatch.setenv("CLINICAL_DEID_MODELS_DIR", str(models_dir))
    from clinical_deid.config import reset_settings
    reset_settings()

    bundle = build_huggingface_label_space_bundle()
    info = bundle["model_info"]["phi-trained"]
    assert info["trained_max_length"] == 256
    assert info["max_position_embeddings"] == 512
    assert info["segmentation"] == "chunk"
    assert info["base_model"] == "emilyalsentzer/Bio_ClinicalBERT"
    assert info["train_documents"] == 42


def test_resolve_dynamic_options_routes_to_huggingface_models(hf_models_dir):
    from clinical_deid.pipes.registry import resolve_dynamic_options

    assert resolve_dynamic_options("huggingface_models") == ["phi-a", "phi-b"]


# ---------------------------------------------------------------------------
# Label resolution from manifest (no model load)
# ---------------------------------------------------------------------------


def test_base_labels_from_manifest(hf_models_dir):
    pipe = HuggingfaceNerPipe(HuggingfaceNerConfig(model="phi-a"))
    assert pipe.base_labels == {"NAME", "DATE"}


def test_entity_map_renames_labels(hf_models_dir):
    pipe = HuggingfaceNerPipe(HuggingfaceNerConfig(
        model="phi-a", entity_map={"NAME": "PATIENT"},
    ))
    assert pipe.base_labels == {"PATIENT", "DATE"}


def test_label_mapping_drops_and_renames(hf_models_dir):
    pipe = HuggingfaceNerPipe(HuggingfaceNerConfig(
        model="phi-b",
        label_mapping={"PHONE": None, "DATE": "OCCURRENCE"},
    ))
    labels = pipe.labels
    assert "PHONE" not in labels
    assert "OCCURRENCE" in labels
    assert "NAME" in labels


def test_base_labels_missing_model_returns_empty():
    pipe = HuggingfaceNerPipe(HuggingfaceNerConfig(model="does-not-exist"))
    assert pipe.base_labels == set()


# ---------------------------------------------------------------------------
# Framework guard: huggingface_ner refuses non-HF models
# ---------------------------------------------------------------------------


def test_framework_mismatch_raises(tmp_path, monkeypatch):
    models_dir = tmp_path / "models"
    spacy_dir = models_dir / "spacy" / "spacy-only"
    spacy_dir.mkdir(parents=True)
    (spacy_dir / "model_manifest.json").write_text(json.dumps({
        "name": "spacy-only",
        "framework": "spacy",
        "labels": ["PERSON"],
    }))
    monkeypatch.setenv("CLINICAL_DEID_MODELS_DIR", str(models_dir))
    from clinical_deid.config import reset_settings
    reset_settings()

    pipe = HuggingfaceNerPipe(HuggingfaceNerConfig(model="spacy-only"))
    doc = AnnotatedDocument(document=Document(id="t", text="Hi"), spans=[])
    with pytest.raises(ValueError, match="huggingface_ner requires"):
        pipe.forward(doc)


# ---------------------------------------------------------------------------
# Dependency check (deploy health)
# ---------------------------------------------------------------------------


def test_dependencies_flag_missing_model(hf_models_dir):
    assert huggingface_ner_dependencies({"model": "phi-a"}) == []
    assert huggingface_ner_dependencies({"model": "missing"}) == ["model:missing"]
    assert huggingface_ner_dependencies({}) == []


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------


def test_load_pipe_huggingface_ner():
    from clinical_deid.pipes.registry import load_pipe

    pipe = load_pipe({
        "type": "huggingface_ner",
        "config": {"model": "phi-a"},
    })
    assert isinstance(pipe, HuggingfaceNerPipe)


def test_dump_pipe_huggingface_ner(hf_models_dir):
    from clinical_deid.pipes.registry import dump_pipe

    pipe = HuggingfaceNerPipe(HuggingfaceNerConfig(model="phi-a"))
    dumped = dump_pipe(pipe)
    assert dumped["type"] == "huggingface_ner"
    assert dumped["config"]["model"] == "phi-a"
    # Defaults are trimmed — no device field, no segmentation:auto.
    assert "device" not in dumped["config"]
    assert "segmentation" not in dumped["config"]


# ---------------------------------------------------------------------------
# Adjacent-span reconciliation
# ---------------------------------------------------------------------------


class _FakeHFPipeline:
    """Stand-in for transformers.pipeline returning a fixed list of entities."""

    def __init__(self, entities: list[dict]):
        self._entities = entities

    def __call__(self, text: str):
        return list(self._entities)


def test_forward_merges_adjacent_same_label_spans(hf_models_dir):
    """HF token classification often splits "John Smith" / "555-123-4567" into
    consecutive entities — they should collapse into a single span."""
    pipe = HuggingfaceNerPipe(HuggingfaceNerConfig(model="phi-a"))
    pipe._segmentation = "truncate"
    pipe._pipeline = _FakeHFPipeline([
        {"start": 0, "end": 4, "entity_group": "NAME", "score": 0.99},
        {"start": 5, "end": 10, "entity_group": "NAME", "score": 0.95},
        {"start": 18, "end": 21, "entity_group": "PHONE", "score": 0.92},
        {"start": 22, "end": 25, "entity_group": "PHONE", "score": 0.91},
        {"start": 26, "end": 30, "entity_group": "PHONE", "score": 0.93},
    ])

    doc = AnnotatedDocument(
        document=Document(id="t", text="John Smith called 555-123-4567"),
        spans=[],
    )
    result = pipe.forward(doc)

    assert len(result.spans) == 2
    name = next(s for s in result.spans if s.label == "NAME")
    phone = next(s for s in result.spans if s.label == "PHONE")
    assert (name.start, name.end) == (0, 10)
    assert (phone.start, phone.end) == (18, 30)


def test_forward_does_not_merge_different_labels(hf_models_dir):
    """Adjacent spans with different labels stay separate even if abutting."""
    pipe = HuggingfaceNerPipe(HuggingfaceNerConfig(model="phi-b"))
    pipe._segmentation = "truncate"
    pipe._pipeline = _FakeHFPipeline([
        {"start": 0, "end": 4, "entity_group": "NAME", "score": 0.99},
        {"start": 5, "end": 15, "entity_group": "DATE", "score": 0.95},
    ])

    doc = AnnotatedDocument(
        document=Document(id="t", text="John 2024-01-15"),
        spans=[],
    )
    result = pipe.forward(doc)

    assert len(result.spans) == 2
    assert {s.label for s in result.spans} == {"NAME", "DATE"}
