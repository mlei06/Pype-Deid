"""Pipe config JSON Schema includes ``ui_*`` hints for dynamic forms."""

from __future__ import annotations

import pytest

from pypedeid.pipes.blacklist.pipe import BlacklistSpansConfig
from pypedeid.pipes.combinators import (
    LabelFilterConfig,
    LabelMapperConfig,
    ResolveSpansConfig,
)
from pypedeid.pipes.regex_ner.pipe import RegexNerConfig
from pypedeid.pipes.registry import registered_pipes
from pypedeid.pipes.ui_schema import pipe_config_json_schema
from pypedeid.pipes.whitelist.pipe import WhitelistConfig


def test_pipe_config_json_schema_matches_model_json_schema() -> None:
    from pypedeid.pipes.combinators import LabelMapperConfig

    assert pipe_config_json_schema(LabelMapperConfig) == LabelMapperConfig.model_json_schema()


def test_unified_labels_field_has_ui_widget() -> None:
    schema = RegexNerConfig.model_json_schema()
    lm = schema["properties"]["labels"]
    assert lm.get("ui_widget") == "unified_label"
    assert lm.get("ui_group") == "Labels"


def test_resolve_spans_strategy_has_ui_hints() -> None:
    p = ResolveSpansConfig.model_json_schema()["properties"]["strategy"]
    assert p.get("ui_widget") == "described_select"
    assert p.get("ui_group") == "Resolution"
    assert isinstance(p.get("ui_enum_descriptions"), dict)
    assert "exact_dedupe" in p["ui_enum_descriptions"]


def test_label_mapper_mapping_has_ui_hints() -> None:
    p = LabelMapperConfig.model_json_schema()["properties"]["mapping"]
    assert p.get("ui_widget") == "label_mapping"


def test_label_filter_drop_keep_documented() -> None:
    props = LabelFilterConfig.model_json_schema()["properties"]
    assert props["drop"]["ui_group"] == "Filter"
    assert props["keep"]["ui_group"] == "Filter"


@pytest.mark.parametrize(
    "name",
    [
        "regex_ner",
        "whitelist",
        "label_mapper",
        "label_filter",
        "resolve_spans",
        "blacklist",
    ],
)
def test_registered_builtin_configs_expose_ui_metadata(name: str) -> None:
    cfg_cls = registered_pipes()[name]
    schema = cfg_cls.model_json_schema()
    props = schema.get("properties") or {}
    assert props, f"{name} should have properties"
    found = False
    for prop in props.values():
        if isinstance(prop, dict) and any(k.startswith("ui_") for k in prop):
            found = True
            break
    assert found, f"{name} should have at least one ui_* key on a property"


def test_whitelist_nested_schema_has_ui() -> None:
    schema = WhitelistConfig.model_json_schema()
    defs = schema.get("$defs", {})
    assert "WhitelistLabelSettings" in defs
    props = schema["properties"]
    assert props["labels"].get("ui_widget") == "whitelist_label"


def test_blacklist_regex_patterns_conditional_meta() -> None:
    p = BlacklistSpansConfig.model_json_schema()["properties"]["regex_blacklist_patterns"]
    assert p.get("ui_advanced") is True


@pytest.mark.parametrize(
    "name",
    [
        "regex_ner",
        "whitelist",
        "presidio_ner",
        "llm_ner",
        "neuroner_ner",
        "huggingface_ner",
    ],
)
def test_all_detectors_expose_skip_overlapping_in_general(name: str) -> None:
    """``skip_overlapping`` is implemented on every detector; the playground shows it
    in the main form (not only under Advanced) so it is discoverable like regex_ner.
    """
    cfg_cls = registered_pipes()[name]
    prop = cfg_cls.model_json_schema()["properties"]["skip_overlapping"]
    assert prop.get("type") == "boolean"
    assert prop.get("ui_widget") == "switch"
    assert prop.get("ui_group") == "General"
    assert prop.get("ui_advanced") is not True


