"""Tests for base-model resolution."""

import json
from pathlib import Path

import pytest

from pypedeid.training.base_model import ResolvedBaseModel, resolve_base_model
from pypedeid.training.errors import BaseModelNotFound, IncompatibleFramework


def _write_manifest(model_dir: Path, name: str, framework: str, labels: list[str]) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"name": name, "framework": framework, "labels": labels}
    (model_dir / "model_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_hub_id_passthrough(tmp_path):
    resolved = resolve_base_model("emilyalsentzer/Bio_ClinicalBERT", tmp_path)
    assert resolved.kind == "hub"
    assert resolved.source == "emilyalsentzer/Bio_ClinicalBERT"
    assert resolved.parent_model_name is None
    assert resolved.saved_label_space == []
    assert resolved.tokenizer_source == resolved.source


def test_local_resolution(tmp_path):
    model_dir = tmp_path / "huggingface" / "clinical-bert-v1"
    _write_manifest(model_dir, "clinical-bert-v1", "huggingface", ["NAME", "DATE"])

    resolved = resolve_base_model("local:clinical-bert-v1", tmp_path)
    assert resolved.kind == "local"
    assert resolved.source == str(model_dir)
    assert resolved.parent_model_name == "clinical-bert-v1"
    assert resolved.saved_label_space == ["NAME", "DATE"]
    assert resolved.tokenizer_source == str(model_dir)


def test_local_not_found(tmp_path):
    with pytest.raises(BaseModelNotFound):
        resolve_base_model("local:does-not-exist", tmp_path)


def test_local_wrong_framework(tmp_path):
    model_dir = tmp_path / "spacy" / "my-spacy-model"
    _write_manifest(model_dir, "my-spacy-model", "spacy", ["PER"])

    with pytest.raises(IncompatibleFramework):
        resolve_base_model("local:my-spacy-model", tmp_path)


def test_resolved_base_model_is_frozen():
    r = ResolvedBaseModel(
        kind="hub",
        source="bert-base-uncased",
        parent_model_name=None,
        saved_label_space=[],
        tokenizer_source="bert-base-uncased",
    )
    with pytest.raises((AttributeError, TypeError)):
        r.source = "other"  # type: ignore[misc]
