"""Serialize :class:`EvalResult` to the ``metrics`` object stored in eval JSON files."""

from __future__ import annotations

from typing import Any

from clinical_deid.eval.runner import EvalResult


def match_result_to_dict(mr) -> dict[str, Any]:
    return {
        "precision": mr.precision,
        "recall": mr.recall,
        "f1": mr.f1,
        "tp": mr.tp,
        "fp": mr.fp,
        "fn": mr.fn,
    }


def eval_metrics_to_dict(em) -> dict[str, Any]:
    return {
        "strict": match_result_to_dict(em.strict),
        "exact_boundary": match_result_to_dict(em.exact_boundary),
        "partial_overlap": match_result_to_dict(em.partial_overlap),
        "token_level": match_result_to_dict(em.token_level),
    }


def macro_average_to_dict(ma) -> dict[str, Any]:
    return {
        "precision": ma.precision,
        "recall": ma.recall,
        "f1": ma.f1,
        "label_count": ma.label_count,
    }


def macro_metrics_to_dict(mm) -> dict[str, Any]:
    return {
        "strict": macro_average_to_dict(mm.strict),
        "partial_overlap": macro_average_to_dict(mm.partial_overlap),
        "token_level": macro_average_to_dict(mm.token_level),
    }


def redaction_metrics_to_dict(rm) -> dict[str, Any]:
    return {
        "gold_phi_count": rm.gold_phi_count,
        "leaked_phi_count": rm.leaked_phi_count,
        "leakage_rate": rm.leakage_rate,
        "redaction_recall": rm.redaction_recall,
        "over_redaction_chars": rm.over_redaction_chars,
        "original_length": rm.original_length,
        "redacted_length": rm.redacted_length,
        "per_label": [
            {
                "label": ll.label,
                "gold_count": ll.gold_count,
                "leaked_count": ll.leaked_count,
                "leakage_rate": ll.leakage_rate,
            }
            for ll in rm.per_label
        ],
        "leaked_spans": [
            {
                "label": ls.label,
                "original_text": ls.original_text,
                "found_at": ls.found_at,
            }
            for ls in rm.leaked_spans
        ],
    }


def build_persisted_eval_metrics(
    result: EvalResult,
    *,
    risk_profile_name: str,
    sample_info: dict[str, Any] | None = None,
    eval_pred_label_remap: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the ``metrics`` object written by :func:`clinical_deid.eval_store.save_eval_result`."""
    per_label_dict: dict[str, Any] = {}
    for label, lm in result.per_label.items():
        per_label_dict[label] = {
            "strict": match_result_to_dict(lm.strict),
            "partial_overlap": match_result_to_dict(lm.partial_overlap),
            "token_level": match_result_to_dict(lm.token_level),
            "support": lm.support,
        }

    metrics: dict[str, Any] = {
        "overall": eval_metrics_to_dict(result.overall),
        "macro": macro_metrics_to_dict(result.macro),
        "per_label": per_label_dict,
        "risk_weighted_recall": result.risk_weighted_recall,
        "label_confusion": result.label_confusion,
        "has_redaction": result.has_redaction,
        "risk_profile_name": risk_profile_name,
    }

    if result.redaction is not None:
        metrics["redaction"] = redaction_metrics_to_dict(result.redaction)

    if sample_info is not None:
        metrics["sample"] = sample_info

    if eval_pred_label_remap:
        metrics["eval_pred_label_remap"] = dict(eval_pred_label_remap)

    return metrics
