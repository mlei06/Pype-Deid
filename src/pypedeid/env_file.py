"""Resolve which ``.env`` file to load (stable paths, not only CWD)."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_repo_root() -> Path | None:
    """Directory containing this project's ``pyproject.toml``, if discoverable.

    Walks up from :mod:`pypedeid` so paths are stable regardless of
    :func:`os.getcwd` (unlike resolving relative paths from the process CWD).
    Returns ``None`` if no ``pyproject.toml`` ancestor is found (e.g. stripped wheel).
    """
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").is_file():
            return parent
    return None


def resolve_env_file_path() -> Path | None:
    """
    1. ``PYPEDEID_ENV_FILE`` if set and the path exists.
    2. First ``.env`` found walking up from :func:`Path.cwd`.
    3. ``.env`` next to the nearest ``pyproject.toml`` ancestor of this package (repo root).
    """
    explicit = os.environ.get("PYPEDEID_ENV_FILE")
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file():
            return p
        return None

    for base in [Path.cwd(), *Path.cwd().parents]:
        cand = base / ".env"
        if cand.is_file():
            return cand

    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").is_file():
            cand = parent / ".env"
            if cand.is_file():
                return cand
            break

    return None
