"""Evaluation runner — batch evaluation with per-label, per-document, and confusion matrix results.

Compares predicted spans against gold spans (standard NER evaluation).
Pipelines only produce spans; redaction is applied separately at the API layer.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from clinical_deid.domain import AnnotatedDocument, EntitySpan
from clinical_deid.eval.matching import (
    EvalMetrics,
    LabelMetrics,
    MacroMetrics,
    MatchResult,
    compute_metrics,
    compute_per_label_metrics,
    macro_average,
    make_match_result,
)
from clinical_deid.eval.redaction import LabelLeakage, RedactionMetrics, compute_redaction_metrics
from clinical_deid.pipes.base import Pipe
from clinical_deid.risk import RiskProfile, default_risk_profile


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DocumentEvalResult:
    """Evaluation result for a single document."""

    document_id: str
    metrics: EvalMetrics
    per_label: list[LabelMetrics]
    false_negatives: list[EntitySpan]
    false_positives: list[EntitySpan]
    risk_weighted_recall: float
    redaction: RedactionMetrics | None = None
    #: Gold document text, carried on the result so callers that want to render
    #: per-document views (e.g. the Evaluate UI) don't need a separate lookup.
    #: In-memory only; never serialized to the eval JSON file.
    text: str = ""
    #: Gold spans as seen by the runner (copy preserves ordering at eval time).
    gold_spans: list[EntitySpan] = field(default_factory=list)
    #: Predicted spans produced by the pipeline for this document.
    pred_spans: list[EntitySpan] = field(default_factory=list)


@dataclass
class EvalResult:
    """Aggregate evaluation result across all documents."""

    overall: EvalMetrics
    macro: MacroMetrics
    per_label: dict[str, LabelMetrics]
    risk_weighted_recall: float
    document_results: list[DocumentEvalResult]
    document_count: int
    label_confusion: dict[str, dict[str, int]]
    redaction: RedactionMetrics | None = None
    has_redaction: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_false_negatives(
    pred_spans: list[EntitySpan], gold_spans: list[EntitySpan]
) -> list[EntitySpan]:
    """Gold spans not matched (exact start, end, label) by any prediction."""
    pred_set = {(s.start, s.end, s.label) for s in pred_spans}
    return [s for s in gold_spans if (s.start, s.end, s.label) not in pred_set]


def _compute_false_positives(
    pred_spans: list[EntitySpan], gold_spans: list[EntitySpan]
) -> list[EntitySpan]:
    """Predicted spans not matched by any gold span."""
    gold_set = {(s.start, s.end, s.label) for s in gold_spans}
    return [s for s in pred_spans if (s.start, s.end, s.label) not in gold_set]


def _build_confusion_matrix(
    pred_spans: list[EntitySpan], gold_spans: list[EntitySpan]
) -> dict[str, dict[str, int]]:
    """Build label confusion matrix from overlapping pred/gold spans.

    Returns ``{gold_label: {pred_label: count}}`` where each gold span
    contributes exactly one cell (the predicted label of its best-overlap pred,
    or ``"<MISSED>"`` if nothing overlaps). Predicted spans that match no gold
    are aggregated under the synthetic ``"<SPURIOUS>"`` row, so the matrix
    surfaces both misses and hallucinations.
    """
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    pred_matched: set[int] = set()

    for gs in gold_spans:
        best_pi: int | None = None
        best_overlap = 0
        for pi, ps in enumerate(pred_spans):
            overlap = max(0, min(gs.end, ps.end) - max(gs.start, ps.start))
            if overlap > best_overlap:
                best_overlap = overlap
                best_pi = pi
        if best_pi is None:
            confusion[gs.label]["<MISSED>"] += 1
        else:
            confusion[gs.label][pred_spans[best_pi].label] += 1
            pred_matched.add(best_pi)

    for pi, ps in enumerate(pred_spans):
        if pi not in pred_matched:
            confusion["<SPURIOUS>"][ps.label] += 1

    return {k: dict(v) for k, v in confusion.items()}


def _aggregate_match_results(results: list[MatchResult]) -> MatchResult:
    """Sum TP/FP/FN across results and recompute P/R/F1."""
    tp = sum(r.tp for r in results)
    fp = sum(r.fp for r in results)
    fn = sum(r.fn for r in results)
    partial = sum(r.partial for r in results)
    return make_match_result(tp, fp, fn, partial)


def _remap_pred_span_labels(
    pred_spans: list[EntitySpan], mapping: dict[str, str] | None
) -> list[EntitySpan]:
    """Rename predicted span labels (POST /eval/run ``eval_pred_label_remap``), preserving offsets."""
    if not mapping:
        return pred_spans
    out: list[EntitySpan] = []
    for s in pred_spans:
        if s.label in mapping and mapping[s.label] != s.label:
            out.append(s.model_copy(update={"label": mapping[s.label]}))
        else:
            out.append(s)
    return out



def _aggregate_redaction_metrics(doc_metrics: list[RedactionMetrics]) -> RedactionMetrics:
    """Aggregate per-document redaction metrics into a corpus-level summary."""
    total_gold = sum(m.gold_phi_count for m in doc_metrics)
    total_leaked = sum(m.leaked_phi_count for m in doc_metrics)
    total_orig_len = sum(m.original_length for m in doc_metrics)
    total_redacted_len = sum(m.redacted_length for m in doc_metrics)
    total_over_redaction = sum(m.over_redaction_chars for m in doc_metrics)

    leakage_rate = total_leaked / total_gold if total_gold > 0 else 0.0

    # Aggregate per-label
    gold_by_label: Counter[str] = Counter()
    leaked_by_label: Counter[str] = Counter()
    for m in doc_metrics:
        for ll in m.per_label:
            gold_by_label[ll.label] += ll.gold_count
            leaked_by_label[ll.label] += ll.leaked_count

    per_label = []
    for label in sorted(gold_by_label):
        gc = gold_by_label[label]
        lc = leaked_by_label.get(label, 0)
        per_label.append(LabelLeakage(
            label=label,
            gold_count=gc,
            leaked_count=lc,
            leakage_rate=round(lc / gc, 6) if gc > 0 else 0.0,
        ))

    # Collect all leaked spans across docs
    all_leaked = []
    for m in doc_metrics:
        all_leaked.extend(m.leaked_spans)

    return RedactionMetrics(
        gold_phi_count=total_gold,
        leaked_phi_count=total_leaked,
        leakage_rate=round(leakage_rate, 6),
        redaction_recall=round(1.0 - leakage_rate, 6),
        per_label=per_label,
        leaked_spans=all_leaked,
        over_redaction_chars=total_over_redaction,
        original_length=total_orig_len,
        redacted_length=total_redacted_len,
    )


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def evaluate_pipeline(
    pipeline: Pipe,
    documents: list[AnnotatedDocument],
    risk_weights: dict[str, float] | None = None,
    risk_profile: RiskProfile | None = None,
    pred_label_remap: dict[str, str] | None = None,
) -> EvalResult:
    """Run pipeline on each doc, compute all metrics, sort docs by worst performance.

    Each document in *documents* is treated as a gold-standard reference.
    The pipeline is run on a clean copy (no spans), and results are compared
    on **raw** span label strings (no :func:`normalize_entity_spans`). Align
    gold and pipeline output via the pipeline (e.g. ``label_mapper``) or the
    corpus so labels match; see docs/configuration.md (label normalization applies
    to ``POST /process/*`` only, not to eval).

    *pred_label_remap*, when set, renames **predicted** span labels right after
    :meth:`Pipe.forward` (same as an ad-hoc label_mapper) so eval can proceed
    without editing the saved pipeline.

    If the pipeline's output text differs from the input (indicating redaction),
    redaction metrics are also computed.

    Pass *risk_profile* to use a named pack (coverage scheme + weights) for
    risk-weighted recall. *risk_weights* overrides only the weights dict and is
    kept for back-compat; new callers should prefer ``risk_profile``.

    When *risk_weights* and *risk_profile* are both omitted, the active profile
    is :func:`~clinical_deid.risk.default_risk_profile` (``CLINICAL_DEID_RISK_PROFILE_NAME``,
    default ``clinical_phi``).
    """
    # Resolve weighting: explicit weights > explicit profile > settings default.
    if risk_weights is not None:
        profile = RiskProfile(name="adhoc", weights=risk_weights, default_weight=1.0)
    else:
        profile = risk_profile or default_risk_profile()
    doc_results: list[DocumentEvalResult] = []
    all_fn: list[EntitySpan] = []
    all_gold: list[EntitySpan] = []

    # Per-mode accumulators
    strict_results: list[MatchResult] = []
    exact_boundary_results: list[MatchResult] = []
    partial_results: list[MatchResult] = []
    token_results: list[MatchResult] = []

    # Per-label accumulators (label → list of LabelMetrics)
    per_label_acc: dict[str, list[LabelMetrics]] = defaultdict(list)

    # Confusion matrix accumulator
    total_confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    # Redaction metrics accumulators
    doc_redaction_metrics: list[RedactionMetrics] = []
    has_redaction = False

    for gold_doc in documents:
        # Run pipeline on clean document (no spans)
        clean = AnnotatedDocument(document=gold_doc.document, spans=[])
        pred_doc = pipeline.forward(clean)

        text = gold_doc.document.text
        gold_spans = list(gold_doc.spans)
        pred_spans = _remap_pred_span_labels(list(pred_doc.spans), pred_label_remap)

        # Detect redaction: output text differs from input
        is_redacted = pred_doc.document.text != text

        # Compute detection metrics
        metrics = compute_metrics(pred_spans, gold_spans, text)
        label_metrics = compute_per_label_metrics(pred_spans, gold_spans, text)

        # False negatives / positives
        fn = _compute_false_negatives(pred_spans, gold_spans)
        fp = _compute_false_positives(pred_spans, gold_spans)
        rwr = profile.risk_weighted_recall(fn, gold_spans)

        # Compute redaction metrics if text was transformed
        doc_redaction: RedactionMetrics | None = None
        if is_redacted:
            has_redaction = True
            gold_span_dicts = [
                {"start": s.start, "end": s.end, "label": s.label}
                for s in gold_spans
            ]
            doc_redaction = compute_redaction_metrics(
                original_text=text,
                redacted_text=pred_doc.document.text,
                gold_spans=gold_span_dicts,
            )
            doc_redaction_metrics.append(doc_redaction)

        doc_results.append(
            DocumentEvalResult(
                document_id=gold_doc.document.id,
                metrics=metrics,
                per_label=label_metrics,
                false_negatives=fn,
                false_positives=fp,
                risk_weighted_recall=rwr,
                redaction=doc_redaction,
                text=text,
                gold_spans=gold_spans,
                pred_spans=pred_spans,
            )
        )

        # Accumulate
        strict_results.append(metrics.strict)
        exact_boundary_results.append(metrics.exact_boundary)
        partial_results.append(metrics.partial_overlap)
        token_results.append(metrics.token_level)
        all_fn.extend(fn)
        all_gold.extend(gold_spans)

        for lm in label_metrics:
            per_label_acc[lm.label].append(lm)

        # Confusion
        doc_confusion = _build_confusion_matrix(pred_spans, gold_spans)
        for gl, pred_map in doc_confusion.items():
            for pl, count in pred_map.items():
                total_confusion[gl][pl] += count

    # Sort documents by worst strict F1 first. Tie-break: empty (no gold and
    # no pred) docs sink to the bottom — their F1=0.0 is noise, not failure —
    # and among real failures, surface higher-support docs ahead of one-off ties.
    def _worst_doc_key(d: DocumentEvalResult) -> tuple[int, float, int]:
        s = d.metrics.strict
        no_signal = (s.tp + s.fp + s.fn) == 0
        return (1 if no_signal else 0, s.f1, -len(d.gold_spans))

    doc_results.sort(key=_worst_doc_key)

    # Aggregate overall metrics
    overall = EvalMetrics(
        strict=_aggregate_match_results(strict_results),
        exact_boundary=_aggregate_match_results(exact_boundary_results),
        partial_overlap=_aggregate_match_results(partial_results),
        token_level=_aggregate_match_results(token_results),
    )

    # Aggregate per-label
    agg_per_label: dict[str, LabelMetrics] = {}
    for label, lm_list in sorted(per_label_acc.items()):
        strict_agg = _aggregate_match_results([lm.strict for lm in lm_list])
        partial_agg = _aggregate_match_results([lm.partial_overlap for lm in lm_list])
        token_agg = _aggregate_match_results([lm.token_level for lm in lm_list])
        support = sum(lm.support for lm in lm_list)
        agg_per_label[label] = LabelMetrics(
            label=label,
            strict=strict_agg,
            partial_overlap=partial_agg,
            token_level=token_agg,
            support=support,
        )

    total_rwr = profile.risk_weighted_recall(all_fn, all_gold)

    # Macro averages — unweighted mean of per-label P/R/F1, so rare labels
    # aren't drowned out by frequent ones (NAME, DATE) the way micro-F1 hides them.
    macro = MacroMetrics(
        strict=macro_average([lm.strict for lm in agg_per_label.values()]),
        partial_overlap=macro_average([lm.partial_overlap for lm in agg_per_label.values()]),
        token_level=macro_average([lm.token_level for lm in agg_per_label.values()]),
    )

    # Aggregate redaction metrics
    agg_redaction: RedactionMetrics | None = None
    if doc_redaction_metrics:
        agg_redaction = _aggregate_redaction_metrics(doc_redaction_metrics)

    return EvalResult(
        overall=overall,
        macro=macro,
        per_label=agg_per_label,
        risk_weighted_recall=total_rwr,
        document_results=doc_results,
        document_count=len(documents),
        label_confusion={k: dict(v) for k, v in total_confusion.items()},
        redaction=agg_redaction,
        has_redaction=has_redaction,
    )
