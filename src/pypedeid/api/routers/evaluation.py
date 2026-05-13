"""Evaluation HTTP API — run pipelines against datasets and retrieve metrics."""

from __future__ import annotations

import logging
import random
import secrets
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from pypedeid.api.auth import require_admin
from pypedeid.api.deps import SessionDep
from pypedeid.config import get_settings
from pypedeid.eval.metrics_json import build_persisted_eval_metrics, eval_metrics_to_dict
from pypedeid.eval_store import EvalResultInfo, list_eval_results, load_eval_result, save_eval_result
from pypedeid.pipeline_store import load_pipeline_config
from pypedeid.pipes.registry import load_pipeline
from pypedeid.tables import AuditLogRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/eval", tags=["evaluation"], dependencies=[require_admin])


def _eval_dataset_source_with_splits(base: str, splits: list[str] | None) -> str:
    if not splits or not any(str(s).strip() for s in splits):
        return base
    norm = sorted({s.strip() for s in splits if s and str(s).strip()})
    return f"{base}:splits={'+'.join(norm)}"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class MatchMetrics(BaseModel):
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int


class EvalMetricsResponse(BaseModel):
    strict: MatchMetrics
    exact_boundary: MatchMetrics
    partial_overlap: MatchMetrics
    token_level: MatchMetrics
    risk_weighted_recall: float


class SaveSampleAsSpec(BaseModel):
    """Register the sampled document list as a new JSONL dataset under ``corpora_dir``."""

    dataset_name: str = Field(
        ..., description="Name for the new dataset; same rules as POST /datasets."
    )
    description: str | None = None


class EvalRunRequest(BaseModel):
    pipeline_name: str
    dataset_path: str | None = None
    dataset_name: str | None = None
    #: If set, only documents whose ``metadata["split"]`` is in this list are evaluated.
    dataset_splits: list[str] | None = None
    risk_profile_name: str | None = Field(
        default=None,
        description=(
            "When set, use this risk profile for risk-weighted recall. "
            "When omitted, uses the active profile from server settings "
            "(PYPEDEID_RISK_PROFILE_NAME, default clinical_phi)."
        ),
    )
    #: Whether to run on the full (split-filtered) corpus or a random subset.
    eval_mode: Literal["full", "sample"] = "full"
    #: Required when ``eval_mode == "sample"``; must satisfy
    #: ``1 <= sample_size <= len(documents_after_split)``.
    sample_size: int | None = None
    #: When ``eval_mode == "sample"``: integer ⇒ deterministic draw, ``None`` ⇒ server draws
    #: a fresh seed and returns it on the response. Ignored when ``eval_mode == "full"``.
    sample_seed: int | None = None
    #: When provided together with ``eval_mode == "sample"``, persist the sampled
    #: document list as a new registered dataset (see :class:`SaveSampleAsSpec`).
    save_sample_as: SaveSampleAsSpec | None = None
    #: When ``true``, the HTTP response (but not the persisted eval JSON) gains
    #: ``metrics.document_level`` — per-document scores sorted worst-F1 first,
    #: truncated at ``Settings.eval_per_document_limit`` (flagged via
    #: ``metrics.document_level_truncated``).
    include_per_document: bool = False
    #: Implies ``include_per_document``; each item additionally carries ``text``,
    #: ``gold_spans``, ``pred_spans``, ``false_positives``, ``false_negatives``.
    #: Only enable for admin-controlled debugging — the payload contains raw
    #: document text and is not redacted.
    include_per_document_spans: bool = False
    #: For this run only, rename **predicted** span labels to match the gold
    #: dataset tagset (same role as a ``label_mapper`` step, without persisting
    #: the pipeline). Keys = pipeline output labels; values = target strings.
    eval_pred_label_remap: dict[str, str] | None = Field(
        default=None,
        description=(
            "Optional: map pipeline span labels to gold label strings for metrics only. "
            "Omitted or empty leaves predictions unchanged."
        ),
    )

    @field_validator("eval_pred_label_remap")
    @classmethod
    def _normalize_remap(
        cls, v: dict[str, str] | None
    ) -> dict[str, str] | None:
        if not v:
            return None
        for k, val in v.items():
            if not str(k).strip():
                raise ValueError("eval_pred_label_remap keys must be non-empty")
            if not str(val).strip():
                raise ValueError("eval_pred_label_remap values must be non-empty")
        return v


class EvalRunSummary(BaseModel):
    id: str
    pipeline_name: str
    dataset_source: str
    document_count: int
    strict_f1: float
    risk_weighted_recall: float
    created_at: str


class EvalRunDetail(EvalRunSummary):
    metrics: dict[str, Any]


class EvalCompareRequest(BaseModel):
    run_id_a: str
    run_id_b: str


class EvalCompareResponse(BaseModel):
    run_a: EvalRunDetail
    run_b: EvalRunDetail
    delta_strict_f1: float
    delta_risk_weighted_recall: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _info_to_summary(info: EvalResultInfo) -> EvalRunSummary:
    return EvalRunSummary(
        id=info.id,
        pipeline_name=info.pipeline_name,
        dataset_source=info.dataset_source,
        document_count=info.document_count,
        strict_f1=info.strict_f1,
        risk_weighted_recall=info.risk_weighted_recall,
        created_at=info.created_at,
    )


def _data_to_detail(data: dict[str, Any]) -> EvalRunDetail:
    metrics = data.get("metrics", {})
    overall = metrics.get("overall", {})
    strict = overall.get("strict", {})
    return EvalRunDetail(
        id=data.get("id", ""),
        pipeline_name=data.get("pipeline_name", ""),
        dataset_source=data.get("dataset_source", ""),
        document_count=data.get("document_count", 0),
        strict_f1=strict.get("f1", 0.0),
        risk_weighted_recall=metrics.get("risk_weighted_recall", 0.0),
        created_at=data.get("created_at", ""),
        metrics=metrics,
    )


def _span_to_dict(span) -> dict[str, Any]:
    return {"start": span.start, "end": span.end, "label": span.label}


def _build_document_level(doc_results, *, include_spans: bool, limit: int) -> dict[str, Any]:
    """Serialize per-document eval results for the HTTP response only.

    ``doc_results`` is already sorted worst-F1 first by the runner, so truncating
    at ``limit`` keeps the hardest cases.
    """
    truncated = len(doc_results) > limit
    trimmed = doc_results[:limit] if truncated else doc_results
    items: list[dict[str, Any]] = []
    for dr in trimmed:
        item: dict[str, Any] = {
            "document_id": dr.document_id,
            "metrics": eval_metrics_to_dict(dr.metrics),
            "risk_weighted_recall": dr.risk_weighted_recall,
            "false_positive_count": len(dr.false_positives),
            "false_negative_count": len(dr.false_negatives),
        }
        if include_spans:
            item["text"] = dr.text
            item["gold_spans"] = [_span_to_dict(s) for s in dr.gold_spans]
            item["pred_spans"] = [_span_to_dict(s) for s in dr.pred_spans]
            item["false_positives"] = [_span_to_dict(s) for s in dr.false_positives]
            item["false_negatives"] = [_span_to_dict(s) for s in dr.false_negatives]
        items.append(item)
    return {
        "document_level": items,
        "document_level_truncated": truncated,
        "document_level_total": len(doc_results),
        "document_level_includes_spans": include_spans,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/run", response_model=EvalRunDetail, status_code=201)
def run_evaluation(session: SessionDep, body: EvalRunRequest) -> EvalRunDetail:
    """Run a pipeline against a local dataset and store results."""
    from pathlib import Path

    from pypedeid.dataset_store import (
        dataset_home,
        save_document_subset,
    )
    from pypedeid.eval.runner import evaluate_pipeline
    from pypedeid.ingest.sources import load_annotated_corpus
    from pypedeid.risk import default_risk_profile, get_risk_profile
    from pypedeid.transform.ops import filter_documents_by_split_query

    settings = get_settings()

    # Early validation of save_sample_as (fail before running eval).
    if body.save_sample_as is not None:
        if body.eval_mode != "sample":
            raise HTTPException(
                status_code=422,
                detail="save_sample_as requires eval_mode == 'sample'.",
            )
        target_name = body.save_sample_as.dataset_name.strip()
        if not target_name:
            raise HTTPException(
                status_code=422,
                detail="save_sample_as.dataset_name is required.",
            )
        try:
            target_home = dataset_home(settings.corpora_dir, target_name)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if target_home.exists():
            raise HTTPException(
                status_code=409,
                detail=f"Dataset {target_name!r} already exists.",
            )

    # Load pipeline from filesystem
    try:
        config = load_pipeline_config(settings.pipelines_dir, body.pipeline_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        pipe_chain = load_pipeline(config)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"failed to build pipeline: {exc}"
        ) from exc

    # Load dataset — either from a registered dataset name or a raw path.
    dataset_source: str
    if body.dataset_name:
        from pypedeid.dataset_store import load_dataset_documents

        try:
            documents = load_dataset_documents(settings.corpora_dir, body.dataset_name)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"failed to load dataset: {exc}") from exc
        dataset_source = _eval_dataset_source_with_splits(
            f"dataset:{body.dataset_name}",
            body.dataset_splits,
        )
    elif body.dataset_path:
        # Scope dataset_path to the corpora root so admin callers can't read arbitrary
        # paths on the server. Use dataset_name for anything already registered.
        corpora_root = settings.corpora_dir.resolve()
        raw_path = Path(body.dataset_path)
        corpus_path = (
            raw_path.resolve()
            if raw_path.is_absolute()
            else (corpora_root / raw_path).resolve()
        )
        try:
            corpus_path.relative_to(corpora_root)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"dataset_path must stay under the corpora root ({corpora_root}); "
                    "use POST /datasets/import/* to register data outside that tree first."
                ),
            ) from exc
        if not corpus_path.exists():
            raise HTTPException(status_code=404, detail=f"dataset path not found: {body.dataset_path}")
        if corpus_path.suffix.lower() != ".jsonl":
            raise HTTPException(
                status_code=422,
                detail=(
                    "dataset_path must be a .jsonl file. "
                    "Convert BRAT to JSONL first (e.g. POST /datasets/import/brat or "
                    "`pypedeid dataset import-brat`)."
                ),
            )

        try:
            documents = load_annotated_corpus(jsonl=corpus_path)
        except Exception as exc:
            raise HTTPException(
                status_code=422, detail=f"failed to load dataset: {exc}"
            ) from exc
        dataset_source = _eval_dataset_source_with_splits(
            str(corpus_path),
            body.dataset_splits,
        )
    else:
        raise HTTPException(
            status_code=422, detail="Provide either dataset_name or dataset_path"
        )

    if not documents:
        raise HTTPException(status_code=422, detail="dataset is empty")

    if body.dataset_splits and any(str(s).strip() for s in body.dataset_splits):
        documents = filter_documents_by_split_query(documents, body.dataset_splits)
        if not documents:
            raise HTTPException(
                status_code=422,
                detail="No documents match dataset_splits; ensure metadata['split'] matches or adjust the filter.",
            )

    sample_info: dict[str, Any] | None = None
    if body.eval_mode == "sample":
        total_after_split = len(documents)
        if body.sample_size is None or body.sample_size < 1:
            raise HTTPException(
                status_code=422,
                detail="sample_size must be a positive integer when eval_mode == 'sample'.",
            )
        if body.sample_size > total_after_split:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"sample_size ({body.sample_size}) exceeds documents after splits "
                    f"({total_after_split})."
                ),
            )
        # Stable ordering by document id so (seed, size, source) → same subset.
        ordered = sorted(documents, key=lambda d: d.document.id)
        # 32-bit seeds fit safely in JS Number; 64-bit values would lose precision on
        # the client round-trip and silently break "copy-paste the seed to reproduce".
        seed_used = body.sample_seed if body.sample_seed is not None else secrets.randbits(32)
        documents = random.Random(seed_used).sample(ordered, body.sample_size)
        sample_info = {
            "eval_mode": "sample",
            "sample_size": body.sample_size,
            "sample_seed_used": seed_used,
            "sample_of_total": total_after_split,
        }

    # Run evaluation
    if body.risk_profile_name:
        try:
            eval_risk_profile = get_risk_profile(body.risk_profile_name)
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        eval_risk_profile = default_risk_profile()

    rem = body.eval_pred_label_remap
    result = evaluate_pipeline(
        pipe_chain, documents, risk_profile=eval_risk_profile, pred_label_remap=rem
    )

    # Optional: persist the sampled document list as a new registered dataset.
    if body.save_sample_as is not None and sample_info is not None:
        spec = body.save_sample_as
        provenance: dict[str, Any] = {
            "derived_from": body.dataset_name or body.dataset_path,
            "sample_seed": sample_info["sample_seed_used"],
            "sample_size": sample_info["sample_size"],
            "sample_of_total": sample_info["sample_of_total"],
            "source_eval_pipeline": body.pipeline_name,
        }
        if body.dataset_splits:
            provenance["source_splits"] = list(body.dataset_splits)
        try:
            save_document_subset(
                settings.corpora_dir,
                spec.dataset_name.strip(),
                documents,
                description=spec.description or "",
                metadata={"provenance": provenance},
            )
        except ValueError as exc:
            # Race condition: name collided between the pre-check and the write, or
            # something else rejected the subset. Surface as 409.
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        sample_info["saved_dataset_name"] = spec.dataset_name.strip()

    metrics = build_persisted_eval_metrics(
        result,
        risk_profile_name=eval_risk_profile.name,
        sample_info=sample_info,
        eval_pred_label_remap=rem,
    )

    # Persist eval result to filesystem
    result_path = save_eval_result(
        settings.evaluations_dir,
        pipeline_name=body.pipeline_name,
        dataset_source=dataset_source,
        metrics=metrics,
        document_count=result.document_count,
    )
    result_id = result_path.stem

    # Audit log
    try:
        import getpass

        record = AuditLogRecord(
            user=getpass.getuser(),
            command="eval",
            pipeline_name=body.pipeline_name,
            pipeline_config=config,
            dataset_source=dataset_source,
            doc_count=result.document_count,
            span_count=result.overall.strict.tp + result.overall.strict.fp,
            duration_seconds=0.0,
            metrics={
                "strict_f1": result.overall.strict.f1,
                "risk_weighted_recall": result.risk_weighted_recall,
            },
            source="api-admin",
        )
        session.add(record)
    except Exception:
        logger.warning("Failed to write eval audit log", exc_info=True)

    # Return result — read back the saved file for consistent id/created_at.
    # Per-document payload is attached **only to the response** (never persisted);
    # the eval JSON on disk stays small and free of raw document text.
    saved = load_eval_result(settings.evaluations_dir, result_id)
    if body.include_per_document or body.include_per_document_spans:
        saved.setdefault("metrics", {}).update(
            _build_document_level(
                result.document_results,
                include_spans=body.include_per_document_spans,
                limit=settings.eval_per_document_limit,
            )
        )
    return _data_to_detail(saved)


@router.get("/runs", response_model=list[EvalRunSummary])
def list_eval_runs(
    pipeline_name: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[EvalRunSummary]:
    """List past evaluation runs (from filesystem)."""
    settings = get_settings()
    results = list_eval_results(settings.evaluations_dir, pipeline_name=pipeline_name)
    # Apply offset/limit
    results = results[offset : offset + limit]
    return [_info_to_summary(r) for r in results]


@router.get("/runs/{run_id}", response_model=EvalRunDetail)
def get_eval_run(run_id: str) -> EvalRunDetail:
    """Get detailed metrics for an evaluation run."""
    settings = get_settings()
    try:
        data = load_eval_result(settings.evaluations_dir, run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _data_to_detail(data)


@router.post("/compare", response_model=EvalCompareResponse)
def compare_eval_runs(body: EvalCompareRequest) -> EvalCompareResponse:
    """Compare two evaluation runs side by side."""
    settings = get_settings()
    try:
        data_a = load_eval_result(settings.evaluations_dir, body.run_id_a)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"run {body.run_id_a!r} not found")
    try:
        data_b = load_eval_result(settings.evaluations_dir, body.run_id_b)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"run {body.run_id_b!r} not found")

    detail_a = _data_to_detail(data_a)
    detail_b = _data_to_detail(data_b)

    return EvalCompareResponse(
        run_a=detail_a,
        run_b=detail_b,
        delta_strict_f1=round(detail_b.strict_f1 - detail_a.strict_f1, 6),
        delta_risk_weighted_recall=round(
            detail_b.risk_weighted_recall - detail_a.risk_weighted_recall, 6
        ),
    )
