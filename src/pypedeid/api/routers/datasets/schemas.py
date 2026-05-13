"""Request / response schemas shared across datasets sub-routers."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from pypedeid.dataset_store import DatasetFormat


class DatasetSummary(BaseModel):
    name: str
    description: str
    data_path: str
    format: DatasetFormat
    document_count: int
    total_spans: int
    labels: list[str]
    created_at: str


class DatasetDetail(DatasetSummary):
    analytics: dict[str, Any]
    metadata: dict[str, Any]
    split_document_counts: dict[str, int] = Field(
        default_factory=dict,
        description="Documents per metadata['split']; missing/invalid → '(none)'.",
    )
    has_split_metadata: bool = False


class RegisterDatasetRequest(BaseModel):
    name: str
    data_path: str
    format: DatasetFormat = "jsonl"
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImportBratRequest(BaseModel):
    name: str
    brat_path: str
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImportSourceCandidate(BaseModel):
    """A JSONL file or JSONL-in-folder that can be imported via ``POST /datasets``."""

    label: str
    data_path: str
    suggested_format: DatasetFormat


class ImportSourcesResponse(BaseModel):
    corpora_root: str
    candidates: list[ImportSourceCandidate]


class BratImportCandidate(BaseModel):
    """A directory under the corpora root that looks like a BRAT tree."""

    label: str
    data_path: str
    kind: Literal["brat-dir", "brat-corpus"]


class BratImportSourcesResponse(BaseModel):
    corpora_root: str
    candidates: list[BratImportCandidate]


class RefreshResultResponse(BaseModel):
    name: str
    status: Literal["ok", "error"]
    error: str | None = None


class UpdateDatasetRequest(BaseModel):
    description: str | None = None
    metadata: dict[str, Any] | None = None


class DocumentPreview(BaseModel):
    document_id: str
    text_preview: str
    span_count: int
    labels: list[str]
    split: str | None = None


class DatasetPreviewResponse(BaseModel):
    items: list[DocumentPreview]
    total: int


class ComposeRequest(BaseModel):
    """Compose multiple registered datasets into a new dataset."""

    output_name: str
    source_datasets: list[str] = Field(min_length=1)
    strategy: Literal["merge", "interleave", "proportional"] = "merge"
    weights: list[float] | None = None
    target_documents: int | None = None
    seed: int = 42
    shuffle: bool = False
    description: str = ""


class TransformRequest(BaseModel):
    """Apply transforms to a dataset and save as a new dataset.

    Output is written under ``$CORPORA_DIR/{output_name}/corpus.jsonl``. Use
    ``/datasets/{name}/export`` with ``format: "brat"`` to materialize BRAT for external tools.
    """

    source_dataset: str
    output_name: str = ""
    #: When True, overwrite the source dataset (``source_dataset``) in place. ``output_name`` is ignored.
    in_place: bool = False
    #: If set, only documents with ``metadata["split"]`` in this list are transformed.
    source_splits: list[str] | None = None
    drop_labels: list[str] | None = None
    keep_labels: list[str] | None = None
    label_mapping: dict[str, str] | None = None
    target_documents: int | None = None
    boost_label: str | None = None
    boost_extra_copies: int = 0
    resplit: dict[str, float] | None = None
    strip_splits: bool = False
    seed: int = 42
    description: str = ""
    transform_mode: Literal["full", "schema", "sampling", "partitioning"] = "full"
    #: If False, :func:`reassign_splits` uses stable document id order (no shuffle) before assignment.
    resplit_shuffle: bool = True
    #: Strip ``metadata['split']`` on targeted documents before re-partitioning (partitioning / full with resplit).
    flatten_target_splits: bool = False


class TransformPreviewRequest(BaseModel):
    """Dry-run the same transforms as ``TransformRequest`` (no write)."""

    source_dataset: str
    #: When true, match :func:`transform_dataset` merge semantics (rest + transformed work). When
    #: false and ``source_splits`` is set, the projected output is the work subset only.
    in_place: bool = False
    source_splits: list[str] | None = None
    drop_labels: list[str] | None = None
    keep_labels: list[str] | None = None
    label_mapping: dict[str, str] | None = None
    target_documents: int | None = None
    boost_label: str | None = None
    boost_extra_copies: int = 0
    resplit: dict[str, float] | None = None
    strip_splits: bool = False
    seed: int = 42
    transform_mode: Literal["full", "schema", "sampling", "partitioning"] = "full"
    resplit_shuffle: bool = True
    flatten_target_splits: bool = False


class DatasetLabelFrequency(BaseModel):
    label: str
    count: int


class DatasetSchemaResponse(BaseModel):
    """Unique span labels and counts for building transform UI controls."""

    dataset: str
    document_count: int
    total_spans: int
    labels: list[DatasetLabelFrequency]


class TransformPreviewResponse(BaseModel):
    """Summary counts for filter / mapping / projected corpus size."""

    source_document_count: int
    source_span_count: int
    spans_dropped_by_filter: int
    spans_kept_after_filter: int
    spans_renamed: int
    projected_document_count: int
    projected_span_count: int
    split_document_counts: dict[str, int] | None = None
    #: Count of documents outside ``source_splits`` (when the filter is set). Omitted from the
    #: output of a *new* transform; left unchanged in the corpus for an *in-place* transform.
    untouched_document_count: int = 0
    conflicts: list[str] = Field(default_factory=list)


class GenerateRequest(BaseModel):
    """Generate synthetic clinical notes via LLM and register as a dataset."""

    output_name: str
    count: int = Field(ge=1, le=500, default=10)
    phi_types: list[str] = Field(
        default_factory=lambda: ["PERSON", "DATE", "LOCATION", "ID", "PHONE", "AGE"],
    )
    special_rules: str = ""
    description: str = ""
    llm_kwargs: dict[str, Any] = Field(default_factory=dict)


class UpdateDocumentRequest(BaseModel):
    """Replace a document's spans (and optionally its text).

    Concurrency: v1 is last-write-wins; two concurrent ``PUT``s for the same
    ``doc_id`` can race. Add an ETag / revision field if stricter semantics become
    necessary.
    """

    spans: list[dict[str, Any]] = Field(default_factory=list)
    text: str | None = None


class UpdateDocumentResponse(BaseModel):
    document_id: str
    text: str
    metadata: dict[str, Any]
    spans: list[dict[str, Any]]


class ExportTrainingRequest(BaseModel):
    format: Literal["conll", "spacy", "huggingface", "brat", "jsonl"] = "conll"
    filename: str | None = None
    target_text: Literal["original", "surrogate"] = Field(
        default="original",
        description=(
            "When 'surrogate', run surrogate alignment on each doc before exporting "
            "(text and spans both point at the surrogate)."
        ),
    )
    surrogate_seed: int | None = None


class ExportTrainingResponse(BaseModel):
    path: str
    format: str
    document_count: int
    total_spans: int
    target_text: Literal["original", "surrogate"] = "original"


class PreviewCorpusLabelsRequest(BaseModel):
    """Path to a gold ``.jsonl`` file under the corpora root (see ``resolve_source_under_corpora``)."""

    path: str = Field(
        ...,
        description="Relative to corpora root or absolute, must stay under that root.",
    )


class PreviewCorpusLabelsResponse(BaseModel):
    labels: list[str] = Field(description="Unique span label strings, sorted")
    document_count: int
    resolved_path: str = Field(
        description="Server-normalized path (for display when debugging).",
    )
