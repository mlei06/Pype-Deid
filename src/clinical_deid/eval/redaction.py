"""Redaction quality evaluation — measures whether PHI was successfully removed from output text.

Complements span-based detection metrics by answering:
"Does any gold-standard PHI still appear verbatim in the redacted output?"
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher


@dataclass(frozen=True)
class LeakedSpan:
    """A gold PHI string that still appears in the redacted text."""

    label: str
    original_text: str
    found_at: list[int]  # character offsets where it was found in redacted text


@dataclass(frozen=True)
class LabelLeakage:
    """Per-label leakage summary (per-occurrence counts)."""

    label: str
    gold_count: int
    leaked_count: int
    leakage_rate: float  # leaked_count / gold_count


@dataclass
class RedactionMetrics:
    """Aggregate redaction quality metrics for a document or corpus.

    Counts are per-occurrence: a PHI string appearing 3x in the original with 1
    surviving copy in the redacted output is reported as 3 gold / 1 leaked.
    """

    gold_phi_count: int
    leaked_phi_count: int
    leakage_rate: float  # leaked / gold (0.0 = perfect, 1.0 = nothing redacted)
    redaction_recall: float  # 1 - leakage_rate
    per_label: list[LabelLeakage] = field(default_factory=list)
    leaked_spans: list[LeakedSpan] = field(default_factory=list)
    over_redaction_chars: int = 0  # non-PHI chars from original that were deleted/replaced
    original_length: int = 0
    redacted_length: int = 0


def _find_all(haystack: str, needle: str) -> list[int]:
    """Find all (overlapping) occurrences of *needle* in *haystack*."""
    positions: list[int] = []
    if not needle:
        return positions
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx == -1:
            break
        positions.append(idx)
        start = idx + 1
    return positions


def _phi_char_mask(original_text: str, gold_spans: list[dict]) -> set[int]:
    mask: set[int] = set()
    text_len = len(original_text)
    for span in gold_spans:
        start = max(0, span["start"])
        end = min(span["end"], text_len)
        for i in range(start, end):
            mask.add(i)
    return mask


def _over_redaction_chars(
    original_text: str, redacted_text: str, gold_spans: list[dict]
) -> int:
    """Count non-PHI characters from *original_text* that were deleted or replaced.

    Uses :class:`difflib.SequenceMatcher` to identify ``delete`` and ``replace``
    opcodes in the original side, then subtracts any character inside a gold
    span (those are *expected* to be removed). The remainder is a real signal
    of over-redaction — it does not depend on whether the redaction is shorter
    or longer than the original.
    """
    if not original_text:
        return 0
    phi_chars = _phi_char_mask(original_text, gold_spans)
    matcher = SequenceMatcher(a=original_text, b=redacted_text, autojunk=False)
    over = 0
    for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
        if tag in ("delete", "replace"):
            for i in range(i1, i2):
                if i not in phi_chars:
                    over += 1
    return over


def compute_redaction_metrics(
    original_text: str,
    redacted_text: str,
    gold_spans: list[dict],
) -> RedactionMetrics:
    """Evaluate redaction quality by checking if gold PHI strings leak into the redacted text.

    Parameters
    ----------
    original_text
        The original document text before any redaction.
    redacted_text
        The pipeline output text (after redaction/surrogate replacement).
    gold_spans
        Gold-standard PHI spans as dicts with ``start``, ``end``, ``label`` keys.
        These reference positions in *original_text*.
    """
    if not gold_spans:
        return RedactionMetrics(
            gold_phi_count=0,
            leaked_phi_count=0,
            leakage_rate=0.0,
            redaction_recall=1.0,
            over_redaction_chars=_over_redaction_chars(original_text, redacted_text, []),
            original_length=len(original_text),
            redacted_length=len(redacted_text),
        )

    # Group gold spans into (text, label) buckets and count occurrences.
    bucket_gold: Counter[tuple[str, str]] = Counter()
    for span in gold_spans:
        start, end, label = span["start"], span["end"], span["label"]
        phi_text = original_text[start:end]
        if not phi_text.strip():
            continue
        bucket_gold[(phi_text, label)] += 1

    redacted_lower = redacted_text.lower()
    leaked_spans: list[LeakedSpan] = []
    bucket_leaked: dict[tuple[str, str], int] = {}

    for (phi_text, label), gold_count in bucket_gold.items():
        positions = _find_all(redacted_lower, phi_text.lower())
        # Leaks are bounded by gold occurrences — extra incidental matches in
        # the redacted text shouldn't exceed how often the PHI actually appeared.
        leaked = min(gold_count, len(positions))
        bucket_leaked[(phi_text, label)] = leaked
        if leaked > 0:
            leaked_spans.append(
                LeakedSpan(label=label, original_text=phi_text, found_at=positions[:leaked])
            )

    total_gold = sum(bucket_gold.values())
    total_leaked = sum(bucket_leaked.values())
    leakage_rate = total_leaked / total_gold if total_gold > 0 else 0.0

    gold_by_label: Counter[str] = Counter()
    leaked_by_label: Counter[str] = Counter()
    for (_phi_text, label), gold_count in bucket_gold.items():
        gold_by_label[label] += gold_count
        leaked_by_label[label] += bucket_leaked.get((_phi_text, label), 0)

    per_label = []
    for label in sorted(gold_by_label):
        gc = gold_by_label[label]
        lc = leaked_by_label.get(label, 0)
        per_label.append(LabelLeakage(
            label=label,
            gold_count=gc,
            leaked_count=lc,
            leakage_rate=lc / gc if gc > 0 else 0.0,
        ))

    return RedactionMetrics(
        gold_phi_count=total_gold,
        leaked_phi_count=total_leaked,
        leakage_rate=round(leakage_rate, 6),
        redaction_recall=round(1.0 - leakage_rate, 6),
        per_label=per_label,
        leaked_spans=leaked_spans,
        over_redaction_chars=_over_redaction_chars(original_text, redacted_text, gold_spans),
        original_length=len(original_text),
        redacted_length=len(redacted_text),
    )
