"""Training package for fine-tuning HF encoder models for PHI NER.

Install the required extras before use:
    pip install 'pypedeid[train]'
"""

from __future__ import annotations

_DEPS_HINT = (
    "Training requires additional dependencies.\n"
    "  pip install 'pypedeid[train]'"
)

try:
    import datasets  # noqa: F401
    import torch  # noqa: F401
    import transformers  # noqa: F401

    _DEPS_AVAILABLE = True
except ImportError:
    _DEPS_AVAILABLE = False


def _check_deps() -> None:
    if not _DEPS_AVAILABLE:
        raise ImportError(_DEPS_HINT)


# Config is pure-pydantic and always importable
from pypedeid.training.config import TrainingConfig, TrainingHyperparams  # noqa: E402
from pypedeid.training.runner import run_training  # noqa: E402

__all__ = ["TrainingConfig", "TrainingHyperparams", "run_training", "_check_deps"]
