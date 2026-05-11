"""Filesystem-based dataset registry (colocated, JSONL-only).

Each dataset named ``my-set`` lives in ``<corpora_dir>/my-set/``:

- ``corpus.jsonl`` — the canonical corpus (one :class:`~clinical_deid.domain.AnnotatedDocument` per line)
- ``dataset.json`` — cached manifest (analytics, metadata)

Listing is discovery-based: any subdirectory containing ``corpus.jsonl`` qualifies, and
``dataset.json`` is auto-created on first read if missing. BRAT is an ingest/export
format, not a storage layout — use :func:`import_brat_to_jsonl` to convert a BRAT tree
into a JSONL home, and ``write_annotated_corpus(brat_dir=…)`` under ``exports_dir`` to
export back out.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from clinical_deid.analytics.stats import (
    compute_dataset_analytics,
    compute_split_document_counts,
    has_split_metadata,
)
from clinical_deid.domain import AnnotatedDocument
from clinical_deid.ingest.sources import load_annotated_corpus
from clinical_deid.ingest.sink import write_annotated_corpus

logger = logging.getLogger(__name__)

#: The on-disk storage format. Only ``"jsonl"`` is supported; the alias is kept for
#: grep-ability and for the small number of call sites that still pass it explicitly.
DatasetFormat = Literal["jsonl"]

DATASET_MANIFEST_NAME = "dataset.json"
CORPUS_JSONL_NAME = "corpus.jsonl"
MANIFEST_SCHEMA_COLOCATED = 2

_SAFE_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")

_BRAT_SPLIT_NAMES = frozenset({"train", "valid", "test", "dev", "deploy"})


def validate_name(name: str) -> None:
    """Reject dataset names that could escape ``corpora_dir`` or write outside the registry.

    Public so API routes can validate ``output_name`` before any ``mkdir`` runs.
    """
    if not _SAFE_NAME.match(name) or ".." in name:
        raise ValueError(
            f"Invalid dataset name {name!r}: must match {_SAFE_NAME.pattern} "
            f"and not contain '..'"
        )


_validate_name = validate_name  # internal alias (kept for back-compat within this module)


def _ensure_corpora_root(corpora_dir: Path) -> None:
    corpora_dir.mkdir(parents=True, exist_ok=True)


def dataset_home(corpora_dir: Path, name: str) -> Path:
    """Return ``corpora_dir / name`` (the dataset directory)."""
    _validate_name(name)
    return corpora_dir / name


def manifest_path(corpora_dir: Path, name: str) -> Path:
    return dataset_home(corpora_dir, name) / DATASET_MANIFEST_NAME


def corpus_data_path(home: Path, fmt: DatasetFormat = "jsonl") -> Path:
    """Path to ``corpus.jsonl`` inside *home* (kept as a helper for call sites)."""
    return home / CORPUS_JSONL_NAME


def _load_documents(home: Path) -> list[AnnotatedDocument]:
    jsonl = home / CORPUS_JSONL_NAME
    return load_annotated_corpus(jsonl=jsonl)


def unique_labels_for_jsonl_corpus(corpus_path: Path) -> tuple[list[str], int]:
    """Return sorted unique gold span label strings and document count for a JSONL file.

    Used by ``POST /datasets/preview-labels`` and tests; loads the full file like eval.
    """
    docs = load_annotated_corpus(jsonl=corpus_path)
    if not docs:
        return [], 0
    analytics = compute_dataset_analytics(docs)
    return sorted(analytics.label_counts.keys()), len(docs)


def _compute_summary(docs: list[AnnotatedDocument]) -> dict[str, Any]:
    analytics = compute_dataset_analytics(docs)
    split_document_counts = compute_split_document_counts(docs)
    return {
        "document_count": analytics.document_count,
        "total_spans": analytics.total_spans,
        "labels": sorted(analytics.label_counts.keys()),
        "analytics": json.loads(analytics.model_dump_json()),
        "split_document_counts": split_document_counts,
        "has_split_metadata": has_split_metadata(docs),
    }


def _build_manifest(
    name: str,
    *,
    description: str,
    metadata: dict[str, Any],
    summary: dict[str, Any],
    created_at: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "schema_version": MANIFEST_SCHEMA_COLOCATED,
        "layout": "colocated",
        "format": "jsonl",
        "description": description,
        "document_count": summary["document_count"],
        "total_spans": summary["total_spans"],
        "labels": summary["labels"],
        "analytics": summary["analytics"],
        "split_document_counts": summary.get("split_document_counts", {}),
        "has_split_metadata": summary.get("has_split_metadata", False),
        "metadata": metadata,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Info struct
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DatasetInfo:
    """Summary of a registered dataset."""

    name: str
    path: Path  # manifest path (…/name/dataset.json)
    description: str
    data_path: str  # resolved path to corpus.jsonl (for API / CLI)
    format: DatasetFormat
    document_count: int
    total_spans: int
    labels: list[str]
    created_at: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class RefreshResult:
    """Outcome of a single dataset refresh (used by :func:`refresh_all_datasets`)."""

    name: str
    status: Literal["ok", "error"]
    error: str | None = None


# ---------------------------------------------------------------------------
# BRAT detection (reused by import helpers)
# ---------------------------------------------------------------------------


def _has_brat_pairs(directory: Path) -> bool:
    for txt in directory.glob("*.txt"):
        if txt.with_suffix(".ann").is_file():
            return True
    return False


def _looks_like_brat_split_corpus(d: Path) -> bool:
    for name in _BRAT_SPLIT_NAMES:
        sub = d / name
        if sub.is_dir() and _has_brat_pairs(sub):
            return True
    return False


# ---------------------------------------------------------------------------
# Import candidates (JSONL + BRAT discovery surfaces)
# ---------------------------------------------------------------------------


def list_import_candidates(corpora_dir: Path) -> list[dict[str, Any]]:
    """JSONL-only import candidates under *corpora_dir*.

    Suggests any ``.jsonl`` file or any unregistered directory that contains a single
    ``.jsonl`` (or ``corpus.jsonl``). BRAT trees are surfaced separately via
    :func:`list_brat_import_candidates`.

    Registered dataset homes (directories that already contain ``corpus.jsonl``) are
    skipped so ``register`` cannot accidentally re-import a live dataset.
    """
    _ensure_corpora_root(corpora_dir)
    out: list[dict[str, Any]] = []
    for child in sorted(corpora_dir.iterdir(), key=lambda p: p.name.lower()):
        if child.name.startswith("."):
            continue
        if child.is_file():
            if child.suffix.lower() == ".jsonl":
                out.append(
                    {
                        "label": child.name,
                        "data_path": str(child.resolve()),
                        "suggested_format": "jsonl",
                    }
                )
            continue
        if not child.is_dir():
            continue
        # Skip registered homes — discovery already surfaces these.
        if (child / CORPUS_JSONL_NAME).is_file():
            continue
        jsonl_files = sorted(child.glob("*.jsonl"))
        if len(jsonl_files) == 1:
            src = jsonl_files[0]
            label = f"{child.name}/{src.name}" if src.name != CORPUS_JSONL_NAME else child.name
            out.append(
                {
                    "label": label,
                    "data_path": str(src.resolve()),
                    "suggested_format": "jsonl",
                }
            )
    return out


def list_brat_import_candidates(corpora_dir: Path) -> list[dict[str, Any]]:
    """BRAT import candidates: directories under *corpora_dir* that look like BRAT trees.

    Flat directories with ``*.txt``/``*.ann`` pairs are tagged ``"brat-dir"``; split
    corpora (``train``/``valid``/…) are tagged ``"brat-corpus"``. These are *suggestions*
    for :func:`import_brat_to_jsonl`; nothing is written until the caller imports.
    """
    _ensure_corpora_root(corpora_dir)
    out: list[dict[str, Any]] = []
    for child in sorted(corpora_dir.iterdir(), key=lambda p: p.name.lower()):
        if child.name.startswith(".") or not child.is_dir():
            continue
        # Skip registered homes.
        if (child / CORPUS_JSONL_NAME).is_file():
            continue
        if _looks_like_brat_split_corpus(child):
            kind: Literal["brat-dir", "brat-corpus"] = "brat-corpus"
        elif _has_brat_pairs(child):
            kind = "brat-dir"
        else:
            continue
        out.append(
            {
                "label": child.name,
                "data_path": str(child.resolve()),
                "kind": kind,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Discovery + CRUD
# ---------------------------------------------------------------------------


def list_datasets(corpora_dir: Path) -> list[DatasetInfo]:
    """Discover datasets: every subdir with ``corpus.jsonl`` qualifies.

    ``dataset.json`` is lazily computed on first listing if missing. Homes whose
    existing ``dataset.json`` declares a non-JSONL ``format`` (legacy BRAT-colocated
    layout) are skipped — those users need to re-import via
    :func:`import_brat_to_jsonl`.
    """
    _ensure_corpora_root(corpora_dir)
    results: list[DatasetInfo] = []
    for child in sorted(corpora_dir.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if not _SAFE_NAME.match(child.name):
            continue
        if not (child / CORPUS_JSONL_NAME).is_file():
            continue
        name = child.name
        mp = child / DATASET_MANIFEST_NAME
        try:
            if mp.is_file():
                data = json.loads(mp.read_text(encoding="utf-8"))
                existing_fmt = data.get("format")
                if existing_fmt and existing_fmt != "jsonl":
                    logger.debug(
                        "Skipping legacy dataset home %s (format=%r; re-import via BRAT → JSONL)",
                        child,
                        existing_fmt,
                    )
                    continue
                # Auto-migrate missing format → jsonl without refreshing analytics.
                if existing_fmt != "jsonl":
                    data["format"] = "jsonl"
                    save_dataset_manifest(corpora_dir, name, data)
            else:
                data = commit_colocated_dataset(corpora_dir, name)
            results.append(_manifest_to_info(corpora_dir, name, mp, data))
        except (json.JSONDecodeError, OSError, KeyError, ValueError) as exc:
            logger.warning("Skipping broken dataset home %s: %s", child, exc)
            continue
    return results


def load_dataset_manifest(corpora_dir: Path, name: str) -> dict[str, Any]:
    """Load the full manifest dict (auto-writes it on first access if missing)."""
    _validate_name(name)
    home = dataset_home(corpora_dir, name)
    path = home / DATASET_MANIFEST_NAME
    if not path.is_file():
        if not (home / CORPUS_JSONL_NAME).is_file():
            available = _available_dataset_names(corpora_dir)
            raise FileNotFoundError(
                f"Dataset {name!r} not found under {corpora_dir}. "
                f"Available: {', '.join(sorted(available)) or '(none)'}"
            )
        return commit_colocated_dataset(corpora_dir, name)
    return json.loads(path.read_text(encoding="utf-8"))


def _available_dataset_names(corpora_dir: Path) -> list[str]:
    if not corpora_dir.is_dir():
        return []
    out: list[str] = []
    for child in corpora_dir.iterdir():
        if child.is_dir() and (child / CORPUS_JSONL_NAME).is_file():
            out.append(child.name)
    return out


def save_dataset_manifest(corpora_dir: Path, name: str, manifest: dict[str, Any]) -> Path:
    """Write ``dataset.json`` for *name*. Creates parent directory if needed."""
    _validate_name(name)
    home = dataset_home(corpora_dir, name)
    home.mkdir(parents=True, exist_ok=True)
    path = home / DATASET_MANIFEST_NAME
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def delete_dataset(corpora_dir: Path, name: str) -> None:
    """Remove the dataset directory (manifest + corpus files)."""
    _validate_name(name)
    home = dataset_home(corpora_dir, name)
    if not home.is_dir() or not (home / CORPUS_JSONL_NAME).is_file():
        raise FileNotFoundError(f"Dataset {name!r} not found under {corpora_dir}")
    shutil.rmtree(home)


# ---------------------------------------------------------------------------
# Import + commit
# ---------------------------------------------------------------------------


def import_jsonl_dataset(
    corpora_dir: Path,
    name: str,
    data_path: str,
    *,
    description: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy a JSONL source into ``corpora_dir/name/`` and write ``dataset.json``."""
    _validate_name(name)
    _ensure_corpora_root(corpora_dir)
    src = Path(data_path).resolve()
    if not src.is_file():
        raise ValueError(f"JSONL source must be a file: {src}")
    home = dataset_home(corpora_dir, name)
    if home.exists():
        raise ValueError(
            f"Dataset directory already exists: {home}. "
            "Choose another name or remove the existing dataset."
        )
    home.mkdir(parents=True)
    try:
        shutil.copy2(src, home / CORPUS_JSONL_NAME)
        docs = _load_documents(home)
        if not docs:
            raise ValueError(f"No documents found after import into {home}")
        summary = _compute_summary(docs)
        manifest = _build_manifest(
            name,
            description=description,
            metadata=metadata or {},
            summary=summary,
        )
        save_dataset_manifest(corpora_dir, name, manifest)
    except Exception:
        if home.is_dir():
            shutil.rmtree(home)
        raise
    return manifest


def save_document_subset(
    corpora_dir: Path,
    name: str,
    documents: list[AnnotatedDocument],
    *,
    description: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write an in-memory :class:`AnnotatedDocument` list as a new registered dataset.

    Used by ``/eval/run`` with ``save_sample_as`` so a sampled subset becomes a named
    dataset without a round-trip through disk. Errors (name collision, empty list)
    propagate as :class:`ValueError`; the home directory is cleaned up on failure.
    """
    _validate_name(name)
    _ensure_corpora_root(corpora_dir)
    if not documents:
        raise ValueError("Cannot save an empty document subset")
    home = dataset_home(corpora_dir, name)
    if home.exists():
        raise ValueError(
            f"Dataset directory already exists: {home}. "
            "Choose another name or remove the existing dataset."
        )
    home.mkdir(parents=True)
    try:
        write_annotated_corpus(documents, jsonl=home / CORPUS_JSONL_NAME)
        summary = _compute_summary(documents)
        manifest = _build_manifest(
            name,
            description=description,
            metadata=metadata or {},
            summary=summary,
        )
        save_dataset_manifest(corpora_dir, name, manifest)
    except Exception:
        if home.is_dir():
            shutil.rmtree(home, ignore_errors=True)
        raise
    return manifest


def register_dataset(
    corpora_dir: Path,
    name: str,
    data_path: str,
    fmt: DatasetFormat = "jsonl",
    *,
    description: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Back-compat shim for :func:`import_jsonl_dataset`.

    Only ``fmt="jsonl"`` is supported. BRAT sources must go through
    :func:`import_brat_to_jsonl`.
    """
    if fmt != "jsonl":
        raise ValueError(
            f"register_dataset no longer accepts fmt={fmt!r}; only 'jsonl' is supported. "
            "Use import_brat_to_jsonl() to convert BRAT → JSONL first."
        )
    return import_jsonl_dataset(
        corpora_dir,
        name,
        data_path,
        description=description,
        metadata=metadata,
    )


def import_brat_to_jsonl(
    corpora_dir: Path,
    name: str,
    brat_source: Path,
    *,
    description: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert a BRAT tree into a new JSONL dataset home.

    Auto-detects flat BRAT (``*.txt``/``*.ann`` pairs) vs split corpus
    (``train``/``valid``/… subdirs). Writes ``corpus.jsonl`` + ``dataset.json`` under
    ``corpora_dir/name/``; the source BRAT files are *not* copied.
    """
    _validate_name(name)
    _ensure_corpora_root(corpora_dir)
    src = Path(brat_source).resolve()
    if not src.is_dir():
        raise ValueError(f"BRAT source must be a directory: {src}")

    if _looks_like_brat_split_corpus(src):
        docs = load_annotated_corpus(brat_corpus=src)
        provenance_kind = "brat-corpus"
    elif _has_brat_pairs(src):
        docs = load_annotated_corpus(brat_dir=src)
        provenance_kind = "brat-dir"
    else:
        raise ValueError(
            f"No BRAT files found under {src} "
            "(expected *.txt/*.ann pairs or train/valid/test subdirs)."
        )

    if not docs:
        raise ValueError(f"No documents loaded from BRAT source {src}")

    home = dataset_home(corpora_dir, name)
    if home.exists():
        raise FileExistsError(
            f"Dataset directory already exists: {home}. "
            "Choose another name or remove the existing dataset."
        )
    home.mkdir(parents=True)
    try:
        write_annotated_corpus(docs, jsonl=home / CORPUS_JSONL_NAME)
        summary = _compute_summary(docs)
        merged_metadata = dict(metadata or {})
        provenance = {
            "imported_from": str(src),
            "source_kind": provenance_kind,
        }
        merged_metadata.setdefault("provenance", provenance)
        manifest = _build_manifest(
            name,
            description=description,
            metadata=merged_metadata,
            summary=summary,
        )
        save_dataset_manifest(corpora_dir, name, manifest)
    except Exception:
        if home.is_dir():
            shutil.rmtree(home)
        raise
    return manifest


def commit_colocated_dataset(
    corpora_dir: Path,
    name: str,
    fmt: DatasetFormat = "jsonl",
    *,
    description: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write ``dataset.json`` for a home that already contains ``corpus.jsonl``.

    If a manifest already exists, its description/metadata/created_at are preserved
    (only analytics are recomputed) unless the caller passes overrides explicitly.
    """
    _validate_name(name)
    if fmt != "jsonl":
        raise ValueError(f"commit_colocated_dataset only supports 'jsonl' (got {fmt!r})")
    home = dataset_home(corpora_dir, name)
    if not home.is_dir():
        raise FileNotFoundError(f"Dataset home not found: {home}")
    if not (home / CORPUS_JSONL_NAME).is_file():
        raise ValueError(f"Missing {CORPUS_JSONL_NAME} in {home}")
    docs = _load_documents(home)
    if not docs:
        raise ValueError(f"No documents found in {home}")

    existing: dict[str, Any] = {}
    mp = home / DATASET_MANIFEST_NAME
    if mp.is_file():
        try:
            existing = json.loads(mp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}

    desc = description if description else existing.get("description", "")
    meta = metadata if metadata is not None else existing.get("metadata", {})
    created_at = existing.get("created_at")

    summary = _compute_summary(docs)
    manifest = _build_manifest(
        name,
        description=desc,
        metadata=meta or {},
        summary=summary,
        created_at=created_at,
    )
    save_dataset_manifest(corpora_dir, name, manifest)
    return manifest


def refresh_analytics(corpora_dir: Path, name: str) -> dict[str, Any]:
    """Reload corpus from disk and update manifest analytics (preserving metadata)."""
    home = dataset_home(corpora_dir, name)
    if not (home / CORPUS_JSONL_NAME).is_file():
        raise FileNotFoundError(f"Dataset {name!r} not found under {corpora_dir}")
    manifest = load_dataset_manifest(corpora_dir, name)
    docs = _load_documents(home)
    summary = _compute_summary(docs)
    manifest.update(
        {
            "format": "jsonl",
            "document_count": summary["document_count"],
            "total_spans": summary["total_spans"],
            "labels": summary["labels"],
            "analytics": summary["analytics"],
            "split_document_counts": summary["split_document_counts"],
            "has_split_metadata": summary["has_split_metadata"],
        }
    )
    save_dataset_manifest(corpora_dir, name, manifest)
    return manifest


#: Public verb alias; ``refresh_analytics`` is retained for existing call sites.
refresh_dataset = refresh_analytics


def refresh_all_datasets(corpora_dir: Path) -> list[RefreshResult]:
    """Refresh analytics for every discovered dataset, catching per-home errors."""
    results: list[RefreshResult] = []
    for info in list_datasets(corpora_dir):
        try:
            refresh_analytics(corpora_dir, info.name)
            results.append(RefreshResult(name=info.name, status="ok"))
        except Exception as exc:
            logger.warning("Refresh failed for %s: %s", info.name, exc)
            results.append(RefreshResult(name=info.name, status="error", error=str(exc)))
    return results


def load_dataset_documents(corpora_dir: Path, name: str) -> list[AnnotatedDocument]:
    home = dataset_home(corpora_dir, name)
    if not (home / CORPUS_JSONL_NAME).is_file():
        raise FileNotFoundError(f"Dataset {name!r} not found under {corpora_dir}")
    return _load_documents(home)


def update_document(
    corpora_dir: Path,
    name: str,
    doc_id: str,
    *,
    spans: list[Any],
    text: str | None = None,
) -> AnnotatedDocument:
    """Replace ``spans`` (and optionally ``text``) on a document; atomic rewrite.

    Validates every span's offsets against the final text. Raises ``KeyError`` if
    the document id is not present, or ``ValueError`` if any span is out of range.
    Recomputes analytics after the rewrite.
    """
    from clinical_deid.domain import EntitySpan

    home = dataset_home(corpora_dir, name)
    corpus_path = home / CORPUS_JSONL_NAME
    if not corpus_path.is_file():
        raise FileNotFoundError(f"Dataset {name!r} not found under {corpora_dir}")

    validated_spans: list[EntitySpan] = []
    for s in spans:
        validated_spans.append(s if isinstance(s, EntitySpan) else EntitySpan.model_validate(s))

    docs = _load_documents(home)
    updated: AnnotatedDocument | None = None
    new_docs: list[AnnotatedDocument] = []
    for d in docs:
        if d.document.id == doc_id:
            new_text = text if text is not None else d.document.text
            for sp in validated_spans:
                if sp.start < 0 or sp.end > len(new_text) or sp.start >= sp.end:
                    raise ValueError(
                        f"Span [{sp.start}:{sp.end}] out of range for text of length {len(new_text)}"
                    )
            new_document = d.document.model_copy(update={"text": new_text}) if text is not None else d.document
            updated = AnnotatedDocument(document=new_document, spans=validated_spans)
            new_docs.append(updated)
        else:
            new_docs.append(d)

    if updated is None:
        raise KeyError(f"Document {doc_id!r} not found in dataset {name!r}")

    tmp_path = corpus_path.with_suffix(corpus_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        for d in new_docs:
            fh.write(d.model_dump_json() + "\n")
    tmp_path.replace(corpus_path)

    refresh_analytics(corpora_dir, name)
    return updated


def public_data_path(corpora_dir: Path, name: str, manifest: dict[str, Any] | None = None) -> str:
    """Resolved corpus path for API responses (``data_path`` field)."""
    home = dataset_home(corpora_dir, name)
    return str((home / CORPUS_JSONL_NAME).resolve())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _manifest_to_info(
    corpora_dir: Path, name: str, path: Path, data: dict[str, Any]
) -> DatasetInfo:
    if data.get("name") and data["name"] != name:
        raise ValueError(f"Manifest name mismatch: dir {name!r} vs manifest {data.get('name')!r}")
    home = dataset_home(corpora_dir, name)
    return DatasetInfo(
        name=name,
        path=path,
        description=data.get("description", ""),
        data_path=str((home / CORPUS_JSONL_NAME).resolve()),
        format="jsonl",
        document_count=data.get("document_count", 0),
        total_spans=data.get("total_spans", 0),
        labels=data.get("labels", []),
        created_at=data.get("created_at", ""),
        metadata=data.get("metadata", {}),
    )
