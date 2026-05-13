"""CLI package — the ``main`` group and its subcommands live in sibling modules.

The ``pypedeid`` console-script entry point in ``pyproject.toml`` still
resolves to ``pypedeid.cli:main`` via this re-export.
"""

from __future__ import annotations

from pypedeid.cli.root import main

# Importing each sub-module registers its commands/subgroups on ``main``.
from pypedeid.cli import audit  # noqa: E402, F401
from pypedeid.cli import dataset  # noqa: E402, F401
from pypedeid.cli import dict_  # noqa: E402, F401
from pypedeid.cli import train  # noqa: E402, F401

__all__ = ["main"]
