"""Training configuration models."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

_SAFE_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


class TrainingHyperparams(BaseModel):
    epochs: float = 3.0
    learning_rate: float = 5e-5
    per_device_train_batch_size: int = 16
    per_device_eval_batch_size: int = 32
    max_length: int = 512
    warmup_ratio: float = 0.1
    weight_decay: float = 0.01
    seed: int = 42
    gradient_accumulation_steps: int = 1
    fp16: bool = False
    bf16: bool = False
    gradient_checkpointing: bool = False
    early_stopping_patience: int | None = None
    logging_steps: int = 50
    eval_steps: int | None = None


class TrainingConfig(BaseModel):
    base_model: str
    train_dataset: str
    extra_train_datasets: list[str] = Field(default_factory=list)
    eval_dataset: str | None = None
    eval_fraction: float | None = None
    test_dataset: str | None = None
    output_name: str
    labels: list[str] | None = None
    label_remap: dict[str, str] | None = None
    freeze_encoder: bool = False
    segmentation: Literal["truncate", "sentence"] = "truncate"
    hyperparams: TrainingHyperparams = Field(default_factory=TrainingHyperparams)
    device: str | None = None  # None → auto-detect: cuda→mps→cpu
    overwrite: bool = False

    @model_validator(mode="after")
    def _validate(self) -> TrainingConfig:
        if not self.base_model.strip():
            raise ValueError("base_model must be non-empty")
        if not _SAFE_NAME.match(self.output_name) or ".." in self.output_name:
            raise ValueError(
                f"Invalid output_name {self.output_name!r}: "
                f"must match {_SAFE_NAME.pattern} and not contain '..'"
            )
        if self.labels is not None:
            if not self.labels:
                raise ValueError("labels must be non-empty when provided")
            if len(self.labels) != len(set(self.labels)):
                raise ValueError("labels list must have no duplicates")
            if "O" in self.labels:
                raise ValueError("'O' is implicit and must not appear in labels")
        if self.eval_fraction is not None and not (0.0 < self.eval_fraction < 1.0):
            raise ValueError("eval_fraction must be in (0, 1)")
        if self.label_remap is not None:
            for src, tgt in self.label_remap.items():
                if not src.strip() or not tgt.strip():
                    raise ValueError("label_remap keys and values must be non-empty")
                if src == "O" or tgt == "O":
                    raise ValueError("'O' cannot appear in label_remap")
        return self
