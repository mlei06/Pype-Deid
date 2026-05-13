"""Pipe combinators: Pipeline, ResolveSpans, LabelMapper, LabelFilter."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from pypedeid.domain import AnnotatedDocument
from pypedeid.pipes.base import ConfigurablePipe, Pipe
from pypedeid.pipes.detector_label_mapping import remap_span_labels
from pypedeid.pipes.span_merge import DEFAULT_LABEL_PRIORITY, apply_resolve_spans
from pypedeid.pipes.trace import PipelineRunResult, PipelineTraceFrame, snapshot_document
from pypedeid.pipes.ui_schema import field_ui


# ---------------------------------------------------------------------------
# ResolveSpans — span transformer (single- or multi-detector via span groups)
# ---------------------------------------------------------------------------


ResolutionStrategy = Literal[
    "exact_dedupe",
    "longest_non_overlapping",
    "max_confidence",
    "consensus",
    "left_to_right",
    "label_priority",
]

_STRATEGY_DESCRIPTIONS: dict[str, str] = {
    "exact_dedupe": "Remove exact-duplicate spans (same start, end, and label).",
    "longest_non_overlapping": "Keep the longest span when overlaps occur; drop shorter overlapping spans.",
    "max_confidence": "Keep the highest-confidence span when overlaps occur.",
    "consensus": "Keep spans that multiple detectors agree on (requires consensus threshold).",
    "left_to_right": "Process spans in document order — the leftmost span wins on overlap.",
    "label_priority": "Highest-risk label wins on overlap, using a configurable priority ranking.",
}


class ResolveSpansConfig(BaseModel):
    """Handle overlapping and duplicate spans produced by upstream detectors."""

    strategy: ResolutionStrategy = Field(
        default="exact_dedupe",
        title="Strategy",
        description="How to handle overlapping spans.",
        json_schema_extra=field_ui(
            ui_group="Resolution",
            ui_order=1,
            ui_widget="described_select",
            ui_enum_descriptions=_STRATEGY_DESCRIPTIONS,
        ),
    )
    consensus_threshold: int = Field(
        default=2,
        ge=1,
        title="Consensus Threshold",
        description="Minimum number of detectors that must agree on a span.",
        json_schema_extra=field_ui(
            ui_group="Resolution",
            ui_order=2,
            ui_widget="number",
            ui_visible_when={"field": "strategy", "equals": "consensus"},
        ),
    )
    label_priority: list[str] = Field(
        default_factory=lambda: list(DEFAULT_LABEL_PRIORITY),
        title="Label Priority",
        description=(
            "Ordered list of labels (first = highest risk). "
            "Pre-populated with the built-in HIPAA risk ranking — reorder, remove, or add labels as needed."
        ),
        json_schema_extra={
            "default": list(DEFAULT_LABEL_PRIORITY),
            **field_ui(
                ui_group="Resolution",
                ui_order=3,
                ui_widget="tag_list",
                ui_visible_when={"field": "strategy", "equals": "label_priority"},
            ),
        },
    )


class ResolveSpans(ConfigurablePipe):
    """SpanTransformer that applies :func:`~pypedeid.pipes.span_merge.apply_resolve_spans` to ``doc.spans``."""

    def __init__(self, config: ResolveSpansConfig | None = None) -> None:
        self._config = config or ResolveSpansConfig()

    def forward(self, doc: AnnotatedDocument) -> AnnotatedDocument:
        merged = apply_resolve_spans(
            [list(doc.spans)],
            strategy=self._config.strategy,
            consensus_threshold=self._config.consensus_threshold,
            label_priority=self._config.label_priority or None,
        )
        return doc.with_spans(merged)


# ---------------------------------------------------------------------------
# LabelMapper
# ---------------------------------------------------------------------------


class LabelFilterConfig(BaseModel):
    """Configuration for LabelFilter.

    Provide *drop* to remove specific labels, or *keep* to retain only those labels.
    Exactly one of *drop* or *keep* must be set.
    """

    drop: list[str] | None = Field(
        default=None,
        json_schema_extra=field_ui(
            ui_group="Filter",
            ui_order=1,
            ui_widget="multiselect",
            ui_help="Remove spans with these labels. Do not set both drop and keep.",
        ),
    )
    keep: list[str] | None = Field(
        default=None,
        json_schema_extra=field_ui(
            ui_group="Filter",
            ui_order=2,
            ui_widget="multiselect",
            ui_help="Keep only these labels. Do not set both drop and keep.",
        ),
    )

    def model_post_init(self, __context: object) -> None:
        if self.drop and self.keep:
            raise ValueError("Provide either 'drop' or 'keep', not both")
        if not self.drop and not self.keep:
            raise ValueError("Provide either 'drop' or 'keep'")


class LabelFilter(ConfigurablePipe):
    """Remove or retain spans by label."""

    def __init__(self, config: LabelFilterConfig) -> None:
        self._config = config

    def forward(self, doc: AnnotatedDocument) -> AnnotatedDocument:
        if self._config.drop:
            drop_set = set(self._config.drop)
            out = [s for s in doc.spans if s.label not in drop_set]
        else:
            keep_set = set(self._config.keep)  # type: ignore[arg-type]
            out = [s for s in doc.spans if s.label in keep_set]
        return doc.with_spans(out)


class LabelMapperConfig(BaseModel):
    """Configuration for LabelMapper."""

    mapping: dict[str, str | None] = Field(
        ...,
        json_schema_extra=field_ui(
            ui_group="Mapping",
            ui_order=1,
            ui_widget="label_mapping",
            ui_help="Map a label to null to drop spans with that label.",
        ),
    )
    drop_unmapped: bool = Field(
        default=False,
        json_schema_extra=field_ui(
            ui_group="Mapping",
            ui_order=2,
            ui_widget="switch",
            ui_help="If true, drop spans whose label is not a key in mapping.",
        ),
    )


class LabelMapper(ConfigurablePipe):
    """SpanTransformer that remaps span labels.

    Map a label to ``null`` to drop spans with that label.
    Unmapped labels are kept as-is unless *drop_unmapped* is True.
    """

    def __init__(self, config: LabelMapperConfig) -> None:
        self._config = config

    def forward(self, doc: AnnotatedDocument) -> AnnotatedDocument:
        return doc.with_spans(
            remap_span_labels(
                list(doc.spans),
                self._config.mapping,
                drop_unmapped=self._config.drop_unmapped,
            )
        )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def _pipe_type_label(pipe: Pipe) -> str:
    if isinstance(pipe, Pipeline):
        return "pipeline"
    return type(pipe).__name__


@dataclass
class Pipeline:
    """Top-level sequential runner.

    Entries can be any ``Pipe``, ``ResolveSpans``, ``BlacklistSpans``,
    or nested ``Pipeline``.

    Pass ``trace=True`` to :meth:`forward` to capture intermediate document
    state after every step.
    """

    pipes: list[Pipe | ResolveSpans | Pipeline] = field(
        default_factory=list
    )

    @property
    def labels(self) -> set[str]:
        """Union of all detector labels in the pipeline."""
        out: set[str] = set()
        for p in self.pipes:
            if hasattr(p, "labels"):
                out |= p.labels  # type: ignore[union-attr]
        return out

    def forward(self, doc: AnnotatedDocument) -> AnnotatedDocument:
        """Run the pipeline. Conforms to the :class:`Pipe` protocol."""
        return self.run(doc).final

    def run(
        self,
        doc: AnnotatedDocument,
        *,
        trace: bool = False,
        timing: bool = False,
        _path_prefix: str = "",
    ) -> PipelineRunResult:
        """Run the pipeline, optionally collecting trace frames and/or per-step timing.

        *trace* captures document snapshots (deep copy) after each step.
        *timing* records ``elapsed_ms`` per step and ``total_elapsed_ms`` on the result.
        Both can be enabled independently.
        """
        frames: list[PipelineTraceFrame] = []
        t_total = time.perf_counter() if timing else 0.0
        for i, pipe in enumerate(self.pipes):
            step_path = f"{_path_prefix}step_{i}" if _path_prefix else f"step_{i}"

            if isinstance(pipe, Pipeline):
                sub = pipe.run(doc, trace=trace, timing=timing, _path_prefix=f"{step_path}/")
                doc = sub.final
                frames.extend(sub.trace)
            else:
                t0 = time.perf_counter() if timing else 0.0
                doc = pipe.forward(doc)
                step_ms = (time.perf_counter() - t0) * 1000 if timing else None

                if trace or timing:
                    frames.append(
                        PipelineTraceFrame(
                            path=step_path,
                            stage="sequential",
                            pipe_type=_pipe_type_label(pipe),
                            document=snapshot_document(doc) if trace else None,
                            elapsed_ms=step_ms,
                        )
                    )

        total_ms = (time.perf_counter() - t_total) * 1000 if timing else None
        return PipelineRunResult(final=doc, trace=frames, total_elapsed_ms=total_ms)

    def __call__(self, doc: AnnotatedDocument) -> AnnotatedDocument:
        return self.forward(doc)
