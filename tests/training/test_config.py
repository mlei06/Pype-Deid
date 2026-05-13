"""Tests for TrainingConfig / TrainingHyperparams validation."""

import pytest
from pydantic import ValidationError

from pypedeid.training.config import TrainingConfig, TrainingHyperparams


def test_default_hyperparams():
    hp = TrainingHyperparams()
    assert hp.epochs == 3.0
    assert hp.seed == 42
    assert hp.max_length == 512
    assert hp.early_stopping_patience is None


def test_valid_minimal_config():
    cfg = TrainingConfig(
        base_model="emilyalsentzer/Bio_ClinicalBERT",
        train_dataset="i2b2-2014",
        output_name="my-model",
    )
    assert cfg.base_model == "emilyalsentzer/Bio_ClinicalBERT"
    assert cfg.eval_dataset is None
    assert cfg.eval_fraction is None
    assert cfg.overwrite is False


def test_local_base_model_format():
    cfg = TrainingConfig(
        base_model="local:clinical-bert-v1",
        train_dataset="ds",
        output_name="model-v2",
    )
    assert cfg.base_model == "local:clinical-bert-v1"


def test_invalid_output_name_special_chars():
    with pytest.raises(ValidationError, match="output_name"):
        TrainingConfig(
            base_model="bert-base-uncased",
            train_dataset="ds",
            output_name="../sneaky",
        )


def test_invalid_output_name_starts_with_dot():
    with pytest.raises(ValidationError, match="output_name"):
        TrainingConfig(
            base_model="bert-base-uncased",
            train_dataset="ds",
            output_name=".hidden",
        )


def test_output_name_dotted_ok():
    cfg = TrainingConfig(
        base_model="bert-base-uncased",
        train_dataset="ds",
        output_name="my-model.v1",
    )
    assert cfg.output_name == "my-model.v1"


def test_labels_deduplication_error():
    with pytest.raises(ValidationError, match="duplicates"):
        TrainingConfig(
            base_model="bert-base-uncased",
            train_dataset="ds",
            output_name="model",
            labels=["NAME", "DATE", "NAME"],
        )


def test_labels_O_not_allowed():
    with pytest.raises(ValidationError, match="'O' is implicit"):
        TrainingConfig(
            base_model="bert-base-uncased",
            train_dataset="ds",
            output_name="model",
            labels=["NAME", "O"],
        )


def test_labels_empty_not_allowed():
    with pytest.raises(ValidationError, match="non-empty"):
        TrainingConfig(
            base_model="bert-base-uncased",
            train_dataset="ds",
            output_name="model",
            labels=[],
        )


def test_eval_fraction_out_of_range():
    with pytest.raises(ValidationError, match="eval_fraction"):
        TrainingConfig(
            base_model="bert-base-uncased",
            train_dataset="ds",
            output_name="model",
            eval_fraction=1.5,
        )


def test_both_eval_dataset_and_fraction_ok():
    # Both set is allowed (eval_dataset takes priority at runtime)
    cfg = TrainingConfig(
        base_model="bert-base-uncased",
        train_dataset="ds",
        output_name="model",
        eval_dataset="eval-ds",
        eval_fraction=0.1,
    )
    assert cfg.eval_dataset == "eval-ds"
    assert cfg.eval_fraction == 0.1


def test_neither_eval_ok():
    # Neither set → no eval pass
    cfg = TrainingConfig(
        base_model="bert-base-uncased",
        train_dataset="ds",
        output_name="model",
    )
    assert cfg.eval_dataset is None
    assert cfg.eval_fraction is None


def test_hyperparams_override():
    cfg = TrainingConfig(
        base_model="bert-base-uncased",
        train_dataset="ds",
        output_name="model",
        hyperparams=TrainingHyperparams(epochs=10, seed=99),
    )
    assert cfg.hyperparams.epochs == 10
    assert cfg.hyperparams.seed == 99
