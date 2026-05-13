"""Whitelist: phrase / dictionary PHI detection via inline terms and dictionary store."""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, ConfigDict, Field

from pypedeid.domain import AnnotatedDocument, EntitySpan
from pypedeid.pipes.base import ConfigurablePipe
from pypedeid.pipes.detector_label_mapping import (
    accumulate_spans,
    apply_detector_label_mapping,
    effective_detector_labels,
)
from pypedeid.pipes.ui_schema import field_ui
from pypedeid.pipes.whitelist.lists import term_to_list_pattern


class WhitelistLabelSettings(BaseModel):
    """Per-label settings for the whitelist detector."""

    model_config = ConfigDict(extra="ignore")  # ignore legacy keys e.g. disabled_dictionaries in old JSON

    enabled: bool = True
    remap: str | None = None
    terms: list[str] = Field(default_factory=list)
    # Named dictionary stems from the global whitelist pool (per-label opt-in)
    dictionaries: list[str] = Field(default_factory=list)


# Backward-compat alias — old configs used WhitelistLabelConfig
WhitelistLabelConfig = WhitelistLabelSettings


class WhitelistConfig(BaseModel):
    """Configuration for :class:`WhitelistPipe`."""

    model_config = ConfigDict(
        json_schema_extra={
            "description": (
                "Per-label phrase lists (whitelist gazetteer). "
                "Chain with ``regex_ner`` for combined coverage."
            )
        }
    )

    source_name: str = Field(
        default="whitelist",
        json_schema_extra=field_ui(
            ui_group="General",
            ui_order=1,
            ui_widget="text",
            ui_advanced=True,
        ),
    )

    labels: dict[str, WhitelistLabelSettings] = Field(
        default_factory=dict,
        title="Labels",
        description=(
            "Configure each detection label: toggle on/off, "
            "select dictionaries from the pool, add inline terms, and remap output labels."
        ),
        json_schema_extra=field_ui(
            ui_group="Labels",
            ui_order=2,
            ui_widget="whitelist_label",
            ui_allow_custom_labels=True,
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

    # ------------------------------------------------------------------
    # Deprecated fields kept for backward compatibility with saved configs
    # ------------------------------------------------------------------
    per_label: dict[str, WhitelistLabelSettings] = Field(
        default_factory=dict,
        exclude=True,
        json_schema_extra=field_ui(ui_advanced=True, ui_order=999),
    )
    label_mapping: dict[str, str | None] = Field(
        default_factory=dict,
        exclude=True,
        json_schema_extra=field_ui(ui_advanced=True, ui_order=999),
    )

    @property
    def _merged_labels(self) -> dict[str, WhitelistLabelSettings]:
        """Merge old per_label/label_mapping into the new labels dict."""
        merged: dict[str, WhitelistLabelSettings] = {k: v for k, v in self.labels.items()}

        for label, old_cfg in self.per_label.items():
            if label not in merged:
                merged[label] = old_cfg
            else:
                existing = merged[label]
                merged[label] = WhitelistLabelSettings(
                    enabled=existing.enabled,
                    remap=existing.remap,
                    terms=sorted({*existing.terms, *old_cfg.terms}),
                    dictionaries=sorted({*existing.dictionaries, *old_cfg.dictionaries}),
                )

        for label, target in self.label_mapping.items():
            if label in merged:
                s = merged[label]
                if target is None:
                    merged[label] = WhitelistLabelSettings(
                        enabled=False, remap=s.remap, terms=s.terms, dictionaries=s.dictionaries,
                    )
                elif not s.remap:
                    merged[label] = WhitelistLabelSettings(
                        enabled=s.enabled, remap=target, terms=s.terms, dictionaries=s.dictionaries,
                    )

        return merged

    @property
    def effective_label_mapping(self) -> dict[str, str | None]:
        """Derived label mapping from the labels dict."""
        mapping: dict[str, str | None] = {}
        for label, s in self._merged_labels.items():
            if not s.enabled:
                mapping[label] = None
            elif s.remap:
                mapping[label] = s.remap
        return mapping


def default_base_labels() -> list[str]:
    """Whitelist does not infer labels from on-disk dictionary layout."""
    return []


class _ResolvedList:
    __slots__ = ("label", "terms")

    def __init__(self, label: str, terms: list[str]) -> None:
        self.label = label
        self.terms = terms


def _get_dictionary_store():
    """Lazy import to avoid circular deps and allow tests to override settings."""
    from pypedeid.config import get_settings
    from pypedeid.dictionary_store import DictionaryStore

    return DictionaryStore(get_settings().dictionaries_dir)


logger = logging.getLogger(__name__)


def _resolve_list_labels(config: WhitelistConfig) -> list[_ResolvedList]:
    merged = config._merged_labels
    try:
        store = _get_dictionary_store()
    except Exception:
        logger.warning("Failed to load dictionary store for whitelist", exc_info=True)
        store = None

    def _get_terms(name: str) -> list[str]:
        if store is None:
            return []
        try:
            return store.get_terms("whitelist", name)
        except FileNotFoundError:
            logger.warning("Whitelist dictionary not found: %r", name)
            return []
        except Exception:
            logger.warning("Failed to read whitelist dictionary %r", name, exc_info=True)
            return []

    label_keys: set[str] = set(merged.keys())
    resolved: list[_ResolvedList] = []
    for label in sorted(label_keys):
        settings = merged[label]
        if not settings.enabled:
            continue
        terms: list[str] = []
        for dict_name in settings.dictionaries:
            if dict_name.strip():
                terms.extend(_get_terms(dict_name.strip()))
        terms.extend(settings.terms)

        seen: set[str] = set()
        uniq: list[str] = []
        for t in terms:
            k = t.casefold()
            if t.strip() and k not in seen:
                seen.add(k)
                uniq.append(t.strip())

        if not uniq:
            continue
        resolved.append(_ResolvedList(label, uniq))
    return resolved


class WhitelistPipe(ConfigurablePipe):
    """Detector: whitelist phrase matching only."""

    def __init__(self, config: WhitelistConfig | None = None) -> None:
        self._config = config or WhitelistConfig()
        self._resolved = _resolve_list_labels(self._config)
        self._list_patterns: list[tuple[str, re.Pattern[str]]] = []
        for r in self._resolved:
            for term in r.terms:
                self._list_patterns.append((r.label, term_to_list_pattern(term)))

    @property
    def base_labels(self) -> set[str]:
        return {r.label for r in self._resolved}

    @property
    def label_mapping(self) -> dict[str, str | None]:
        return dict(self._config.effective_label_mapping)

    @property
    def labels(self) -> set[str]:
        return effective_detector_labels(self.base_labels, self._config.effective_label_mapping)

    def forward(self, doc: AnnotatedDocument) -> AnnotatedDocument:
        text = doc.document.text
        found: list[EntitySpan] = []
        seen: set[tuple[int, int, str]] = set()
        for label, rx in self._list_patterns:
            for m in rx.finditer(text):
                key = (m.start(), m.end(), label)
                if key not in seen:
                    seen.add(key)
                    found.append(
                        EntitySpan(
                            start=m.start(),
                            end=m.end(),
                            label=label,
                            confidence=1.0,
                            source=self._config.source_name,
                        )
                    )
        found.sort(key=lambda s: (s.start, s.end, s.label))
        found = apply_detector_label_mapping(found, self._config.effective_label_mapping)
        return accumulate_spans(doc, found, skip_overlapping=self._config.skip_overlapping)
