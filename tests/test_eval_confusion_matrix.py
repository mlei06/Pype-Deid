"""Tests for the label confusion matrix produced by the eval runner."""

from __future__ import annotations

from clinical_deid.domain import EntitySpan
from clinical_deid.eval.runner import _build_confusion_matrix


def _span(start: int, end: int, label: str) -> EntitySpan:
    return EntitySpan(start=start, end=end, label=label)


def test_each_gold_counted_once_even_with_multiple_overlapping_preds():
    """A gold span overlapping two preds contributes one cell (best overlap)."""
    gold = [_span(0, 10, "NAME")]
    pred = [_span(0, 4, "NAME"), _span(5, 10, "ADDR")]  # second has bigger overlap
    confusion = _build_confusion_matrix(pred, gold)
    # Best overlap is the ADDR pred (overlap=5 vs 4), so the confusion cell is NAME->ADDR.
    assert confusion["NAME"] == {"ADDR": 1}


def test_unmatched_pred_lands_in_spurious_row():
    """Predicted spans with no gold overlap show up under <SPURIOUS>."""
    gold = [_span(0, 5, "NAME")]
    pred = [_span(0, 5, "NAME"), _span(20, 30, "PHONE")]
    confusion = _build_confusion_matrix(pred, gold)
    assert confusion["NAME"] == {"NAME": 1}
    assert confusion["<SPURIOUS>"] == {"PHONE": 1}


def test_missed_gold_lands_in_missed_column():
    """Gold spans with no overlapping pred remain in the <MISSED> column."""
    gold = [_span(0, 5, "NAME"), _span(10, 15, "DATE")]
    pred = [_span(0, 5, "NAME")]
    confusion = _build_confusion_matrix(pred, gold)
    assert confusion["NAME"] == {"NAME": 1}
    assert confusion["DATE"] == {"<MISSED>": 1}
    assert "<SPURIOUS>" not in confusion


def test_empty_inputs_return_empty_matrix():
    assert _build_confusion_matrix([], []) == {}
