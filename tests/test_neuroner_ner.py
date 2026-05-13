"""Tests for the neuroner_ner detector pipe.

Uses mocked HTTP helpers — no Docker sidecar or TensorFlow required.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from pypedeid.domain import AnnotatedDocument, Document, EntitySpan
from pypedeid.pipes.neuroner_ner.pipe import (
    DEFAULT_ENTITY_MAP,
    NeuroNerConfig,
    NeuroNerPipe,
)


def _make_doc(text: str, doc_id: str = "test") -> AnnotatedDocument:
    return AnnotatedDocument(document=Document(id=doc_id, text=text), spans=[])


# ── Config tests ───────────────────────────────────────────────────────────


def test_config_defaults() -> None:
    cfg = NeuroNerConfig()
    assert cfg.base_url == ""
    assert cfg.model == "i2b2_2014_glove_spacy_bioes"
    assert cfg.source_name == "neuroner_ner"
    assert cfg.entity_map == DEFAULT_ENTITY_MAP


def test_config_custom_model() -> None:
    cfg = NeuroNerConfig(model="mimic_glove_spacy_bioes")
    assert cfg.model == "mimic_glove_spacy_bioes"


def test_registry_roundtrip() -> None:
    """Pipe can be loaded from JSON config via the registry."""
    from pypedeid.pipes.registry import load_pipe

    spec = {
        "type": "neuroner_ner",
        "config": {"model": "i2b2_2014_glove_spacy_bioes"},
    }
    pipe = load_pipe(spec)
    assert isinstance(pipe, NeuroNerPipe)
    assert pipe._config.model == "i2b2_2014_glove_spacy_bioes"


def test_serialization_roundtrip() -> None:
    """Pipe can be serialized back to JSON via the registry."""
    from pypedeid.pipes.registry import dump_pipe, load_pipe

    spec = {
        "type": "neuroner_ner",
        "config": {"model": "mimic_glove_spacy_bioes"},
    }
    pipe = load_pipe(spec)
    dumped = dump_pipe(pipe)
    assert dumped["type"] == "neuroner_ner"
    assert dumped["config"]["model"] == "mimic_glove_spacy_bioes"


# ── Entity map coverage ───────────────────────────────────────────────────


I2B2_LABELS = {
    "AGE", "BIOID", "CITY", "COUNTRY", "DATE", "DEVICE", "DOCTOR", "EMAIL",
    "FAX", "HEALTHPLAN", "HOSPITAL", "IDNUM", "LOCATION_OTHER",
    "MEDICALRECORD", "ORGANIZATION", "PATIENT", "PHONE", "PROFESSION",
    "STATE", "STREET", "URL", "USERNAME", "ZIP",
}


def test_default_entity_map_covers_i2b2_labels() -> None:
    """Every i2b2 2014 label has a mapping in DEFAULT_ENTITY_MAP."""
    assert I2B2_LABELS == set(DEFAULT_ENTITY_MAP.keys())


def test_default_entity_map_values_are_nonempty() -> None:
    for k, v in DEFAULT_ENTITY_MAP.items():
        assert isinstance(v, str) and len(v) > 0, f"Bad mapping for {k}: {v!r}"


# ── Forward with mocked HTTP ───────────────────────────────────────────────


@pytest.fixture()
def pipe_with_mock():
    """Create a NeuroNerPipe with mocked HTTP readiness and prediction."""
    pipe = NeuroNerPipe(NeuroNerConfig())
    pipe._model_labels = list(I2B2_LABELS)
    pipe._labels_model_key = pipe._labels_cache_key()
    return pipe


def test_forward_maps_entities(pipe_with_mock: NeuroNerPipe) -> None:
    pipe = pipe_with_mock
    fake_response = {
        "entities": [
            {"id": "T1", "type": "DOCTOR", "start": 8, "end": 18, "text": "John Smith", "confidence": 0.91},
            {"id": "T2", "type": "DATE", "start": 32, "end": 42, "text": "01/15/2023", "confidence": 0.88},
        ]
    }
    with patch.object(pipe, "_ensure_http_ready", return_value=None), \
         patch.object(pipe, "_http_predict", return_value=fake_response):
        doc = _make_doc("Patient John Smith admitted on 01/15/2023 for surgery.")
        result = pipe.forward(doc)

    assert len(result.spans) == 2
    labels = {s.label for s in result.spans}
    assert "NAME" in labels  # DOCTOR mapped to NAME
    assert "DATE" in labels
    assert all(s.source == "neuroner_ner" for s in result.spans)
    assert result.spans[0].confidence == pytest.approx(0.91)
    assert result.spans[1].confidence == pytest.approx(0.88)


def test_forward_empty_text(pipe_with_mock: NeuroNerPipe) -> None:
    pipe = pipe_with_mock
    doc = _make_doc("")
    result = pipe.forward(doc)
    assert result.spans == []


def test_forward_whitespace_only(pipe_with_mock: NeuroNerPipe) -> None:
    pipe = pipe_with_mock
    doc = _make_doc("   \n  ")
    result = pipe.forward(doc)
    assert result.spans == []


def test_forward_skips_invalid_offsets(pipe_with_mock: NeuroNerPipe) -> None:
    """Entities with out-of-range offsets are silently dropped."""
    pipe = pipe_with_mock
    fake_response = {
        "entities": [
            {"id": "T1", "type": "DOCTOR", "start": 0, "end": 5, "text": "Hello"},
            {"id": "T2", "type": "DATE", "start": 0, "end": 999, "text": "bad"},
        ]
    }
    with patch.object(pipe, "_ensure_http_ready", return_value=None), \
         patch.object(pipe, "_http_predict", return_value=fake_response):
        doc = _make_doc("Hello world")
        result = pipe.forward(doc)

    assert len(result.spans) == 1
    assert result.spans[0].label == "NAME"


def test_forward_unmapped_label_passes_through(pipe_with_mock: NeuroNerPipe) -> None:
    """Entity labels not in entity_map pass through unchanged."""
    pipe = pipe_with_mock
    fake_response = {
        "entities": [
            {"id": "T1", "type": "UNKNOWN_LABEL", "start": 0, "end": 5, "text": "Hello"},
        ]
    }
    with patch.object(pipe, "_ensure_http_ready", return_value=None), \
         patch.object(pipe, "_http_predict", return_value=fake_response):
        doc = _make_doc("Hello world")
        result = pipe.forward(doc)

    assert len(result.spans) == 1
    assert result.spans[0].label == "UNKNOWN_LABEL"


def test_forward_with_label_mapping() -> None:
    """label_mapping (post-entity_map) drops or remaps labels."""
    config = NeuroNerConfig(label_mapping={"NAME": None, "DATE": "TEMPORAL"})
    pipe = NeuroNerPipe(config)
    pipe._model_labels = list(I2B2_LABELS)
    pipe._labels_model_key = pipe._labels_cache_key()

    fake_response = {
        "entities": [
            {"id": "T1", "type": "DOCTOR", "start": 8, "end": 18, "text": "John Smith"},
            {"id": "T2", "type": "DATE", "start": 32, "end": 42, "text": "01/15/2023"},
        ]
    }
    with patch.object(pipe, "_ensure_http_ready", return_value=None), \
         patch.object(pipe, "_http_predict", return_value=fake_response):
        doc = _make_doc("Patient John Smith admitted on 01/15/2023 for surgery.")
        result = pipe.forward(doc)

    # NAME was dropped (mapped to None), DATE was remapped to TEMPORAL
    assert len(result.spans) == 1
    assert result.spans[0].label == "TEMPORAL"


def test_forward_accumulates_with_existing_spans() -> None:
    """New spans are accumulated with pre-existing document spans."""
    pipe = NeuroNerPipe(NeuroNerConfig())
    pipe._model_labels = list(I2B2_LABELS)
    pipe._labels_model_key = pipe._labels_cache_key()

    existing = EntitySpan(start=0, end=7, label="NAME", source="other_detector")
    doc = AnnotatedDocument(
        document=Document(id="test", text="Patient John Smith was seen on 01/15/2023."),
        spans=[existing],
    )
    fake_response = {
        "entities": [
            {"id": "T1", "type": "DATE", "start": 31, "end": 41, "text": "01/15/2023"},
        ]
    }
    with patch.object(pipe, "_ensure_http_ready", return_value=None), \
         patch.object(pipe, "_http_predict", return_value=fake_response):
        result = pipe.forward(doc)

    assert len(result.spans) == 2
    sources = {s.source for s in result.spans}
    assert "other_detector" in sources
    assert "neuroner_ner" in sources


# ── Label introspection ────────────────────────────────────────────────────


def test_model_labels_returns_cached() -> None:
    pipe = NeuroNerPipe(NeuroNerConfig())
    pipe._model_labels = ["AGE", "DATE", "DOCTOR"]
    pipe._labels_model_key = pipe._labels_cache_key()
    assert pipe.model_labels() == ["AGE", "DATE", "DOCTOR"]


def test_base_labels_after_entity_map_default_model() -> None:
    """base_labels are post-entity_map names (inputs to label_mapping), not raw NER tags."""
    pipe = NeuroNerPipe(NeuroNerConfig())
    bl = pipe.base_labels
    assert "DOCTOR" not in bl
    assert "NAME" in bl
    assert "DATE" in bl


def test_neuroner_raw_labels_match_get_model_registry() -> None:
    """``_raw_entity_labels`` uses the same ``model_manifest.json`` as :func:`~pypedeid.models.get_model`."""
    from pathlib import Path

    import json

    from pypedeid.config import get_settings
    from pypedeid.models import get_model

    root = Path("models/neuroner")
    if not root.is_dir():
        pytest.skip("no models/neuroner in repo")

    for name in ("conll_2003_en", "i2b2_2014_glove_spacy_bioes"):
        manifest = root / name / "model_manifest.json"
        if not manifest.is_file():
            pytest.skip(f"missing {manifest}")
        expected = json.loads(manifest.read_text(encoding="utf-8"))["labels"]
        info = get_model(get_settings().models_dir, name)
        assert info.labels == expected
        pipe = NeuroNerPipe(NeuroNerConfig(model=name))
        assert sorted(pipe._raw_entity_labels()) == sorted(expected)


def test_compute_base_labels_differs_between_neuroner_models() -> None:
    """POST /pipelines/pipe-types/neuroner_ner/labels must vary with ``model`` when manifests differ."""
    from pathlib import Path

    from pypedeid.pipes.registry import compute_base_labels

    root = Path("models/neuroner")
    if not (root / "conll_2003_en" / "model_manifest.json").is_file():
        pytest.skip("no conll_2003_en model")
    if not (root / "i2b2_2014_glove_spacy_bioes" / "model_manifest.json").is_file():
        pytest.skip("no i2b2 model")

    a = compute_base_labels("neuroner_ner", {"model": "conll_2003_en", "entity_map": {}})
    b = compute_base_labels("neuroner_ner", {"model": "i2b2_2014_glove_spacy_bioes", "entity_map": {}})
    assert a != b


def test_compute_base_labels_follows_model_manifest(tmp_path) -> None:
    """``compute_base_labels`` reflects the selected model directory's manifest."""
    from pypedeid.pipes.registry import compute_base_labels

    models = tmp_path / "neuroner"
    models.mkdir()
    alpha = models / "alpha"
    beta = models / "beta"
    alpha.mkdir()
    beta.mkdir()
    (alpha / "model_manifest.json").write_text(
        '{"labels": ["DOCTOR", "DATE"], "framework": "neuroner"}\n',
        encoding="utf-8",
    )
    (beta / "model_manifest.json").write_text(
        '{"labels": ["CUSTOM_A", "CUSTOM_B"], "framework": "neuroner"}\n',
        encoding="utf-8",
    )

    cfg_a = {"model": "alpha", "models_dir": str(models), "entity_map": {}}
    cfg_b = {"model": "beta", "models_dir": str(models), "entity_map": {}}

    assert compute_base_labels("neuroner_ner", cfg_a) == ["DATE", "DOCTOR"]
    assert compute_base_labels("neuroner_ner", cfg_b) == ["CUSTOM_A", "CUSTOM_B"]


def test_effective_labels_with_mapping() -> None:
    config = NeuroNerConfig(label_mapping={"NAME": "PERSON", "DATE": None})
    pipe = NeuroNerPipe(config)
    eff = pipe.labels
    assert "PERSON" in eff
    assert "DATE" not in eff  # dropped by label_mapping
