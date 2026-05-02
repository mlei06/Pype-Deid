"""Multi-mode span matching (SemEval partial matching scheme).

Four matching modes:
- **Strict**: exact (start, end, label) match
- **Exact boundary**: exact (start, end), any label
- **Partial overlap**: spans overlap AND same label
- **Character-level**: per-character B/I/O tags compared
"""

from __future__ import annotations

from dataclasses import dataclass

from clinical_deid.domain import EntitySpan


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MatchResult:
    """Metrics for a single matching mode."""

    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int
    partial: int = 0  # only for partial mode: count of partial matches


@dataclass
class EvalMetrics:
    """All matching modes computed together."""

    strict: MatchResult
    exact_boundary: MatchResult
    partial_overlap: MatchResult
    token_level: MatchResult


@dataclass(frozen=True)
class MacroAverage:
    """Unweighted mean of per-label precision/recall/F1 for one matching mode."""

    precision: float
    recall: float
    f1: float
    label_count: int


@dataclass
class MacroMetrics:
    """Macro averages across all labels.

    Excludes ``exact_boundary`` (which ignores label, so a per-label macro is
    not meaningful for it).
    """

    strict: MacroAverage
    partial_overlap: MacroAverage
    token_level: MacroAverage


@dataclass(frozen=True)
class LabelMetrics:
    """Per-label metrics across matching modes."""

    label: str
    strict: MatchResult
    partial_overlap: MatchResult
    token_level: MatchResult
    support: int  # number of gold spans for this label


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    return prec, rec, f1


def make_match_result(tp: int, fp: int, fn: int, partial: int = 0) -> MatchResult:
    prec, rec, f1 = prf(tp, fp, fn)
    return MatchResult(precision=prec, recall=rec, f1=f1, tp=tp, fp=fp, fn=fn, partial=partial)


def macro_average(results: list[MatchResult]) -> MacroAverage:
    """Unweighted mean of P/R/F1 across per-label results.

    Empty input yields zeros — surfaces "no labels evaluated" cleanly to the UI
    rather than raising.
    """
    n = len(results)
    if n == 0:
        return MacroAverage(precision=0.0, recall=0.0, f1=0.0, label_count=0)
    return MacroAverage(
        precision=sum(r.precision for r in results) / n,
        recall=sum(r.recall for r in results) / n,
        f1=sum(r.f1 for r in results) / n,
        label_count=n,
    )


def _spans_overlap(a: EntitySpan, b: EntitySpan) -> bool:
    return a.start < b.end and b.start < a.end


def _overlap_chars(a: EntitySpan, b: EntitySpan) -> int:
    return max(0, min(a.end, b.end) - max(a.start, b.start))


# ---------------------------------------------------------------------------
# Strict matching
# ---------------------------------------------------------------------------


def _strict_match(pred: list[EntitySpan], gold: list[EntitySpan]) -> MatchResult:
    pred_set = {(s.start, s.end, s.label) for s in pred}
    gold_set = {(s.start, s.end, s.label) for s in gold}
    tp = len(pred_set & gold_set)
    fp = len(pred_set - gold_set)
    fn = len(gold_set - pred_set)
    return make_match_result(tp, fp, fn)


# ---------------------------------------------------------------------------
# Exact boundary matching (ignore label)
# ---------------------------------------------------------------------------


def _exact_boundary_match(pred: list[EntitySpan], gold: list[EntitySpan]) -> MatchResult:
    pred_set = {(s.start, s.end) for s in pred}
    gold_set = {(s.start, s.end) for s in gold}
    tp = len(pred_set & gold_set)
    fp = len(pred_set - gold_set)
    fn = len(gold_set - pred_set)
    return make_match_result(tp, fp, fn)


# ---------------------------------------------------------------------------
# Partial overlap matching (same label required)
# ---------------------------------------------------------------------------


def _partial_overlap_match(pred: list[EntitySpan], gold: list[EntitySpan]) -> MatchResult:
    """Spans overlap AND share the same label = match; greedy assignment.

    Walks predicted spans in input order and assigns each one to the unmatched
    gold span (same label) with the largest character overlap. Order-dependent:
    different pred orderings can yield different TP/FP/FN.
    """
    gold_matched: set[int] = set()
    pred_matched: set[int] = set()
    partial_count = 0

    pred_indexed = list(enumerate(pred))
    gold_indexed = list(enumerate(gold))

    for pi, ps in pred_indexed:
        best_gi: int | None = None
        best_overlap = 0
        for gi, gs in gold_indexed:
            if gi in gold_matched:
                continue
            if ps.label != gs.label:
                continue
            overlap = _overlap_chars(ps, gs)
            if overlap > best_overlap:
                best_overlap = overlap
                best_gi = gi
        if best_gi is not None:
            pred_matched.add(pi)
            gold_matched.add(best_gi)
            # Check if it's a partial (not exact) match
            gs = gold[best_gi]
            if not (ps.start == gs.start and ps.end == gs.end):
                partial_count += 1

    tp = len(pred_matched)
    fp = len(pred) - tp
    fn = len(gold) - len(gold_matched)
    return make_match_result(tp, fp, fn, partial=partial_count)


# ---------------------------------------------------------------------------
# Token-level matching (BIO tagging)
# ---------------------------------------------------------------------------


def _spans_to_char_tags(
    spans: list[EntitySpan], text_length: int
) -> list[str]:
    """Convert spans to per-character BIO-like tags.

    Returns a list of length *text_length* where each entry is ``"O"`` or
    ``"B-LABEL"`` / ``"I-LABEL"``.
    """
    tags = ["O"] * text_length
    # Sort spans by start, then by descending length (longer wins on overlap)
    sorted_spans = sorted(spans, key=lambda s: (s.start, -(s.end - s.start)))
    for s in sorted_spans:
        for i in range(s.start, min(s.end, text_length)):
            if tags[i] == "O":
                tag = f"B-{s.label}" if i == s.start else f"I-{s.label}"
                tags[i] = tag
    return tags


def _char_level_match(
    pred: list[EntitySpan], gold: list[EntitySpan], text_length: int
) -> MatchResult:
    """Per-character B/I/O comparison."""
    if text_length == 0:
        return make_match_result(0, 0, 0)

    pred_tags = _spans_to_char_tags(pred, text_length)
    gold_tags = _spans_to_char_tags(gold, text_length)

    tp = fp = fn = 0
    for pt, gt in zip(pred_tags, gold_tags):
        if pt != "O" and gt != "O":
            if pt == gt:
                tp += 1
            else:
                fp += 1
                fn += 1
        elif pt != "O":
            fp += 1
        elif gt != "O":
            fn += 1

    return make_match_result(tp, fp, fn)


# ---------------------------------------------------------------------------
# Combined computation
# ---------------------------------------------------------------------------


def compute_metrics(
    pred_spans: list[EntitySpan],
    gold_spans: list[EntitySpan],
    text: str,
) -> EvalMetrics:
    """Compute all four matching modes for a single document."""
    return EvalMetrics(
        strict=_strict_match(pred_spans, gold_spans),
        exact_boundary=_exact_boundary_match(pred_spans, gold_spans),
        partial_overlap=_partial_overlap_match(pred_spans, gold_spans),
        token_level=_char_level_match(pred_spans, gold_spans, len(text)),
    )


def compute_per_label_metrics(
    pred_spans: list[EntitySpan],
    gold_spans: list[EntitySpan],
    text: str,
) -> list[LabelMetrics]:
    """Compute per-label metrics across all matching modes."""
    all_labels = sorted(
        {s.label for s in pred_spans} | {s.label for s in gold_spans}
    )
    results: list[LabelMetrics] = []
    for label in all_labels:
        p = [s for s in pred_spans if s.label == label]
        g = [s for s in gold_spans if s.label == label]
        strict = _strict_match(p, g)
        partial = _partial_overlap_match(p, g)
        token = _char_level_match(p, g, len(text))
        results.append(
            LabelMetrics(
                label=label,
                strict=strict,
                partial_overlap=partial,
                token_level=token,
                support=len(g),
            )
        )
    return results
