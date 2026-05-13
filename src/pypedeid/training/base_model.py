"""Base-model resolution: HF Hub id vs local:{name}."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class ResolvedBaseModel:
    kind: Literal["hub", "local"]
    source: str                     # hub id or absolute path string
    parent_model_name: str | None   # local model name; None for hub
    saved_label_space: list[str]    # manifest labels for local; [] for hub
    tokenizer_source: str


def resolve_base_model(ref: str, models_dir: Path) -> ResolvedBaseModel:
    """Resolve a base_model reference to a ResolvedBaseModel.

    Hub ids (no 'local:' prefix) pass through without validation — let
    transformers raise at load time so the error message is clear.
    """
    if ref.startswith("local:"):
        return _resolve_local(ref[len("local:"):], models_dir)
    return ResolvedBaseModel(
        kind="hub",
        source=ref,
        parent_model_name=None,
        saved_label_space=[],
        tokenizer_source=ref,
    )


def _resolve_local(name: str, models_dir: Path) -> ResolvedBaseModel:
    from pypedeid.models import get_model
    from pypedeid.training.errors import BaseModelNotFound, IncompatibleFramework

    try:
        info = get_model(models_dir, name)
    except KeyError as exc:
        raise BaseModelNotFound(str(exc)) from exc

    if info.framework != "huggingface":
        raise IncompatibleFramework(
            f"Model {name!r} uses framework {info.framework!r}; "
            "only 'huggingface' models can be used as a training base."
        )

    source = str(info.path)
    return ResolvedBaseModel(
        kind="local",
        source=source,
        parent_model_name=name,
        saved_label_space=info.labels,
        tokenizer_source=source,
    )
