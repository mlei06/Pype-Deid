"""UI hints merged into pipe config JSON Schema via ``Field(json_schema_extra=…)``.

Standard keys (all optional):

- ``ui_group``: Section title in generated forms.
- ``ui_order``: Sort order within a group (int or float).
- ``ui_widget``: Suggested control — ``text``, ``textarea``, ``number``, ``slider``,
  ``switch``, ``select``, ``multiselect``, ``key_value``, ``label_mapping``,
  ``json``, ``file_paths``, ``regex``, ``nested_dict``, ``password``.
- ``ui_advanced``: If true, prefer an “Advanced” subsection.
- ``ui_placeholder`` / ``ui_help``: Short strings for inputs and tooltips.
- ``ui_visible_when``: Conditional display, e.g.
  ``{"field": "operator", "equals": "mask"}``.
- ``ui_allow_custom_labels``: When false (default for ``label_space`` / output mapping),
  hide the “add custom label” row; true for regex_ner and whitelist label editors.
- ``ui_options_source``: Token for dynamic enums (e.g. ``builtin_regex_labels``).

These appear on each property in :func:`pipe_config_json_schema` output (alongside
``description``, ``type``, etc.).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def field_ui(**kwargs: Any) -> dict[str, Any]:
    """Build a ``json_schema_extra`` dict; ``None`` values are omitted."""
    return {k: v for k, v in kwargs.items() if v is not None}


def pipe_config_json_schema(config_cls: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema for validating pipe ``config`` payloads (includes ``ui_*`` hints)."""
    return config_cls.model_json_schema()
