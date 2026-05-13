"""seqeval-based training metrics for use with HF Trainer."""

from __future__ import annotations

from typing import Any, Callable


def make_compute_metrics(id2label: dict[int, str]) -> Callable[[Any], dict[str, float]]:
    """Return a compute_metrics closure for HF Trainer."""

    def compute_metrics(eval_pred: Any) -> dict[str, float]:
        import numpy as np
        from seqeval.metrics import classification_report, f1_score, precision_score, recall_score

        logits, label_ids = eval_pred
        predictions = np.argmax(logits, axis=2)

        true_seqs: list[list[str]] = []
        pred_seqs: list[list[str]] = []

        for pred_row, label_row in zip(predictions, label_ids):
            true_seq: list[str] = []
            pred_seq: list[str] = []
            for pred_id, label_id in zip(pred_row, label_row):
                if label_id == -100:
                    continue
                true_seq.append(id2label.get(int(label_id), "O"))
                pred_seq.append(id2label.get(int(pred_id), "O"))
            true_seqs.append(true_seq)
            pred_seqs.append(pred_seq)

        result: dict[str, float] = {
            "eval_precision": precision_score(true_seqs, pred_seqs, zero_division=0),
            "eval_recall": recall_score(true_seqs, pred_seqs, zero_division=0),
            "eval_f1": f1_score(true_seqs, pred_seqs, zero_division=0),
        }

        report = classification_report(true_seqs, pred_seqs, output_dict=True, zero_division=0)
        for label, scores in report.items():
            if isinstance(scores, dict) and label not in ("micro avg", "macro avg", "weighted avg"):
                result[f"eval_{label}_f1"] = float(scores.get("f1-score", 0.0))

        return result

    return compute_metrics


def build_metrics_report(
    raw_logits: Any,
    raw_label_ids: Any,
    id2label: dict[int, str],
) -> dict[str, Any]:
    """Build the full metrics dict (overall + per_label) for the manifest."""
    import numpy as np
    from seqeval.metrics import classification_report, f1_score, precision_score, recall_score

    predictions = np.argmax(raw_logits, axis=2)

    true_seqs: list[list[str]] = []
    pred_seqs: list[list[str]] = []

    for pred_row, label_row in zip(predictions, raw_label_ids):
        true_seq: list[str] = []
        pred_seq: list[str] = []
        for pred_id, label_id in zip(pred_row, label_row):
            if label_id == -100:
                continue
            true_seq.append(id2label.get(int(label_id), "O"))
            pred_seq.append(id2label.get(int(pred_id), "O"))
        true_seqs.append(true_seq)
        pred_seqs.append(pred_seq)

    overall = {
        "precision": float(precision_score(true_seqs, pred_seqs, zero_division=0)),
        "recall": float(recall_score(true_seqs, pred_seqs, zero_division=0)),
        "f1": float(f1_score(true_seqs, pred_seqs, zero_division=0)),
    }

    report = classification_report(true_seqs, pred_seqs, output_dict=True, zero_division=0)
    per_label: dict[str, Any] = {}
    for label, scores in report.items():
        if isinstance(scores, dict) and label not in ("micro avg", "macro avg", "weighted avg"):
            per_label[label] = {
                "precision": float(scores.get("precision", 0.0)),
                "recall": float(scores.get("recall", 0.0)),
                "f1": float(scores.get("f1-score", 0.0)),
                "support": int(scores.get("support", 0)),
            }

    return {"overall": overall, "per_label": per_label, "confusion": None}
