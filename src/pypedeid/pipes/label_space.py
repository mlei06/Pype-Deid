"""Approximate the set of span label strings a pipeline can emit after all detector remaps
and sequential ``label_mapper`` / ``label_filter`` steps.

This is a **symbolic** upper bound: resolve/blacklist steps may remove spans without renaming
labels, so the true set of labels observed at runtime can be a subset."""

from __future__ import annotations

from pypedeid.pipes.base import Pipe
from pypedeid.pipes.combinators import LabelFilter, LabelMapper, Pipeline
from pypedeid.pipes.detector_label_mapping import remap_label_set


def _flatten_steps(pipe: Pipeline | Pipe) -> list[Pipe]:
    """Flatten nested :class:`Pipeline` steps into a linear execution order."""
    if isinstance(pipe, Pipeline):
        out: list[Pipe] = []
        for child in pipe.pipes:
            out.extend(_flatten_steps(child))
        return out
    return [pipe]


def effective_output_labels_from_pipeline(pipe: Pipeline) -> set[str]:
    """Fold detector ``.labels`` and span transformers in execution order.

    - Detectors: union their effective output label sets (``pipe.labels``).
    - :class:`LabelMapper`: apply mapping (and optional drop of unmapped keys).
    - :class:`LabelFilter`: intersect with ``keep`` or subtract ``drop``.
    - Other span transformers (resolve, blacklist, …): assumed not to introduce new label strings.
    """
    steps = _flatten_steps(pipe)
    acc: set[str] = set()
    for p in steps:
        if isinstance(p, LabelMapper):
            acc = remap_label_set(
                acc,
                dict(p._config.mapping),
                drop_unmapped=p._config.drop_unmapped,
            )
        elif isinstance(p, LabelFilter):
            cfg = p._config
            if cfg.drop:
                acc -= set(cfg.drop)
            elif cfg.keep:
                acc &= set(cfg.keep)
        elif hasattr(p, "labels"):
            lbl = getattr(p, "labels")
            if isinstance(lbl, (set, frozenset)):
                acc |= lbl
            else:
                acc |= set(lbl)
        # Else: no change to the symbolic label set (subset in reality).
    return acc


def try_effective_output_labels_from_config(config: dict) -> tuple[list[str] | None, str | None]:
    """Load pipeline from *config* and return sorted labels, or ``(None, error)``."""
    try:
        from pypedeid.pipes.registry import load_pipeline

        pl = load_pipeline(config)
        labs = effective_output_labels_from_pipeline(pl)
        return sorted(labs), None
    except Exception as exc:
        return None, str(exc)


def try_effective_input_labels_before_step(
    full_config: dict, step_index: int
) -> tuple[list[str] | None, str | None]:
    """Symbolic label set **entering** the pipe at *step_index* (i.e. after ``pipes[:step_index]``).

    Used by the pipeline builder to suggest ``label_mapper`` mapping keys. This is an upper bound
    (same caveats as :func:`effective_output_labels_from_pipeline`).
    """
    pipes = full_config.get("pipes")
    if not isinstance(pipes, list):
        return None, "config must contain a 'pipes' array"
    if step_index < 0:
        return None, "step_index must be non-negative"
    if step_index > len(pipes):
        return None, f"step_index must be <= len(pipes) ({len(pipes)})"
    prefix = {k: v for k, v in full_config.items() if k != "pipes"}
    prefix["pipes"] = pipes[:step_index]
    try:
        from pypedeid.pipes.registry import load_pipeline

        pl = load_pipeline(prefix)
        labs = effective_output_labels_from_pipeline(pl)
        return sorted(labs), None
    except Exception as exc:
        return None, str(exc)


def enrich_pipeline_config_with_label_space(config: dict) -> dict:
    """Return a copy of *config* with ``output_label_space`` / ``output_label_space_updated_at`` set."""
    from datetime import datetime, timezone

    out = dict(config)
    labels, err = try_effective_output_labels_from_config(out)
    if labels is not None:
        out["output_label_space"] = labels
        out["output_label_space_updated_at"] = datetime.now(timezone.utc).isoformat()
    # On failure, leave ``out`` unchanged (caller already validated loadability).
    return out
