import { diffSpans } from './traceDiff';
import type { EntitySpanResponse } from '../api/types';

export interface PairSummary {
  /** Spans (start,end,label) present in BOTH a and b. */
  agreed: number;
  /** Only in a. */
  onlyA: number;
  /** Only in b. */
  onlyB: number;
  /** Same (start,end) but different label. */
  relabeled: number;
}

/**
 * Pairwise summary between two pipelines on the same text. ``agreed`` /
 * ``onlyA`` / ``onlyB`` use exact (start,end,label) keys via ``diffSpans``;
 * ``relabeled`` counts ranges that match by (start,end) but differ in label
 * — those count as both ``onlyA`` and ``onlyB`` in the strict diff, so we
 * surface them explicitly.
 */
export function summarizePair(
  a: EntitySpanResponse[],
  b: EntitySpanResponse[],
): PairSummary {
  const { added, removed, kept } = diffSpans(a, b);
  // ``added`` = in b only; ``removed`` = in a only.
  const aRanges = new Map<string, string>();
  for (const s of removed) aRanges.set(`${s.start}:${s.end}`, s.label);
  let relabeled = 0;
  for (const s of added) {
    const otherLabel = aRanges.get(`${s.start}:${s.end}`);
    if (otherLabel != null && otherLabel !== s.label) relabeled++;
  }
  return {
    agreed: kept.length,
    onlyA: removed.length - relabeled,
    onlyB: added.length - relabeled,
    relabeled,
  };
}
