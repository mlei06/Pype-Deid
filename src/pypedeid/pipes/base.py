from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from pypedeid.domain import AnnotatedDocument


@runtime_checkable
class Pipe(Protocol):
    """Base protocol — all pipes take and return AnnotatedDocument."""

    def forward(self, doc: AnnotatedDocument) -> AnnotatedDocument: ...


class ConfigurablePipe:
    """Concrete base for pipes that store a Pydantic config as ``_config``.

    Provides a :attr:`pipe_config` property so serialization (``dump_pipe``)
    can access the config without relying on private-attribute conventions.
    """

    _config: BaseModel

    @property
    def pipe_config(self) -> BaseModel:
        return self._config


@runtime_checkable
class Detector(Pipe, Protocol):
    """Produces PHI spans from document text."""

    @property
    def labels(self) -> set[str]:
        """Entity labels this detector can produce."""
        ...


@runtime_checkable
class DetectorWithLabelMapping(Detector, Protocol):
    """Detector with configurable :attr:`label_mapping` (including null to drop a label)."""

    @property
    def base_labels(self) -> set[str]:
        """Labels produced before ``label_mapping`` is applied."""

    @property
    def label_mapping(self) -> dict[str, str | None]:
        """Current map from base label → output label, or ``None`` to drop."""

    @property
    def labels(self) -> set[str]:
        """Effective output labels after ``label_mapping``."""


class Preprocessor(Pipe, Protocol):
    """Transforms document text before detection (e.g. normalise whitespace)."""

    ...


class SpanTransformer(Pipe, Protocol):
    """Modifies spans without changing document text (e.g. remap labels, filter)."""

    ...
