"""Symbolic pipeline output label space (detectors + label_mapper + label_filter)."""

from __future__ import annotations

from pypedeid.pipes.label_space import (
    effective_output_labels_from_pipeline,
    try_effective_input_labels_before_step,
    try_effective_output_labels_from_config,
)
from pypedeid.pipes.registry import load_pipeline


def test_label_mapper_renames_phone() -> None:
    cfg = {
        "pipes": [
            {"type": "regex_ner"},
            {"type": "label_mapper", "config": {"mapping": {"PHONE": "TELEPHONE"}}},
        ]
    }
    pl = load_pipeline(cfg)
    labs = effective_output_labels_from_pipeline(pl)
    assert "TELEPHONE" in labs
    assert "PHONE" not in labs


def test_label_filter_keep() -> None:
    cfg = {
        "pipes": [
            {"type": "regex_ner"},
            {"type": "label_filter", "config": {"keep": ["PHONE"]}},
        ]
    }
    pl = load_pipeline(cfg)
    labs = effective_output_labels_from_pipeline(pl)
    assert labs == {"PHONE"}


def test_try_effective_from_config_empty_pipeline() -> None:
    labels, err = try_effective_output_labels_from_config({"pipes": []})
    assert err is None
    assert labels == []


def test_input_labels_before_step_label_mapper() -> None:
    cfg = {
        "pipes": [
            {"type": "regex_ner"},
            {"type": "label_mapper", "config": {"mapping": {"PHONE": "TEL"}}},
        ]
    }
    before, err = try_effective_input_labels_before_step(cfg, 1)
    assert err is None
    assert before  # non-empty: regex_ner effective labels
    assert "PHONE" in before
