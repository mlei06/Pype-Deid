"""Blacklist: drop spans that match a benign / safe-term vocabulary (false-positive filter)."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from pypedeid.domain import AnnotatedDocument, EntitySpan
from pypedeid.pipes.base import ConfigurablePipe
from pypedeid.pipes.ui_schema import field_ui
from pypedeid.pipes.whitelist.lists import parse_list_file

logger = logging.getLogger(__name__)

_WORD = re.compile(r"\w+", re.UNICODE)


class BlacklistDictConfig(BaseModel):
    """Dictionary and term settings for the blacklist pipe."""

    disabled_dictionaries: list[str] = Field(default_factory=list)
    terms: list[str] = Field(default_factory=list)


class BlacklistSpansConfig(BaseModel):
    """Spans are removed when they match the blacklist policy (see *match*)."""

    dict_config: BlacklistDictConfig = Field(
        default_factory=BlacklistDictConfig,
        title="Dictionaries & Safe Terms",
        description="Toggle dictionaries, upload new ones, and add inline safe terms.",
        json_schema_extra=field_ui(
            ui_group="Terms",
            ui_order=1,
            ui_widget="blacklist_dicts",
        ),
    )

    match: Literal[
        "any_token",
        "whole_span",
        "substring",
        "overlap_document",
    ] = Field(
        default="any_token",
        description="How span text is compared against the blacklist.",
        json_schema_extra=field_ui(
            ui_group="Matching",
            ui_order=2,
            ui_widget="described_select",
            ui_enum_descriptions={
                "any_token": (
                    "Drop the span if any single word token in it "
                    "matches a blacklist term."
                ),
                "whole_span": (
                    "Drop only if the full span text (whitespace-normalized) "
                    "matches a blacklist entry exactly."
                ),
                "substring": (
                    "Drop if any blacklist term appears as a substring "
                    "within the span text."
                ),
                "overlap_document": (
                    "Scan the full document for blacklist regions "
                    "(literal terms + regex patterns) and drop any span "
                    "that overlaps a matched region."
                ),
            },
        ),
    )

    @field_validator("match", mode="before")
    @classmethod
    def _migrate_exact_span(cls, v: str) -> str:
        """exact_span was identical to whole_span; accept it for backward compat."""
        if v == "exact_span":
            return "whole_span"
        return v

    apply_to_labels: list[str] | None = Field(
        default=None,
        json_schema_extra=field_ui(
            ui_group="Scope",
            ui_order=3,
            ui_widget="multiselect",
            ui_help="If set, only these span labels are filtered; others pass through.",
            ui_advanced=True,
        ),
    )

    regex_blacklist_patterns: list[str] = Field(
        default_factory=list,
        description="Extra regex patterns for overlap_document mode.",
        json_schema_extra=field_ui(
            ui_group="Matching",
            ui_order=4,
            ui_widget="regex",
            ui_advanced=True,
        ),
    )

    extra_wordlist_paths: list[str] = Field(
        default_factory=list,
        json_schema_extra=field_ui(ui_advanced=True, ui_order=999),
    )

    # ------------------------------------------------------------------
    # Deprecated fields — backward compatibility with saved configs
    # ------------------------------------------------------------------
    terms: list[str] = Field(
        default_factory=list,
        exclude=True,
        json_schema_extra=field_ui(ui_advanced=True, ui_order=999),
    )
    dictionaries: list[str] = Field(
        default_factory=list,
        exclude=True,
        json_schema_extra=field_ui(ui_advanced=True, ui_order=999),
    )
    load_all_dictionaries: bool = Field(
        default=True,
        exclude=True,
        json_schema_extra=field_ui(ui_advanced=True, ui_order=999),
    )

    @property
    def _effective_terms(self) -> list[str]:
        """Merge dict_config.terms with deprecated top-level terms."""
        seen: set[str] = set()
        merged: list[str] = []
        for t in [*self.dict_config.terms, *self.terms]:
            u = t.strip().upper()
            if u and u not in seen:
                seen.add(u)
                merged.append(t.strip())
        return merged

    @property
    def _effective_disabled(self) -> set[str]:
        return set(self.dict_config.disabled_dictionaries)


def _get_dictionary_store():
    """Lazy import to avoid circular deps and allow tests to override settings."""
    from pypedeid.config import get_settings
    from pypedeid.dictionary_store import DictionaryStore

    return DictionaryStore(get_settings().dictionaries_dir)


def _auto_discover_blacklist_terms() -> set[str]:
    """Load all blacklist dictionaries from the store."""
    try:
        store = _get_dictionary_store()
        dicts = store.list_dictionaries(kind="blacklist")
    except Exception:
        return set()
    terms: set[str] = set()
    for d in dicts:
        try:
            for t in store.get_terms("blacklist", d.name):
                u = t.strip().upper()
                if u:
                    terms.add(u)
        except FileNotFoundError:
            continue
    return terms


def _load_named_dictionaries(names: list[str]) -> set[str]:
    """Load terms from explicitly named blacklist dictionaries."""
    if not names:
        return set()
    try:
        store = _get_dictionary_store()
        terms = store.load_blacklist_terms(names)
        return {t.strip().upper() for t in terms if t.strip()}
    except Exception:
        return set()


def _load_path_terms(path: Path) -> set[str]:
    raw = path.read_text(encoding="utf-8")
    return {t.upper() for t in parse_list_file(raw, filename=path.name) if t}


def _build_blacklist_set(config: BlacklistSpansConfig) -> frozenset[str]:
    s: set[str] = set()
    for t in config._effective_terms:
        u = t.strip().upper()
        if u:
            s.add(u)
    disabled = config._effective_disabled
    try:
        store = _get_dictionary_store()
        dicts = store.list_dictionaries(kind="blacklist")
    except Exception:
        dicts = []
    for d in dicts:
        if d.name in disabled:
            continue
        try:
            for t in store.get_terms("blacklist", d.name):
                u = t.strip().upper()
                if u:
                    s.add(u)
        except FileNotFoundError:
            continue
    for raw in config.extra_wordlist_paths:
        p = Path(raw).expanduser()
        if p.is_file():
            s |= _load_path_terms(p)
    return frozenset(s)


def _merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not intervals:
        return []
    intervals = sorted(intervals)
    out: list[tuple[int, int]] = [intervals[0]]
    for s, e in intervals[1:]:
        ps, pe = out[-1]
        if s <= pe:
            out[-1] = (ps, max(pe, e))
        else:
            out.append((s, e))
    return out


def blacklist_regions_for_terms(text: str, terms: frozenset[str]) -> list[tuple[int, int]]:
    """Intervals where literal blacklist *terms* match (``overlap_document`` mode)."""
    return blacklist_regions_for_text(text, terms, ())


def blacklist_regions_for_text(
    text: str,
    terms: frozenset[str],
    regex_patterns: tuple[str, ...] = (),
) -> list[tuple[int, int]]:
    """Merged blacklist regions from literal *terms* and optional *regex_patterns*."""
    raw: list[tuple[int, int]] = []
    for term in terms:
        t = term.strip()
        if not t:
            continue
        if re.search(r"\s", t):
            parts = [p for p in re.split(r"\s+", t) if p]
            if not parts:
                continue
            pat = re.compile(r"\s+".join(re.escape(p) for p in parts), re.IGNORECASE)
        else:
            pat = re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE)
        for m in pat.finditer(text):
            raw.append((m.start(), m.end()))
    for p in regex_patterns:
        ps = p.strip()
        if not ps:
            continue
        try:
            rx = re.compile(ps, re.IGNORECASE)
        except re.error:
            logger.warning("Skipping invalid blacklist regex pattern: %s", ps)
            continue
        for m in rx.finditer(text):
            raw.append((m.start(), m.end()))
    return _merge_intervals(raw)


def _interval_overlaps_regions(s: int, e: int, regions: list[tuple[int, int]]) -> bool:
    """Check if [s, e) overlaps any region using binary search.

    Requires *regions* to be sorted and merged (as produced by ``_merge_intervals``).
    """
    import bisect

    if not regions:
        return False
    # Find the first region whose start is >= e; check it and the one before.
    idx = bisect.bisect_left(regions, (e,))
    # Check the region at idx-1 (the last one starting before e).
    if idx > 0:
        a, b = regions[idx - 1]
        if a < e and s < b:
            return True
    # Also check at idx in case of exact boundary match.
    if idx < len(regions):
        a, b = regions[idx]
        if a < e and s < b:
            return True
    return False


class BlacklistSpans(ConfigurablePipe):
    """Span transformer: remove spans that hit the blacklist (benign vocabulary)."""

    def __init__(self, config: BlacklistSpansConfig | None = None) -> None:
        self._config = config or BlacklistSpansConfig()
        self._blacklist = _build_blacklist_set(self._config)
        self._regex_patterns = tuple(self._config.regex_blacklist_patterns)
        self._label_filter: frozenset[str] | None = (
            frozenset(self._config.apply_to_labels) if self._config.apply_to_labels else None
        )

    def forward(self, doc: AnnotatedDocument) -> AnnotatedDocument:
        text = doc.document.text
        regions: list[tuple[int, int]] | None = None
        if self._config.match == "overlap_document" and (self._blacklist or self._regex_patterns):
            regions = blacklist_regions_for_text(text, self._blacklist, self._regex_patterns)

        out: list[EntitySpan] = []
        for span in doc.spans:
            if self._label_filter is not None and span.label not in self._label_filter:
                out.append(span)
                continue
            if self._should_drop(text, span, regions):
                continue
            out.append(span)
        return doc.with_spans(out)

    def _should_drop(
        self,
        text: str,
        span: EntitySpan,
        regions: list[tuple[int, int]] | None,
    ) -> bool:
        start, end = span.start, span.end
        if start < 0 or end > len(text) or start >= end:
            return False
        mode = self._config.match
        if mode == "overlap_document":
            if not regions:
                return False
            return _interval_overlaps_regions(start, end, regions)

        if not self._blacklist:
            return False
        snippet = text[start:end]
        if mode == "whole_span":
            key = " ".join(snippet.split()).upper()
            return key in self._blacklist
        if mode == "substring":
            low = snippet.casefold()
            for term in self._blacklist:
                if len(term) >= 1 and term.casefold() in low:
                    return True
            return False
        for m in _WORD.finditer(snippet):
            if m.group().upper() in self._blacklist:
                return True
        return False
