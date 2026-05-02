"""Hugging Face NER detector pipe.

Loads a token-classification model from ``models/huggingface/{name}/`` (registered
via ``model_manifest.json``) and produces ``EntitySpan``s.  Device is selected at
runtime — CUDA when available, else CPU — so the pipeline JSON stays portable
across machines.  Segmentation defaults to whatever the model was trained with
(``training.segmentation`` in the manifest), so inference matches training context
without manual configuration.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from clinical_deid.domain import AnnotatedDocument, EntitySpan
from clinical_deid.pipes.base import ConfigurablePipe
from clinical_deid.pipes.detector_label_mapping import (
    accumulate_spans,
    apply_detector_label_mapping,
    detector_label_mapping_field,
    effective_detector_labels,
)
from clinical_deid.pipes.span_merge import reconcile_overlapping_spans
from clinical_deid.pipes.ui_schema import field_ui

logger = logging.getLogger(__name__)


# Trained clinical models already emit canonical PHI labels (NAME, DATE, …),
# so the default entity_map is empty — keys pass through unchanged.  Users can
# still add overrides via config.entity_map if a model uses non-canonical tags.
DEFAULT_ENTITY_MAP: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Catalog helpers
# ---------------------------------------------------------------------------


def list_huggingface_model_names() -> list[str]:
    """Names of models under ``models/huggingface/`` (drives the model-select dropdown)."""
    from clinical_deid.config import get_settings
    from clinical_deid.models import list_models

    return [info.name for info in list_models(get_settings().models_dir, framework="huggingface")]


def default_base_labels() -> list[str]:
    """Empty by default — labels come from the selected model's manifest."""
    return []


def _read_max_position_embeddings(model_path: Path) -> int | None:
    """Read the model's architectural context window from ``config.json``.

    Cheap (one ~5KB JSON read) and only happens when the bundle endpoint is hit,
    so we avoid loading the model just to display this in the UI.
    """
    config_path = model_path / "config.json"
    if not config_path.is_file():
        return None
    try:
        import json
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    val = raw.get("max_position_embeddings")
    return int(val) if isinstance(val, int) else None


def build_huggingface_label_space_bundle() -> dict[str, Any]:
    """Bundle payload powering the label-mapping widget.

    ``labels_by_model`` is keyed by model name and lists the canonical PHI labels
    declared in each model's ``model_manifest.json`` (raw NER tags, before
    ``entity_map`` projection).  ``default_model`` is the first registered HF
    model so the UI has a sensible fallback when a fresh pipe is added.

    ``model_info`` carries display-only training metadata (trained max sequence
    length, architectural context window, segmentation, base model, training
    document count) so the config panel can show what each model can handle
    without forcing the user to inspect the manifest.
    """
    from clinical_deid.config import get_settings
    from clinical_deid.models import list_models

    labels_by_model: dict[str, list[str]] = {}
    model_info: dict[str, dict[str, Any]] = {}
    default_model = ""
    for info in list_models(get_settings().models_dir, framework="huggingface"):
        labels_by_model[info.name] = sorted(info.labels)
        if not default_model:
            default_model = info.name

        hyperparams = (info.training_config or {}).get("hyperparams") or {}
        meta = info.training_meta or {}
        model_info[info.name] = {
            "trained_max_length": hyperparams.get("max_length"),
            "max_position_embeddings": _read_max_position_embeddings(info.path),
            "segmentation": meta.get("segmentation"),
            "base_model": info.base_model,
            "train_documents": meta.get("train_documents"),
            "trained_at": meta.get("trained_at"),
        }
    return {
        "labels_by_model": labels_by_model,
        "default_entity_map": dict(DEFAULT_ENTITY_MAP),
        "default_model": default_model,
        "model_info": model_info,
    }


def huggingface_ner_dependencies(config: dict[str, Any]) -> list[str]:
    """Flag a missing model in the configured pipeline so deploy health can warn."""
    from clinical_deid.config import get_settings
    from clinical_deid.models import get_model

    model_name = (config or {}).get("model")
    if not model_name:
        return []
    try:
        info = get_model(get_settings().models_dir, model_name)
    except Exception:
        return [f"model:{model_name}"]
    if info.framework != "huggingface":
        return [f"model:{model_name}"]
    return []


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


SegmentationMode = Literal["auto", "truncate", "sentence", "chunk"]

# Sliding-window stride for ``chunk`` mode. Must be larger than the longest
# expected entity (HIPAA addresses run ~6-8 tokens) so an entity straddling a
# window boundary is fully visible inside the next window.
CHUNK_STRIDE_TOKENS = 64


class HuggingfaceNerConfig(BaseModel):
    """Configuration for :class:`HuggingfaceNerPipe`.

    Device is intentionally not exposed — it is picked at runtime (CUDA when
    available, else CPU).  Segmentation defaults to ``auto``, which uses the
    mode the model was trained with (recorded in ``model_manifest.json``).
    """

    model_config = ConfigDict(protected_namespaces=(), extra="ignore")

    model: str = Field(
        ...,
        title="Model",
        description="Name of a model directory under ``models/huggingface/``.",
        json_schema_extra=field_ui(
            ui_group="Model",
            ui_order=1,
            ui_widget="select",
            ui_help="Choose a trained Hugging Face model registered under models/huggingface/",
            ui_options_source="huggingface_models",
        ),
    )

    segmentation: SegmentationMode = Field(
        default="auto",
        title="Segmentation",
        description=(
            "How to segment input. ``auto`` uses ``sentence`` if the model was trained "
            "that way, otherwise ``chunk`` so no token is dropped. ``chunk`` slides a "
            "window across the document with overlap and stitches predictions back "
            "together. ``sentence`` runs inference per sentence. ``truncate`` runs one "
            "pass and silently drops anything past the model's context window."
        ),
        json_schema_extra=field_ui(
            ui_group="Detection",
            ui_order=2,
            ui_widget="select",
        ),
    )

    entity_map: dict[str, str] = Field(
        default_factory=lambda: dict(DEFAULT_ENTITY_MAP),
        description=(
            "Map raw model labels to project PHI labels. Trained clinical models "
            "usually emit canonical labels already — leave this empty unless you need overrides."
        ),
        json_schema_extra=field_ui(
            ui_group="Output labels",
            ui_order=1,
            ui_widget="key_value",
            ui_advanced=True,
        ),
    )

    label_mapping: dict[str, str | None] = detector_label_mapping_field()

    source_name: str = Field(
        default="huggingface_ner",
        json_schema_extra=field_ui(
            ui_group="General",
            ui_widget="text",
            ui_advanced=True,
        ),
    )

    skip_overlapping: bool = Field(
        default=False,
        description="Drop new spans that overlap any existing span in the document.",
        json_schema_extra=field_ui(
            ui_group="General",
            ui_order=99,
            ui_widget="switch",
        ),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_device_index() -> int:
    """Return the Transformers ``device`` index — 0 when CUDA is available, else -1 (CPU)."""
    try:
        import torch
    except ImportError:
        return -1
    try:
        if torch.cuda.is_available():
            return 0
    except Exception:
        return -1
    return -1


def _resolve_segmentation_mode(
    requested: SegmentationMode,
    trained: str | None,
    model_name: str,
) -> str:
    """Resolve effective inference segmentation.

    ``auto`` honors a sentence-trained manifest (``sentence``) but otherwise
    upgrades to ``chunk`` — even ``truncate``-trained or older manifests get
    full-document coverage at inference, since silently dropping PHI past the
    context window is unsafe for de-identification.  An explicit override is
    honored but logs a warning when it diverges from the training-time mode.
    """
    if requested == "auto":
        if trained == "sentence":
            return "sentence"
        return "chunk"
    if trained and trained != requested:
        logger.warning(
            "huggingface_ner: model %r was trained with segmentation=%r but "
            "inference is configured with segmentation=%r. Context at "
            "inference will differ from training.",
            model_name, trained, requested,
        )
    return requested


def _load_pipeline(model_path: Path, device_index: int) -> Any:
    """Build a Transformers token-classification pipeline."""
    try:
        from transformers import (
            AutoConfig,
            AutoTokenizer,
            PreTrainedTokenizerFast,
            pipeline as hf_pipeline,
        )
    except ImportError as exc:
        raise ImportError(
            "transformers is required for huggingface_ner. "
            "Install with: pip install transformers torch"
        ) from exc
    # Some BERT tokenizer configs leave ``model_max_length`` unset (a sentinel
    # like 1e30), which disables auto-truncation in the token-classification
    # pipeline and lets inputs blow past the model's position-embedding window.
    # Pin the tokenizer to the model's actual ``max_position_embeddings``.
    config = AutoConfig.from_pretrained(str(model_path))
    max_len = int(getattr(config, "max_position_embeddings", 512) or 512)
    try:
        tokenizer = AutoTokenizer.from_pretrained(str(model_path), model_max_length=max_len)
    except ValueError as exc:
        # Some models (e.g. saved by transformers 5.x dev builds) write a
        # ``tokenizer_class`` AutoTokenizer can't resolve in this version.
        # Fall back to the fast tokenizer driven by ``tokenizer.json``.
        if not (model_path / "tokenizer.json").exists():
            raise
        logger.warning(
            "huggingface_ner: AutoTokenizer rejected %s (%s); falling back to "
            "PreTrainedTokenizerFast via tokenizer.json. Consider fixing the "
            "model's tokenizer_config.json.",
            model_path.name, exc,
        )
        tokenizer = PreTrainedTokenizerFast.from_pretrained(
            str(model_path), model_max_length=max_len
        )
    return hf_pipeline(
        "token-classification",
        model=str(model_path),
        tokenizer=tokenizer,
        device=device_index,
        aggregation_strategy="simple",
    )


def _predict_truncate(
    hf,
    text: str,
    source: str,
    entity_map: dict[str, str],
) -> list[EntitySpan]:
    """Single forward pass — input is truncated at the model's context window."""
    spans: list[EntitySpan] = []
    for ent in hf(text):
        raw = ent.get("entity_group") or ent.get("entity", "UNK")
        label = entity_map.get(raw, raw)
        spans.append(EntitySpan(
            start=ent["start"],
            end=ent["end"],
            label=label,
            confidence=round(float(ent.get("score", 1.0)), 4),
            source=source,
        ))
    return spans


def _predict_by_chunks(
    hf,
    text: str,
    source: str,
    entity_map: dict[str, str],
    max_tokens: int,
) -> list[EntitySpan]:
    """Sliding-window inference for documents longer than the model context.

    Tokenizes once with offset mapping, slices the text into overlapping
    char-windows whose token counts fit the model's context, runs the
    pipeline on each, and remaps predictions back to document coordinates.
    Duplicate predictions in the overlap region are collapsed downstream
    by :func:`reconcile_overlapping_spans`.
    """
    tokenizer = hf.tokenizer
    encoded = tokenizer(
        text,
        return_offsets_mapping=True,
        add_special_tokens=False,
        truncation=False,
    )
    offsets = list(encoded["offset_mapping"])
    if not offsets:
        return []

    try:
        special_budget = tokenizer.num_special_tokens_to_add(pair=False)
    except Exception:
        special_budget = 2
    # Two-token safety margin guards against the tokenizer producing one or two
    # extra tokens when re-tokenizing the substring (boundary effects).
    window_tokens = max(1, max_tokens - special_budget - 2)
    n = len(offsets)
    step = max(1, window_tokens - CHUNK_STRIDE_TOKENS)

    spans: list[EntitySpan] = []
    start_tok = 0
    while start_tok < n:
        end_tok = min(start_tok + window_tokens, n)
        char_start = offsets[start_tok][0]
        char_end = offsets[end_tok - 1][1]
        sub = text[char_start:char_end]
        if sub:
            for ent in hf(sub):
                raw = ent.get("entity_group") or ent.get("entity", "UNK")
                label = entity_map.get(raw, raw)
                spans.append(EntitySpan(
                    start=ent["start"] + char_start,
                    end=ent["end"] + char_start,
                    label=label,
                    confidence=round(float(ent.get("score", 1.0)), 4),
                    source=source,
                ))
        if end_tok >= n:
            break
        start_tok += step
    return spans


def _predict_by_sentence(
    hf,
    text: str,
    source: str,
    entity_map: dict[str, str],
) -> list[EntitySpan]:
    """Run the pipeline per sentence and remap offsets back to document coords."""
    from clinical_deid.training.segmentation import sentence_offsets

    bounds = sentence_offsets(text)
    if not bounds:
        return []

    spans: list[EntitySpan] = []
    for sent_start, sent_end in bounds:
        sub = text[sent_start:sent_end]
        if not sub:
            continue
        for ent in hf(sub):
            raw = ent.get("entity_group") or ent.get("entity", "UNK")
            label = entity_map.get(raw, raw)
            spans.append(EntitySpan(
                start=ent["start"] + sent_start,
                end=ent["end"] + sent_start,
                label=label,
                confidence=round(float(ent.get("score", 1.0)), 4),
                source=source,
            ))
    return spans


# ---------------------------------------------------------------------------
# Pipe
# ---------------------------------------------------------------------------


class HuggingfaceNerPipe(ConfigurablePipe):
    """Detector backed by a Hugging Face token-classification model."""

    def __init__(self, config: HuggingfaceNerConfig | dict[str, Any]) -> None:
        if isinstance(config, dict):
            config = HuggingfaceNerConfig.model_validate(config)
        self._config = config
        self._pipeline: Any = None
        self._manifest_labels: list[str] = []
        self._segmentation: str = "truncate"
        self._max_tokens: int = 512

    def _resolve_model(self) -> tuple[Path, dict[str, Any]]:
        from clinical_deid.config import get_settings
        from clinical_deid.models import get_model, list_models

        settings = get_settings()
        try:
            info = get_model(settings.models_dir, self._config.model)
        except KeyError as exc:
            hf_names = [
                m.name
                for m in list_models(settings.models_dir, framework="huggingface")
            ]
            avail = ", ".join(sorted(hf_names)) or "(none)"
            hint = ""
            if self._config.model.startswith(("spacy/", "huggingface/")) and "/" in self._config.model:
                hint = (
                    " Presidio model strings (e.g. spacy/… or huggingface/obi/…) belong on the "
                    "presidio_ner pipe; huggingface_ner only accepts names of directories under "
                    "models/huggingface/ with model_manifest.json."
                )
            raise ValueError(
                f"huggingface_ner model {self._config.model!r} is not registered under "
                f"models/huggingface/.{hint} Available: {avail}"
            ) from exc
        if info.framework != "huggingface":
            raise ValueError(
                f"Model {info.name!r} has framework={info.framework!r}; "
                "huggingface_ner requires framework='huggingface'."
            )
        return info.path, {
            "labels": info.labels,
            "trained_segmentation": info.training_meta.get("segmentation"),
        }

    def _ensure_loaded(self) -> None:
        if self._pipeline is not None:
            return
        model_path, manifest = self._resolve_model()
        self._manifest_labels = list(manifest.get("labels") or [])
        self._segmentation = _resolve_segmentation_mode(
            self._config.segmentation,
            manifest.get("trained_segmentation"),
            self._config.model,
        )
        self._pipeline = _load_pipeline(model_path, _resolve_device_index())
        self._max_tokens = int(self._pipeline.tokenizer.model_max_length or 512)

    @property
    def base_labels(self) -> set[str]:
        """Canonical PHI labels the selected model can produce.

        Reads from the model manifest without loading the model — matches
        ``build_huggingface_label_space_bundle`` so the UI stays in sync.
        """
        if self._manifest_labels:
            return {self._config.entity_map.get(lbl, lbl) for lbl in self._manifest_labels}
        try:
            _, manifest = self._resolve_model()
        except Exception:
            return set()
        labels = manifest.get("labels") or []
        return {self._config.entity_map.get(lbl, lbl) for lbl in labels}

    @property
    def label_mapping(self) -> dict[str, str | None]:
        return dict(self._config.label_mapping)

    @property
    def labels(self) -> set[str]:
        return effective_detector_labels(self.base_labels, self._config.label_mapping)

    def forward(self, doc: AnnotatedDocument) -> AnnotatedDocument:
        text = doc.document.text
        if not text.strip():
            return doc

        self._ensure_loaded()
        source = f"{self._config.source_name}:{self._config.model}"

        if self._segmentation == "sentence":
            found = _predict_by_sentence(
                self._pipeline, text, source, self._config.entity_map
            )
        elif self._segmentation == "chunk":
            found = _predict_by_chunks(
                self._pipeline, text, source, self._config.entity_map, self._max_tokens
            )
        else:
            found = _predict_truncate(
                self._pipeline, text, source, self._config.entity_map
            )

        found.sort(key=lambda s: (s.start, s.end, s.label))
        found = apply_detector_label_mapping(found, self._config.label_mapping)
        # Token-classification often splits full names / dates / phone numbers
        # across consecutive entities ("John" + "Smith"). Collapse same-label
        # spans that overlap or are immediately adjacent into one span.
        found = reconcile_overlapping_spans(found)
        return accumulate_spans(doc, found, skip_overlapping=self._config.skip_overlapping)
