"""User-facing training error hierarchy."""

from __future__ import annotations


class TrainingError(Exception):
    """Base class for all training errors."""


class BaseModelNotFound(TrainingError):
    """local: reference that doesn't resolve to a known model."""


class IncompatibleFramework(TrainingError):
    """Local base model is not framework='huggingface'."""


class OutputExists(TrainingError):
    """Target output directory already exists and overwrite=False."""


class SlowTokenizerUnsupported(TrainingError):
    """Base model has no fast tokenizer (word_ids() not available)."""


class EmptyDataset(TrainingError):
    """Train split has zero documents after loading."""


class NoLabelsFound(TrainingError):
    """After label derivation only 'O' is present — nothing to train."""
