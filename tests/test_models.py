"""Tests for model directory scanner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pypedeid.models import get_model, list_models, scan_models


def _write_manifest(model_dir: Path, manifest: dict) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "model_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def test_scan_models_empty(tmp_path: Path) -> None:
    assert scan_models(tmp_path) == {}


def test_scan_models_nonexistent(tmp_path: Path) -> None:
    assert scan_models(tmp_path / "nope") == {}


def test_scan_single_model(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path / "spacy" / "my-ner",
        {
            "name": "my-ner",
            "framework": "spacy",
            "labels": ["PATIENT", "DATE"],
            "description": "Test model",
            "device": "cpu",
        },
    )
    models = scan_models(tmp_path)
    assert len(models) == 1
    info = models["my-ner"]
    assert info.name == "my-ner"
    assert info.framework == "spacy"
    assert info.labels == ["PATIENT", "DATE"]
    assert info.description == "Test model"
    assert info.path == tmp_path / "spacy" / "my-ner"


def test_scan_multiple_frameworks(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path / "spacy" / "sp-model",
        {"name": "sp-model", "framework": "spacy", "labels": ["NAME"]},
    )
    _write_manifest(
        tmp_path / "huggingface" / "hf-model",
        {"name": "hf-model", "framework": "huggingface", "labels": ["DATE"]},
    )
    _write_manifest(
        tmp_path / "external" / "ext-model",
        {"name": "ext-model", "framework": "external", "labels": ["PHONE"]},
    )
    models = scan_models(tmp_path)
    assert len(models) == 3
    assert set(models.keys()) == {"sp-model", "hf-model", "ext-model"}


def test_scan_skips_dirs_without_manifest(tmp_path: Path) -> None:
    (tmp_path / "spacy" / "no-manifest").mkdir(parents=True)
    assert scan_models(tmp_path) == {}


def test_scan_skips_hidden_dirs(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path / "spacy" / ".hidden",
        {"name": ".hidden", "framework": "spacy", "labels": ["X"]},
    )
    assert scan_models(tmp_path) == {}


def test_manifest_missing_name(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path / "spacy" / "bad",
        {"framework": "spacy", "labels": ["X"]},
    )
    with pytest.raises(ValueError, match="missing 'name'"):
        scan_models(tmp_path)


def test_manifest_missing_framework(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path / "spacy" / "bad",
        {"name": "bad", "labels": ["X"]},
    )
    with pytest.raises(ValueError, match="missing 'framework'"):
        scan_models(tmp_path)


def test_manifest_missing_labels(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path / "spacy" / "bad",
        {"name": "bad", "framework": "spacy"},
    )
    with pytest.raises(ValueError, match="missing or invalid 'labels'"):
        scan_models(tmp_path)


def test_manifest_name_mismatch(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path / "spacy" / "dir-name",
        {"name": "different-name", "framework": "spacy", "labels": ["X"]},
    )
    with pytest.raises(ValueError, match="does not match directory name"):
        scan_models(tmp_path)


def test_manifest_unknown_framework(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path / "pytorch" / "my-model",
        {"name": "my-model", "framework": "pytorch", "labels": ["X"]},
    )
    with pytest.raises(ValueError, match="Unknown framework"):
        scan_models(tmp_path)


def test_duplicate_model_name(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path / "spacy" / "dup",
        {"name": "dup", "framework": "spacy", "labels": ["X"]},
    )
    _write_manifest(
        tmp_path / "huggingface" / "dup",
        {"name": "dup", "framework": "huggingface", "labels": ["Y"]},
    )
    with pytest.raises(ValueError, match="Duplicate model name"):
        scan_models(tmp_path)


def test_get_model_found(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path / "spacy" / "find-me",
        {"name": "find-me", "framework": "spacy", "labels": ["A"]},
    )
    info = get_model(tmp_path, "find-me")
    assert info.name == "find-me"


def test_get_model_not_found(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="not found"):
        get_model(tmp_path, "nope")


def test_list_models_all(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path / "spacy" / "a",
        {"name": "a", "framework": "spacy", "labels": ["X"]},
    )
    _write_manifest(
        tmp_path / "huggingface" / "b",
        {"name": "b", "framework": "huggingface", "labels": ["Y"]},
    )
    result = list_models(tmp_path)
    assert len(result) == 2
    assert result[0].name == "b"  # huggingface sorts before spacy
    assert result[1].name == "a"


def test_list_models_filter_framework(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path / "spacy" / "a",
        {"name": "a", "framework": "spacy", "labels": ["X"]},
    )
    _write_manifest(
        tmp_path / "huggingface" / "b",
        {"name": "b", "framework": "huggingface", "labels": ["Y"]},
    )
    result = list_models(tmp_path, framework="spacy")
    assert len(result) == 1
    assert result[0].name == "a"


def test_manifest_optional_fields(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path / "huggingface" / "full",
        {
            "name": "full",
            "framework": "huggingface",
            "labels": ["PATIENT", "DATE"],
            "description": "Full model",
            "base_model": "roberta-base",
            "dataset": "i2b2-2014",
            "metrics": {"f1": 0.92, "precision": 0.94, "recall": 0.90},
            "device": "mps",
            "created_at": "2026-03-28T12:00:00Z",
        },
    )
    info = get_model(tmp_path, "full")
    assert info.base_model == "roberta-base"
    assert info.dataset == "i2b2-2014"
    assert info.metrics["f1"] == 0.92
    assert info.device == "mps"
    assert info.created_at == "2026-03-28T12:00:00Z"
