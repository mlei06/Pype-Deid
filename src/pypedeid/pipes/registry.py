"""Pipe registry and JSON serialization.

Provides a central registry that maps type names to (config_class, pipe_class)
pairs, plus functions to load/dump entire pipelines from/to JSON.

JSON schema example::

    {
      "pipes": [
        {"type": "regex_ner", "config": {"label_mapping": {"PHONE": "TEL", "DATE": null}}},
        {"type": "whitelist"},
        {"type": "presidio_ner", "config": {"model": "HuggingFace/obi/deid_roberta_i2b2"}},
        {"type": "label_mapper", "config": {"mapping": {"NAME": "PATIENT"}}},
        {"type": "resolve_spans", "config": {"strategy": "longest_non_overlapping"}}
      ]
    }
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

from pypedeid.pipes.base import ConfigurablePipe, Pipe

LabelSource = Literal["none", "compute", "bundle", "both"]
BundleKeySemantics = Literal["ner_raw", "presidio_entity"]

if TYPE_CHECKING:
    from pypedeid.pipes.combinators import Pipeline

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, tuple[type[BaseModel], type]] = {}


def _import_dotted(path: str) -> type:
    """Import ``'some.module:ClassName'`` and return the class."""
    module_path, class_name = path.rsplit(":", 1)
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


def register(name: str, config_cls: type[BaseModel], pipe_cls: type) -> None:
    """Register a pipe type so it can be referenced by *name* in JSON."""
    _REGISTRY[name] = (config_cls, pipe_cls)


def registered_pipes() -> dict[str, type[BaseModel]]:
    """Return ``{name: config_class}`` for all registered pipes."""
    return {name: cfg for name, (cfg, _) in _REGISTRY.items()}


# ---------------------------------------------------------------------------
# Pipe catalog — all known pipe types, including uninstalled ones
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PipeCatalogEntry:
    """Describes a pipe type that the system knows about."""

    name: str
    description: str
    role: str  # "detector", "span_transformer", "preprocessor"
    extra: str | None  # pip extra name, e.g. "presidio", or None if always available
    install_hint: str  # human-readable install command
    config_path: str  # "module.path:ConfigClass"
    pipe_path: str  # "module.path:PipeClass"
    # Optional callable returning (ready: bool, details: dict) for pipes whose
    # availability depends on runtime state beyond Python imports (e.g. venvs,
    # downloaded models, embeddings).  ``None`` means "installed == ready".
    check_ready: str | None = None  # "module.path:function_name"
    # Zero-arg callable returning ``list[str]`` of default base labels.
    # Only meaningful for detector-role entries.
    default_base_labels_fn: str | None = None  # "module.path:function_name"
    # How the playground discovers this detector's label space:
    #   "none"    — no label-space UI (span_transformers, preprocessors)
    #   "compute" — POST /pipe-types/{name}/labels with a config
    #   "bundle"  — GET /pipe-types/{name}/label-space-bundle (one fetch, switch models client-side)
    #   "both"    — bundle for fast switching; POST also available
    label_source: LabelSource = "none"
    # Zero-arg callable returning a ``LabelSpaceBundle``-shaped dict.
    # Required when ``label_source in {"bundle", "both"}``.
    label_space_bundle_fn: str | None = None  # "module.path:function_name"
    # How the bundle's ``labels_by_model`` keys should be interpreted by the
    # frontend before merging with ``entity_map``.  Required for "bundle"/"both".
    bundle_key_semantics: BundleKeySemantics | None = None
    # Map from ``ui_options_source`` token to a zero-arg callable returning
    # ``list[str]``.  Used by the catalog to populate ``enum`` values for
    # dynamic select widgets without the router knowing the source name.
    dynamic_options_fns: dict[str, str] = field(default_factory=dict)
    # Optional callable taking ``(config: dict | None) -> list[str]`` returning
    # missing-dependency tags (e.g. ``"model:foo"``) for deploy health checks.
    dependencies_fn: str | None = None  # "module.path:function_name"
    deprecated: bool = False


_CATALOG: list[PipeCatalogEntry] = [
    PipeCatalogEntry(
        name="regex_ner",
        description="Regex-only PHI detection (built-in clinical patterns per label)",
        role="detector",
        extra=None,
        install_hint="Included by default",
        config_path="pypedeid.pipes.regex_ner.pipe:RegexNerConfig",
        pipe_path="pypedeid.pipes.regex_ner.pipe:RegexNerPipe",
        default_base_labels_fn="pypedeid.pipes.regex_ner.pipe:default_base_labels",
        label_source="compute",
    ),
    PipeCatalogEntry(
        name="whitelist",
        description="Phrase / dictionary (gazetteer) matching per label; chain with regex_ner for combined coverage",
        role="detector",
        extra=None,
        install_hint="Included by default",
        config_path="pypedeid.pipes.whitelist.pipe:WhitelistConfig",
        pipe_path="pypedeid.pipes.whitelist.pipe:WhitelistPipe",
        default_base_labels_fn="pypedeid.pipes.whitelist.pipe:default_base_labels",
        label_source="compute",
    ),
    PipeCatalogEntry(
        name="label_mapper",
        description=(
            "Remap all span labels on the document (e.g. unify detectors: PATIENT → PERSON). "
            "Use after merge/resolve; per-detector label_mapping only affects that detector's output."
        ),
        role="span_transformer",
        extra=None,
        install_hint="Included by default",
        config_path="pypedeid.pipes.combinators:LabelMapperConfig",
        pipe_path="pypedeid.pipes.combinators:LabelMapper",
    ),
    PipeCatalogEntry(
        name="label_filter",
        description="Drop or keep only specific labels",
        role="span_transformer",
        extra=None,
        install_hint="Included by default",
        config_path="pypedeid.pipes.combinators:LabelFilterConfig",
        pipe_path="pypedeid.pipes.combinators:LabelFilter",
    ),
    PipeCatalogEntry(
        name="resolve_spans",
        description="Resolve overlapping or duplicate spans from upstream detectors.",
        role="span_transformer",
        extra=None,
        install_hint="Included by default",
        config_path="pypedeid.pipes.combinators:ResolveSpansConfig",
        pipe_path="pypedeid.pipes.combinators:ResolveSpans",
    ),
    PipeCatalogEntry(
        name="blacklist",
        description=(
            "Remove spans matching a benign-term blacklist (false-positive filter)"
        ),
        role="span_transformer",
        extra=None,
        install_hint="Included by default",
        config_path="pypedeid.pipes.blacklist.pipe:BlacklistSpansConfig",
        pipe_path="pypedeid.pipes.blacklist.pipe:BlacklistSpans",
    ),
    PipeCatalogEntry(
        name="presidio_ner",
        description="PHI detection via Microsoft Presidio (spaCy, HuggingFace, Stanza, Flair)",
        role="detector",
        extra="presidio",
        install_hint="pip install '.[presidio]'",
        config_path="pypedeid.pipes.presidio_ner.pipe:PresidioNerConfig",
        pipe_path="pypedeid.pipes.presidio_ner.pipe:PresidioNerPipe",
        default_base_labels_fn="pypedeid.pipes.presidio_ner.pipe:default_base_labels",
        label_source="bundle",
        label_space_bundle_fn="pypedeid.pipes.presidio_ner.pipe:build_presidio_label_space_bundle",
        bundle_key_semantics="presidio_entity",
    ),
    PipeCatalogEntry(
        name="consistency_propagator",
        description=(
            "Propagate high-confidence spans to all matching text occurrences in the document"
        ),
        role="span_transformer",
        extra=None,
        install_hint="Included by default",
        config_path="pypedeid.pipes.consistency_propagator:ConsistencyPropagatorConfig",
        pipe_path="pypedeid.pipes.consistency_propagator:ConsistencyPropagatorPipe",
    ),
    PipeCatalogEntry(
        name="llm_ner",
        description="LLM-prompted PHI detection via OpenAI Responses API (text-based extraction)",
        role="detector",
        extra="llm",
        install_hint="pip install '.[llm]'",
        config_path="pypedeid.pipes.llm_ner:LlmNerConfig",
        pipe_path="pypedeid.pipes.llm_ner:LlmNerPipe",
        default_base_labels_fn="pypedeid.pipes.llm_ner:default_base_labels",
        label_source="compute",
    ),
    PipeCatalogEntry(
        name="neuroner_ner",
        description="Clinical PHI detection via NeuroNER LSTM-CRF (Docker HTTP sidecar)",
        role="detector",
        extra=None,
        install_hint=(
            "Inference: docker compose -f neuroner-cspmc/sidecar/compose.yaml up -d. "
            "Training: ./scripts/setup_neuroner.sh"
        ),
        config_path="pypedeid.pipes.neuroner_ner.pipe:NeuroNerConfig",
        pipe_path="pypedeid.pipes.neuroner_ner.pipe:NeuroNerPipe",
        check_ready="pypedeid.pipes.neuroner_ner.pipe:check_neuroner_ready",
        default_base_labels_fn="pypedeid.pipes.neuroner_ner.pipe:default_base_labels",
        label_source="bundle",
        label_space_bundle_fn="pypedeid.pipes.neuroner_ner.pipe:build_neuroner_label_space_bundle",
        bundle_key_semantics="ner_raw",
        dynamic_options_fns={
            "neuroner_models": "pypedeid.pipes.neuroner_ner.pipe:list_neuroner_model_names",
        },
    ),
    PipeCatalogEntry(
        name="huggingface_ner",
        description="Hugging Face token-classification model loaded from models/huggingface/",
        role="detector",
        extra=None,
        install_hint=(
            "Place a trained model under models/huggingface/{name}/ with model_manifest.json. "
            "Requires: pip install transformers torch"
        ),
        config_path="pypedeid.pipes.huggingface_ner.pipe:HuggingfaceNerConfig",
        pipe_path="pypedeid.pipes.huggingface_ner.pipe:HuggingfaceNerPipe",
        default_base_labels_fn="pypedeid.pipes.huggingface_ner.pipe:default_base_labels",
        label_source="bundle",
        label_space_bundle_fn=(
            "pypedeid.pipes.huggingface_ner.pipe:build_huggingface_label_space_bundle"
        ),
        bundle_key_semantics="ner_raw",
        dynamic_options_fns={
            "huggingface_models": (
                "pypedeid.pipes.huggingface_ner.pipe:list_huggingface_model_names"
            ),
        },
        dependencies_fn=(
            "pypedeid.pipes.huggingface_ner.pipe:huggingface_ner_dependencies"
        ),
    ),
]


def pipe_catalog() -> list[PipeCatalogEntry]:
    """Return the full catalog of known pipe types."""
    return list(_CATALOG)


def compute_base_labels(pipe_name: str, config: dict[str, Any] | None = None) -> list[str]:
    """Compute the base label space for a detector given optional config.

    Instantiates the config class (using defaults if *config* is ``None``),
    then builds a temporary pipe to read ``base_labels``.  Falls back to the
    catalog's static ``default_base_labels_fn`` on any error.
    """
    entry_map = {e.name: e for e in _CATALOG}
    cat = entry_map.get(pipe_name)
    if cat is None:
        return []

    reg = _REGISTRY.get(pipe_name)
    if reg is not None:
        config_cls, pipe_cls = reg
        try:
            cfg = config_cls.model_validate(config or {})
            pipe = pipe_cls(cfg)
            if hasattr(pipe, "base_labels"):
                return sorted(pipe.base_labels)
        except Exception:
            pass

    if cat.default_base_labels_fn is not None:
        try:
            fn = _import_dotted(cat.default_base_labels_fn)
            return fn()
        except Exception:
            pass

    return []


def get_catalog_entry(pipe_name: str) -> PipeCatalogEntry | None:
    """Return the catalog entry for *pipe_name*, or ``None`` if unknown."""
    for entry in _CATALOG:
        if entry.name == pipe_name:
            return entry
    return None


def get_label_space_bundle(pipe_name: str) -> dict[str, Any] | None:
    """Build the label-space bundle for *pipe_name*.

    Returns ``None`` when the pipe is unknown or does not declare a bundle
    (``label_source not in {'bundle', 'both'}`` or no ``label_space_bundle_fn``).
    """
    entry = get_catalog_entry(pipe_name)
    if entry is None or entry.label_source not in ("bundle", "both"):
        return None
    if entry.label_space_bundle_fn is None:
        return None
    fn = _import_dotted(entry.label_space_bundle_fn)
    return fn()


def resolve_dynamic_options(source: str) -> list[str] | None:
    """Look up a ``ui_options_source`` token across all catalog entries.

    Returns the resolver's output (``list[str]``) or ``None`` if no entry
    declares this source.  Falls back to ``None`` if the resolver raises.
    """
    for entry in _CATALOG:
        dotted = entry.dynamic_options_fns.get(source)
        if dotted is None:
            continue
        try:
            fn = _import_dotted(dotted)
            return fn()
        except Exception:
            return None
    return None


def pipe_dependencies(pipe_name: str, config: dict[str, Any] | None) -> list[str]:
    """Return missing-dependency tags for a single pipe given its config.

    Each tag is a string like ``"model:foo"``.  Empty list means the pipe
    has no declared dependency check or all dependencies resolve.
    """
    entry = get_catalog_entry(pipe_name)
    if entry is None or entry.dependencies_fn is None:
        return []
    try:
        fn = _import_dotted(entry.dependencies_fn)
        return list(fn(config or {}))
    except Exception as exc:
        return [f"dependency_check_error:{pipe_name}:{exc}"]


def pipe_check_ready(pipe_name: str) -> dict[str, Any]:
    """Run the catalog ``check_ready`` hook (if any) for *pipe_name*.

    Returns a dict with:

    - ``installed`` (bool): whether the pipe is currently registered
    - ``ready`` (bool): ``installed`` and (if ``check_ready`` is defined) the
      hook reported ready
    - ``ready_details`` (dict | None): granular detail from ``check_ready``
    - ``install_hint`` (str | None): the catalog's install_hint when present

    Unknown pipe names return ``installed=False`` / ``ready=False``.
    """
    entry = get_catalog_entry(pipe_name)
    if entry is None:
        return {
            "installed": False,
            "ready": False,
            "ready_details": None,
            "install_hint": None,
        }
    installed = pipe_name in _REGISTRY
    ready = installed
    ready_details: dict[str, Any] | None = None
    if installed and entry.check_ready is not None:
        try:
            check_fn = _import_dotted(entry.check_ready)
            ready, ready_details = check_fn()
        except Exception as exc:
            ready = False
            ready_details = {"error": str(exc)}
    return {
        "installed": installed,
        "ready": ready,
        "ready_details": ready_details,
        "install_hint": entry.install_hint,
    }


def pipe_availability() -> list[dict[str, Any]]:
    """Return each known pipe type with its install status.

    Each entry has:
    - ``name``, ``description``, ``role``, ``install_hint`` from the catalog
    - ``installed`` (bool): whether the pipe is currently registered
    - ``extra``: pip extra group name, or null
    - ``ready`` (bool): whether the pipe can actually run (always True when
      there is no ``check_ready`` hook and the pipe is installed)
    - ``ready_details`` (dict | null): granular status from ``check_ready``
    """
    registered = set(_REGISTRY)
    out: list[dict[str, Any]] = []
    for entry in _CATALOG:
        installed = entry.name in registered
        ready = installed
        ready_details: dict[str, Any] | None = None

        if installed and entry.check_ready is not None:
            try:
                check_fn = _import_dotted(entry.check_ready)
                ready, ready_details = check_fn()
            except Exception as exc:
                ready = False
                ready_details = {"error": str(exc)}

        base_labels: list[str] | None = None
        if entry.default_base_labels_fn is not None:
            try:
                labels_fn = _import_dotted(entry.default_base_labels_fn)
                base_labels = labels_fn()
            except Exception:
                base_labels = None

        out.append({
            "name": entry.name,
            "description": entry.description,
            "role": entry.role,
            "extra": entry.extra,
            "install_hint": entry.install_hint,
            "installed": installed,
            "ready": ready,
            "ready_details": ready_details,
            "base_labels": base_labels,
            "label_source": entry.label_source,
            "bundle_key_semantics": entry.bundle_key_semantics,
            "deprecated": entry.deprecated,
        })
    return out


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def _load_pipeline_from_dict(spec: dict[str, Any]) -> Pipeline:
    """Build :class:`~pypedeid.pipes.combinators.Pipeline` from a dict with ``pipes``."""
    from pypedeid.pipes.combinators import Pipeline as PipelineCls

    if "pipes" not in spec:
        raise ValueError(f"pipeline spec missing 'pipes': {spec}")
    pipe_list: list[Pipe] = [load_pipe(p) for p in spec["pipes"]]
    return PipelineCls(pipes=pipe_list)


def load_pipe(spec: dict[str, Any]) -> Pipe:
    """Recursively build a single pipe from a JSON-like dict."""
    pipe_type = spec.get("type")
    if pipe_type is None:
        raise ValueError(f"Pipe spec missing 'type': {spec}")

    if pipe_type == "pipeline":
        return _load_pipeline_from_dict(spec)

    # Registered pipes
    entry = _REGISTRY.get(pipe_type)
    if entry is None:
        raise ValueError(
            f"Unknown pipe type {pipe_type!r}. "
            f"Registered: {', '.join(sorted(_REGISTRY))}"
        )

    config_cls, pipe_cls = entry
    raw_config = spec.get("config") or {}
    config = config_cls.model_validate(raw_config)
    return pipe_cls(config)


def load_pipeline(source: dict[str, Any] | str | Path) -> Pipeline:
    """Build a ``Pipeline`` from a JSON dict, JSON string, or file path."""
    if isinstance(source, Path):
        source = json.loads(source.read_text())
    elif isinstance(source, str):
        stripped = source.lstrip()
        if stripped.startswith("{") or stripped.startswith("["):
            source = json.loads(source)
        else:
            source = json.loads(Path(source).read_text())

    return _load_pipeline_from_dict(source)


def validate_pipeline_config(config: dict[str, Any]) -> list[str]:
    """Validate a pipeline config dict without instantiating pipes.

    Returns a list of error strings (empty = valid).  Checks that each pipe
    type is registered and that the config parses against the config class.
    Does NOT call pipe constructors, so no models are loaded.
    """
    errors: list[str] = []
    pipes = config.get("pipes")
    if not isinstance(pipes, list):
        return ["pipeline config must have a 'pipes' list"]

    for i, spec in enumerate(pipes):
        if not isinstance(spec, dict):
            errors.append(f"pipe[{i}]: expected a dict, got {type(spec).__name__}")
            continue
        pipe_type = spec.get("type")
        if not pipe_type:
            errors.append(f"pipe[{i}]: missing 'type'")
            continue
        if pipe_type == "pipeline":
            sub_errors = validate_pipeline_config(spec)
            errors.extend(f"pipe[{i}].{e}" for e in sub_errors)
            continue
        entry = _REGISTRY.get(pipe_type)
        if entry is None:
            catalog_entry = get_catalog_entry(pipe_type)
            if catalog_entry is not None:
                errors.append(
                    f"pipe[{i}] ({pipe_type!r}): not installed — "
                    f"run: {catalog_entry.install_hint}"
                )
            else:
                errors.append(
                    f"pipe[{i}] ({pipe_type!r}): unknown pipe type. "
                    f"Registered: {', '.join(sorted(_REGISTRY))}"
                )
            continue
        config_cls, _ = entry
        raw_config = spec.get("config") or {}
        try:
            config_cls.model_validate(raw_config)
        except Exception as exc:
            errors.append(f"pipe[{i}] ({pipe_type!r}) config error: {exc}")

    return errors


# ---------------------------------------------------------------------------
# Dump
# ---------------------------------------------------------------------------

def _dump_pipeline_steps(pipeline: Pipeline) -> dict[str, Any]:
    """Shared helper: serialize a pipeline's steps into a dict."""
    out: dict[str, Any] = {"pipes": []}
    for p in pipeline.pipes:
        out["pipes"].append(dump_pipe(p))
    return out


def dump_pipe(pipe: Pipe) -> dict[str, Any]:
    """Serialize a single pipe to a JSON-compatible dict."""
    from pypedeid.pipes.combinators import Pipeline

    if isinstance(pipe, Pipeline):
        out = _dump_pipeline_steps(pipe)
        out["type"] = "pipeline"
        return out

    # Registered pipes — reverse lookup by class
    for name, (config_cls, pipe_cls) in _REGISTRY.items():
        if isinstance(pipe, pipe_cls):
            if isinstance(pipe, ConfigurablePipe):
                config = pipe.pipe_config
            elif hasattr(pipe, "_config"):
                config = pipe._config  # type: ignore[attr-defined]
            else:
                raise ValueError(
                    f"Cannot serialize pipe {type(pipe).__name__}: "
                    f"not a ConfigurablePipe and has no _config attribute"
                )
            dumped = config.model_dump()
            # Omit fields that match defaults to keep JSON concise
            defaults = {}
            for field_name, field_info in config_cls.model_fields.items():
                if field_info.is_required():
                    continue
                default = field_info.get_default(call_default_factory=True)
                defaults[field_name] = default
            trimmed = {
                k: v for k, v in dumped.items() if k not in defaults or v != defaults[k]
            }
            result = {"type": name}
            if trimmed:
                result["config"] = trimmed
            return result

    raise ValueError(f"Cannot serialize pipe {type(pipe).__name__}: not in registry")


def dump_pipeline(pipeline: Pipeline) -> dict[str, Any]:
    """Serialize a ``Pipeline`` to a JSON-compatible dict (top-level, no ``type`` key)."""
    return _dump_pipeline_steps(pipeline)


def dump_pipeline_json(pipeline: Pipeline, indent: int = 2) -> str:
    """Serialize a ``Pipeline`` to a JSON string."""
    return json.dumps(dump_pipeline(pipeline), indent=indent)


def save_pipeline(pipeline: Pipeline, path: str | Path) -> None:
    """Write a ``Pipeline`` to a JSON file."""
    Path(path).write_text(dump_pipeline_json(pipeline) + "\n")


# ---------------------------------------------------------------------------
# Register built-in pipes
# ---------------------------------------------------------------------------

def _register_builtins() -> None:
    """Register all built-in pipes from the catalog.

    Pipes whose optional dependencies are not installed are silently skipped.
    Always-available pipes (``extra is None``) re-raise on ``ImportError``.
    """
    for entry in _CATALOG:
        try:
            config_cls = _import_dotted(entry.config_path)
            pipe_cls = _import_dotted(entry.pipe_path)
            register(entry.name, config_cls, pipe_cls)
        except ImportError:
            if entry.extra is None:
                raise  # always-available pipes must not fail silently


_register_builtins()
