"""LLM-driven synthetic dataset generation."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException

from clinical_deid.api.routers.datasets import router
from clinical_deid.api.routers.datasets.helpers import (
    corpora_dir,
    manifest_to_detail,
)
from clinical_deid.api.routers.datasets.schemas import DatasetDetail, GenerateRequest
from clinical_deid.config import get_settings
from clinical_deid.dataset_store import (
    CORPUS_JSONL_NAME,
    commit_colocated_dataset,
    list_datasets,
    validate_name as validate_dataset_name,
)

logger = logging.getLogger(__name__)


@router.post("/generate", response_model=DatasetDetail, status_code=201)
def generate_dataset(body: GenerateRequest) -> DatasetDetail:
    """Generate synthetic annotated clinical notes via LLM and register as a dataset.

    Uses the configured OpenAI-compatible endpoint (see ``OPENAI_API_KEY`` / settings).
    Each generated note is aligned to produce character-level PHI spans.
    """
    from clinical_deid.ingest.sink import write_annotated_corpus
    from clinical_deid.synthesis.document import synthesis_result_to_annotated_document
    from clinical_deid.synthesis.synthesizer import LLMSynthesizer

    corp = corpora_dir()
    settings = get_settings()

    try:
        validate_dataset_name(body.output_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = [d.name for d in list_datasets(corp)]
    if body.output_name in existing:
        raise HTTPException(status_code=409, detail=f"Dataset {body.output_name!r} already exists")

    try:
        llm = settings.openai_chat_client()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    synthesizer = LLMSynthesizer(
        llm=llm,
        phi_types=body.phi_types,
        examples=[],
        special_rules=body.special_rules,
    )

    docs: list[Any] = []
    errors: list[dict[str, Any]] = []
    for i in range(body.count):
        doc_id = f"synth_{i + 1:04d}"
        try:
            result = synthesizer.generate_one(**body.llm_kwargs)
            ad = synthesis_result_to_annotated_document(
                result,
                document_id=doc_id,
                metadata={"source": "llm_synthesis", "index": i},
            )
            docs.append(ad)
        except Exception as exc:
            logger.warning("Generation failed for doc %s: %s", doc_id, exc)
            errors.append({"doc_id": doc_id, "error": str(exc)})

    if not docs:
        raise HTTPException(
            status_code=500,
            detail=f"All {body.count} generation attempts failed. Errors: {errors[:5]}",
        )

    home = settings.corpora_dir / body.output_name
    home.mkdir(parents=True)
    output_path = home / CORPUS_JSONL_NAME
    write_annotated_corpus(docs, jsonl=output_path)

    provenance: dict[str, Any] = {
        "generated": True,
        "requested_count": body.count,
        "actual_count": len(docs),
        "phi_types": body.phi_types,
        "error_count": len(errors),
    }
    if errors:
        provenance["sample_errors"] = errors[:5]

    manifest = commit_colocated_dataset(
        settings.corpora_dir,
        body.output_name,
        "jsonl",
        description=body.description or f"LLM-generated synthetic data ({len(docs)} notes)",
        metadata={"provenance": provenance},
    )
    return manifest_to_detail(manifest)
