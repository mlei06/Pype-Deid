import type { EntitySpanResponse, TraceFrame } from '../types';

export interface SpanLabelConflict {
  start: number;
  end: number;
  labelA: string;
  labelB: string;
  pipeA: string;
  pipeB: string;
}

/** Key by character range (same bounds from two pipes). */
export type ConflictRangeMap = Map<string, SpanLabelConflict>;

export function conflictRangeKey(start: number, end: number): string {
  return `${start}-${end}`;
}

/**
 * Detect same-boundary spans with different labels between regex-based detection
 * and whitelist passes in the pipeline trace (common source of "who wins?" ambiguity).
 */
export function buildConflictMapFromTrace(
  trace: TraceFrame[] | null | undefined,
): ConflictRangeMap {
  const map: ConflictRangeMap = new Map();
  if (!trace?.length) return map;

  const lower = (t: string) => t.toLowerCase();
  const regexFrame = trace.find(
    (f) =>
      lower(f.pipe_type).includes('regex') && f.document?.spans,
  );
  const whitelistFrame = trace.find(
    (f) =>
      lower(f.pipe_type).includes('whitelist') && f.document?.spans,
  );

  if (!regexFrame?.document || !whitelistFrame?.document) return map;

  const ra = regexFrame.document.spans;
  const wb = whitelistFrame.document.spans;

  for (const a of ra) {
    const b = wb.find((s) => s.start === a.start && s.end === a.end);
    if (b && a.label !== b.label) {
      map.set(conflictRangeKey(a.start, a.end), {
        start: a.start,
        end: a.end,
        labelA: a.label,
        labelB: b.label,
        pipeA: regexFrame.pipe_type,
        pipeB: whitelistFrame.pipe_type,
      });
    }
  }
  return map;
}

/** Map final span keys (start-end-label) to conflict info when range matches. */
export function conflictsForFinalSpans(
  conflicts: ConflictRangeMap,
  spans: EntitySpanResponse[],
): Map<string, SpanLabelConflict> {
  const out = new Map<string, SpanLabelConflict>();
  for (const s of spans) {
    const c = conflicts.get(conflictRangeKey(s.start, s.end));
    if (c) {
      out.set(`${s.start}-${s.end}-${s.label}`, c);
    }
  }
  return out;
}
