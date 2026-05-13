"""Filesystem-backed dictionary store for whitelist and blacklist term lists.

Layout::

    dictionaries/
      whitelist/
        ontario_hospitals.txt
        us_cities.csv
        label_disambig__foo.txt
      blacklist/
        clinical_terms.txt
        custom_safe_words.txt

Whitelist and blacklist dictionaries are each a flat set of files (unique stem
per file). Whitelist files are not organized by NER label; pipeline configs
assign named dictionaries to labels.

Pipeline configs reference dictionaries by name (stem, without extension) and
the store resolves them to file paths.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pypedeid.pipes.whitelist.lists import parse_list_file

DictKind = Literal["whitelist", "blacklist"]

_SAFE_DICT_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def _validate_dict_name(name: str) -> None:
    """Reject dictionary names that could escape the whitelist/blacklist parent."""
    if not _SAFE_DICT_NAME.match(name) or ".." in name:
        raise ValueError(
            f"Invalid dictionary name {name!r}: must match {_SAFE_DICT_NAME.pattern} "
            f"and not contain '..'"
        )


@dataclass(frozen=True)
class DictionaryInfo:
    """Metadata for a stored dictionary file."""

    kind: DictKind
    label: str | None  # always None (reserved; blacklist has no label)
    name: str  # file stem
    filename: str  # full filename with extension
    term_count: int


class DictionaryStore:
    """CRUD operations on the ``dictionaries/`` folder."""

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    # -- paths ---------------------------------------------------------------

    def _whitelist_dir(self) -> Path:
        return self._root / "whitelist"

    def _blacklist_dir(self) -> Path:
        return self._root / "blacklist"

    def _resolve_path(self, kind: DictKind, name: str) -> Path | None:
        """Find a dictionary file by name (stem). Returns None if not found."""
        self._flatten_legacy_subdirs(kind)
        if kind == "whitelist":
            parent = self._whitelist_dir()
        else:
            parent = self._blacklist_dir()
        if not parent.is_dir():
            return None
        for p in parent.iterdir():
            if p.is_file() and p.stem == name:
                return p
        return None

    # -- list ----------------------------------------------------------------

    def list_dictionaries(
        self,
        kind: DictKind | None = None,
        label: str | None = None,
    ) -> list[DictionaryInfo]:
        """List stored dictionaries, optionally filtered by kind.

        The ``label`` filter is accepted for API compatibility; it is ignored
        (whitelist is not keyed by label on disk).
        """
        _ = label  # legacy query param, no longer used
        results: list[DictionaryInfo] = []
        if kind is None or kind == "whitelist":
            results.extend(self._list_whitelist())
        if kind is None or kind == "blacklist":
            results.extend(self._list_blacklist())
        return results

    def _list_whitelist(self) -> list[DictionaryInfo]:
        self._flatten_legacy_subdirs("whitelist")
        wl = self._whitelist_dir()
        if not wl.is_dir():
            return []
        out: list[DictionaryInfo] = []
        for path in sorted(wl.iterdir()):
            if path.is_file() and path.suffix in (".txt", ".csv", ".json"):
                terms = self._load_terms(path)
                out.append(DictionaryInfo(
                    kind="whitelist",
                    label=None,
                    name=path.stem,
                    filename=path.name,
                    term_count=len(terms),
                ))
        return out

    def _list_blacklist(self) -> list[DictionaryInfo]:
        self._flatten_legacy_subdirs("blacklist")
        bl_root = self._blacklist_dir()
        if not bl_root.is_dir():
            return []
        out: list[DictionaryInfo] = []
        for path in sorted(bl_root.iterdir()):
            if path.is_file() and path.suffix in (".txt", ".csv", ".json"):
                terms = self._load_terms(path)
                out.append(DictionaryInfo(
                    kind="blacklist",
                    label=None,
                    name=path.stem,
                    filename=path.name,
                    term_count=len(terms),
                ))
        return out

    # -- get terms -----------------------------------------------------------

    def get_terms(self, kind: DictKind, name: str, label: str | None = None) -> list[str]:
        """Load and return parsed terms from a dictionary by name.

        The ``label`` parameter is accepted for API compatibility; it is
        ignored. Raises ``FileNotFoundError`` if the dictionary does not exist.
        """
        _ = label
        path = self._resolve_path(kind, name)
        if path is None:
            loc = f"{kind}/{name}"
            raise FileNotFoundError(f"dictionary not found: {loc}")
        return self._load_terms(path)

    # -- save ----------------------------------------------------------------

    def save(
        self,
        kind: DictKind,
        name: str,
        content: str,
        label: str | None = None,
        extension: str = ".txt",
    ) -> DictionaryInfo:
        """Write a dictionary file. Overwrites if it already exists.

        The ``label`` parameter is accepted for API compatibility; it is
        ignored for whitelist (dictionaries are flat).
        """
        _ = label
        _validate_dict_name(name)
        if kind == "whitelist":
            parent = self._whitelist_dir()
        else:
            parent = self._blacklist_dir()
        self._flatten_legacy_subdirs(kind)
        parent.mkdir(parents=True, exist_ok=True)

        for existing in parent.iterdir():
            if existing.is_file() and existing.stem == name:
                existing.unlink()

        ext = extension if extension.startswith(".") else f".{extension}"
        path = parent / f"{name}{ext}"
        path.write_text(content, encoding="utf-8")

        terms = self._load_terms(path)
        return DictionaryInfo(
            kind=kind,
            label=None,
            name=name,
            filename=path.name,
            term_count=len(terms),
        )

    # -- delete --------------------------------------------------------------

    def delete(self, kind: DictKind, name: str, label: str | None = None) -> None:
        """Remove a dictionary file. Raises ``FileNotFoundError`` if missing."""
        _ = label
        path = self._resolve_path(kind, name)
        if path is None:
            loc = f"{kind}/{name}"
            raise FileNotFoundError(f"dictionary not found: {loc}")
        path.unlink()

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _load_terms(path: Path) -> list[str]:
        text = path.read_text(encoding="utf-8")
        return parse_list_file(text, filename=path.name)

    def _flatten_legacy_subdirs(self, kind: DictKind) -> None:
        """Move one-level nested dictionary files into the flat kind directory.

        Legacy layout used kind/label/name.ext for whitelist and, in some setups,
        for blacklist as well. The current contract is flat kind directories for
        both. We transparently migrate on access.
        """
        root = self._whitelist_dir() if kind == "whitelist" else self._blacklist_dir()
        if not root.is_dir():
            return
        allowed = {".txt", ".csv", ".json"}
        for sub in root.iterdir():
            if not sub.is_dir():
                continue
            for path in sub.iterdir():
                if not path.is_file() or path.suffix not in allowed:
                    continue
                target = root / path.name
                if target.exists():
                    # Keep deterministic and avoid overwrite; suffix with legacy folder.
                    target = root / f"{path.stem}__{sub.name}{path.suffix}"
                path.replace(target)
            try:
                sub.rmdir()
            except OSError:
                # Non-empty (unexpected artifacts); leave it for manual cleanup.
                pass

    # -- preview / paginated browse ------------------------------------------

    def get_preview(
        self,
        kind: DictKind,
        name: str,
        label: str | None = None,
        sample_size: int = 20,
    ) -> dict:
        """Return metadata and a sample of terms for a dictionary."""
        _ = label
        path = self._resolve_path(kind, name)
        if path is None:
            loc = f"{kind}/{name}"
            raise FileNotFoundError(f"dictionary not found: {loc}")
        terms = self._load_terms(path)
        return {
            "kind": kind,
            "label": None,
            "name": name,
            "term_count": len(terms),
            "sample_terms": terms[:sample_size],
            "file_size_bytes": path.stat().st_size,
        }

    def get_terms_paginated(
        self,
        kind: DictKind,
        name: str,
        label: str | None = None,
        offset: int = 0,
        limit: int = 50,
        search: str | None = None,
    ) -> dict:
        """Return a page of terms with optional text filter."""
        _ = label
        path = self._resolve_path(kind, name)
        if path is None:
            loc = f"{kind}/{name}"
            raise FileNotFoundError(f"dictionary not found: {loc}")
        terms = self._load_terms(path)
        if search:
            needle = search.casefold()
            terms = [t for t in terms if needle in t.casefold()]
        total = len(terms)
        page = terms[offset : offset + limit]
        return {
            "terms": page,
            "total": total,
            "offset": offset,
            "limit": limit,
            "search": search,
        }

    # -- bulk load for pipes -------------------------------------------------

    def load_whitelist_terms(self, names: list[str]) -> list[str]:
        """Load and merge terms from multiple whitelist dictionaries by name."""
        all_terms: list[str] = []
        for name in names:
            all_terms.extend(self.get_terms("whitelist", name))
        return all_terms

    def load_blacklist_terms(self, names: list[str]) -> list[str]:
        """Load and merge terms from multiple blacklist dictionaries."""
        all_terms: list[str] = []
        for name in names:
            all_terms.extend(self.get_terms("blacklist", name))
        return all_terms
