from pypedeid.pipes.base import (
    ConfigurablePipe,
    Detector,
    DetectorWithLabelMapping,
    Pipe,
    Preprocessor,
    SpanTransformer,
)
from pypedeid.pipes.detector_label_mapping import (
    DETECTOR_LABEL_MAPPING,
    DETECTOR_LABEL_MAPPING_DESCRIPTION,
    accumulate_spans,
    apply_detector_label_mapping,
    detector_label_mapping_field,
    effective_detector_labels,
    remap_label_set,
    remap_span_labels,
)
from pypedeid.pipes.ui_schema import field_ui, pipe_config_json_schema
from pypedeid.pipes.blacklist import (
    BlacklistSpans,
    BlacklistSpansConfig,
    blacklist_regions_for_text,
)
from pypedeid.pipes.combinators import (
    LabelFilter,
    LabelFilterConfig,
    LabelMapper,
    LabelMapperConfig,
    Pipeline,
    ResolveSpans,
    ResolveSpansConfig,
)
from pypedeid.pipes.regex_ner import (
    BUILTIN_REGEX_PATTERNS,
    RegexLabelSettings,
    RegexNerConfig,
    RegexNerPipe,
    builtin_regex_label_names,
)
from pypedeid.pipes.registry import (
    dump_pipeline,
    dump_pipeline_json,
    load_pipeline,
    pipe_availability,
    pipe_catalog,
    register,
    registered_pipes,
    save_pipeline,
)
from pypedeid.pipes.trace import PipelineRunResult, PipelineTraceFrame, snapshot_document
from pypedeid.pipes.span_merge import MergeStrategy, apply_resolve_spans
from pypedeid.pipes.whitelist import WhitelistConfig, WhitelistPipe, WhitelistLabelConfig, WhitelistLabelSettings

__all__ = [
    # Base
    "ConfigurablePipe",
    # Protocols
    "Detector",
    "DetectorWithLabelMapping",
    "DETECTOR_LABEL_MAPPING",
    "DETECTOR_LABEL_MAPPING_DESCRIPTION",
    "detector_label_mapping_field",
    "apply_detector_label_mapping",
    "accumulate_spans",
    "effective_detector_labels",
    "remap_label_set",
    "remap_span_labels",
    "field_ui",
    "pipe_config_json_schema",
    "Pipe",
    "Preprocessor",
    "SpanTransformer",
    # Combinators
    "LabelFilter",
    "LabelFilterConfig",
    "LabelMapper",
    "LabelMapperConfig",
    "MergeStrategy",
    "Pipeline",
    "PipelineRunResult",
    "PipelineTraceFrame",
    "snapshot_document",
    "ResolveSpans",
    "ResolveSpansConfig",
    "apply_resolve_spans",
    # Span transformers
    "BlacklistSpans",
    "BlacklistSpansConfig",
    "blacklist_regions_for_text",
    # Detectors
    "BUILTIN_REGEX_PATTERNS",
    "RegexLabelSettings",
    "RegexNerConfig",
    "RegexNerPipe",
    "WhitelistLabelConfig",
    "WhitelistLabelSettings",
    "WhitelistConfig",
    "WhitelistPipe",
    "builtin_regex_label_names",
    # Registry / serialization
    "dump_pipeline",
    "dump_pipeline_json",
    "load_pipeline",
    "pipe_availability",
    "pipe_catalog",
    "register",
    "registered_pipes",
    "save_pipeline",
]

# Optional: Presidio NER — available when `pip install .[presidio]`
try:
    from pypedeid.pipes.presidio_ner import PresidioNerConfig, PresidioNerPipe

    __all__ += [
        "PresidioNerConfig",
        "PresidioNerPipe",
    ]
except ImportError:
    pass
