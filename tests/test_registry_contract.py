"""Contract test for the pipe catalog.

Loops every catalog entry and asserts metadata is internally consistent so
adding a new detector without filling out the right fields fails CI rather
than silently breaking the playground.
"""

from __future__ import annotations

import importlib

import pytest

from pypedeid.pipes.registry import (
    PipeCatalogEntry,
    pipe_availability,
    pipe_catalog,
)


def _import_dotted(path: str):
    module_path, name = path.rsplit(":", 1)
    return getattr(importlib.import_module(module_path), name)


@pytest.fixture(scope="module")
def catalog() -> list[PipeCatalogEntry]:
    return pipe_catalog()


def test_every_entry_resolves_config_and_pipe(catalog: list[PipeCatalogEntry]) -> None:
    """``config_path`` and ``pipe_path`` import cleanly for every always-available pipe."""
    for entry in catalog:
        if entry.extra is not None:
            continue  # optional install — may not be importable in test env
        _import_dotted(entry.config_path)
        _import_dotted(entry.pipe_path)


def test_default_base_labels_fn_resolves_when_set(catalog: list[PipeCatalogEntry]) -> None:
    for entry in catalog:
        if entry.default_base_labels_fn is None or entry.extra is not None:
            continue
        fn = _import_dotted(entry.default_base_labels_fn)
        result = fn()
        assert isinstance(result, list)
        assert all(isinstance(x, str) for x in result)


def test_bundle_pipes_declare_bundle_fn_and_semantics(
    catalog: list[PipeCatalogEntry],
) -> None:
    """``label_source in {'bundle', 'both'}`` requires both bundle fn and key semantics."""
    for entry in catalog:
        if entry.label_source not in ("bundle", "both"):
            continue
        assert entry.label_space_bundle_fn, (
            f"{entry.name}: label_source={entry.label_source!r} requires label_space_bundle_fn"
        )
        assert entry.bundle_key_semantics, (
            f"{entry.name}: label_source={entry.label_source!r} requires bundle_key_semantics"
        )
        if entry.extra is None:
            fn = _import_dotted(entry.label_space_bundle_fn)
            bundle = fn()
            assert {"labels_by_model", "default_entity_map", "default_model"} <= bundle.keys()


def test_dynamic_options_fns_resolve(catalog: list[PipeCatalogEntry]) -> None:
    for entry in catalog:
        for source, dotted in entry.dynamic_options_fns.items():
            fn = _import_dotted(dotted)
            assert callable(fn), f"{entry.name}: source {source!r} dotted {dotted!r} not callable"
            assert isinstance(fn(), list)


def test_dependencies_fn_signature(catalog: list[PipeCatalogEntry]) -> None:
    for entry in catalog:
        if entry.dependencies_fn is None:
            continue
        fn = _import_dotted(entry.dependencies_fn)
        result = fn({})
        assert isinstance(result, list)
        assert all(isinstance(x, str) for x in result)


def test_non_detectors_have_label_source_none(catalog: list[PipeCatalogEntry]) -> None:
    """Span transformers and redactors should not expose a label space to the UI."""
    for entry in catalog:
        if entry.role == "detector":
            continue
        assert entry.label_source == "none", (
            f"{entry.name}: role={entry.role!r} should have label_source='none'"
        )


def test_pipe_availability_includes_new_fields() -> None:
    """``pipe_availability()`` exposes label_source + bundle_key_semantics so the API can serialize them."""
    for info in pipe_availability():
        assert "label_source" in info
        assert "bundle_key_semantics" in info
