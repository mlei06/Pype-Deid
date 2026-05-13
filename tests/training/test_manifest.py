"""Tests for manifest v1/v2 round-trips and ModelInfo loading."""

import json
from pathlib import Path

import pytest

from pypedeid.models import _load_manifest
from pypedeid.training.manifest import write_manifest_v2


# ---------------------------------------------------------------------------
# v1 manifest — must load unchanged
# ---------------------------------------------------------------------------


def _write_v1(model_dir: Path, name: str) -> Path:
    model_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": name,
        "framework": "huggingface",
        "labels": ["NAME", "DATE"],
    }
    p = model_dir / "model_manifest.json"
    p.write_text(json.dumps(manifest), encoding="utf-8")
    return p


def test_v1_loads_without_error(tmp_path):
    model_dir = tmp_path / "huggingface" / "old-model"
    p = _write_v1(model_dir, "old-model")
    info = _load_manifest(p)
    assert info.name == "old-model"
    assert info.labels == ["NAME", "DATE"]
    assert info.schema_version is None
    assert info.parent_model is None
    assert info.training_meta == {}


def test_v1_missing_optional_fields_default_correctly(tmp_path):
    model_dir = tmp_path / "huggingface" / "bare"
    p = _write_v1(model_dir, "bare")
    info = _load_manifest(p)
    assert info.has_crf is False
    assert info.training_config is None
    assert info.tokenizer is None


# ---------------------------------------------------------------------------
# v2 manifest — write and round-trip
# ---------------------------------------------------------------------------


def test_v2_write_and_reload(tmp_path):
    model_dir = tmp_path / "huggingface" / "new-model"
    model_dir.mkdir(parents=True, exist_ok=True)

    write_manifest_v2(
        model_dir,
        name="new-model",
        base_model="emilyalsentzer/Bio_ClinicalBERT",
        parent_model_name=None,
        tokenizer_source="emilyalsentzer/Bio_ClinicalBERT",
        labels=["NAME", "DATE"],
        bio_labels=["O", "B-NAME", "I-NAME", "B-DATE", "I-DATE"],
        training_config={"base_model": "emilyalsentzer/Bio_ClinicalBERT"},
        train_dataset="i2b2-2014",
        train_documents=790,
        eval_dataset=None,
        eval_fraction=0.1,
        eval_documents=79,
        seed=42,
        device_used="cuda:0",
        total_steps=1500,
        train_runtime_sec=412.3,
        head_reinitialised=False,
        metrics={
            "overall": {"precision": 0.942, "recall": 0.918, "f1": 0.930},
            "per_label": {},
            "confusion": None,
        },
    )

    p = model_dir / "model_manifest.json"
    assert p.exists()
    info = _load_manifest(p)

    assert info.schema_version == 2
    assert info.labels == ["NAME", "DATE"]
    assert info.base_model == "emilyalsentzer/Bio_ClinicalBERT"
    assert info.parent_model is None
    assert info.tokenizer == "emilyalsentzer/Bio_ClinicalBERT"
    assert info.has_crf is False
    assert info.training_meta["train_documents"] == 790
    assert info.training_meta["bio_labels"] == ["O", "B-NAME", "I-NAME", "B-DATE", "I-DATE"]
    assert info.training_meta["head_reinitialised"] is False
    assert info.metrics["overall"]["f1"] == pytest.approx(0.930)


def test_v2_with_parent_model(tmp_path):
    model_dir = tmp_path / "huggingface" / "fine-tuned-v2"
    model_dir.mkdir(parents=True, exist_ok=True)

    write_manifest_v2(
        model_dir,
        name="fine-tuned-v2",
        base_model="/models/huggingface/fine-tuned-v1",
        parent_model_name="fine-tuned-v1",
        tokenizer_source="/models/huggingface/fine-tuned-v1",
        labels=["NAME"],
        bio_labels=["O", "B-NAME", "I-NAME"],
        training_config={},
        train_dataset="ds",
        train_documents=100,
        eval_dataset=None,
        eval_fraction=None,
        eval_documents=0,
        seed=42,
        device_used="cpu",
        total_steps=50,
        train_runtime_sec=10.0,
        head_reinitialised=True,
        metrics={},
    )

    info = _load_manifest(model_dir / "model_manifest.json")
    assert info.parent_model == "fine-tuned-v1"
    assert info.training_meta["head_reinitialised"] is True
