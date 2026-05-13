import type { EntitySpanResponse } from '../api/types';
import { entitySpanKey } from '@shared/lib/entitySpanKey';

/**
 * Mirrors ``DEFAULT_LABEL_PRIORITY`` in ``pypedeid/pipes/span_merge.py``
 * for ``resolve_spans`` with strategy ``label_priority``.
 */
export const RESOLVE_SPANS_LABEL_PRIORITY: string[] = [
  'NAME',
  'PATIENT',
  'FIRST_NAME',
  'LAST_NAME',
  'SSN',
  'MRN',
  'ID',
  'DATE',
  'DOB',
  'PHONE',
  'FAX',
  'EMAIL',
  'ADDRESS',
  'STREET',
  'CITY',
  'STATE',
  'ZIP',
  'COUNTRY',
  'HOSPITAL',
  'ORGANIZATION',
  'AGE',
  'URL',
  'IP',
  'DEVICE',
  'PLATE',
  'VIN',
  'ACCOUNT',
];

function overlaps(a: EntitySpanResponse, b: EntitySpanResponse): boolean {
  return a.start < b.end && b.start < a.end;
}

function hasOverlapWithKept(span: EntitySpanResponse, kept: EntitySpanResponse[]): boolean {
  return kept.some((k) => overlaps(span, k));
}

/**
 * Same greedy merge as ``merge_label_priority`` / ``apply_resolve_spans(..., strategy="label_priority")``.
 * Higher-priority labels (earlier in *labelPriority*) win; ties break by longer span, then leftmost.
 */
export function mergeLabelPrioritySpans(
  spans: EntitySpanResponse[],
  labelPriority: string[] = RESOLVE_SPANS_LABEL_PRIORITY,
): EntitySpanResponse[] {
  const priorityMap = new Map(labelPriority.map((l, i) => [l, i]));
  const defaultRank = labelPriority.length;
  const all = [...spans].sort((a, b) => {
    const pa = priorityMap.get(a.label) ?? defaultRank;
    const pb = priorityMap.get(b.label) ?? defaultRank;
    if (pa !== pb) return pa - pb;
    const la = a.end - a.start;
    const lb = b.end - b.start;
    if (la !== lb) return lb - la;
    return a.start - b.start;
  });
  const kept: EntitySpanResponse[] = [];
  for (const span of all) {
    if (!hasOverlapWithKept(span, kept)) {
      kept.push(span);
    }
  }
  kept.sort((a, b) => a.start - b.start || a.end - b.end || a.label.localeCompare(b.label));
  return kept;
}

export type ResolveStrategyId = 'label_priority' | 'longest_wins' | 'leftmost_first';

export const RESOLVE_STRATEGY_LABEL: Record<ResolveStrategyId, string> = {
  label_priority: 'Label priority',
  longest_wins: 'Longest wins',
  leftmost_first: 'Leftmost first',
};

/**
 * Greedy "leftmost first" — sort by start ascending, **shorter** spans winning ties,
 * then label, then deterministic. Earlier, smaller chunks beat later, larger ones.
 */
export function mergeLeftmostFirstSpans(spans: EntitySpanResponse[]): EntitySpanResponse[] {
  const all = [...spans].sort((a, b) => {
    if (a.start !== b.start) return a.start - b.start;
    const la = a.end - a.start;
    const lb = b.end - b.start;
    if (la !== lb) return la - lb;
    return a.label.localeCompare(b.label);
  });
  const kept: EntitySpanResponse[] = [];
  for (const span of all) {
    if (!hasOverlapWithKept(span, kept)) {
      kept.push(span);
    }
  }
  kept.sort((a, b) => a.start - b.start || a.end - b.end || a.label.localeCompare(b.label));
  return kept;
}

export function applyResolveStrategy(
  spans: EntitySpanResponse[],
  strategy: ResolveStrategyId,
): EntitySpanResponse[] {
  switch (strategy) {
    case 'label_priority':
      return mergeLabelPrioritySpans(spans);
    case 'longest_wins':
      return mergeLabelPrioritySpans(spans, []);
    case 'leftmost_first':
      return mergeLeftmostFirstSpans(spans);
  }
}

/** Stable key for a character range. Retained for span-level rendering hooks. */
export function spanRangeKey(start: number, end: number): string {
  return `${start}-${end}`;
}

const RESOLVE_PRIORITY_RANK: ReadonlyMap<string, number> = new Map(
  RESOLVE_SPANS_LABEL_PRIORITY.map((l, i) => [l, i]),
);
const RESOLVE_PRIORITY_DEFAULT_RANK = RESOLVE_SPANS_LABEL_PRIORITY.length;

/** Resolution priority for *label*. Lower wins. Mirrors ``mergeLabelPrioritySpans``. */
export function labelPriority(label: string): number {
  return RESOLVE_PRIORITY_RANK.get(label) ?? RESOLVE_PRIORITY_DEFAULT_RANK;
}

/**
 * Sort by the same key as the bulk "label_priority" strategy:
 * priority asc, length desc, start asc, label asc. So the head matches what
 * ``mergeLabelPrioritySpans`` would have kept.
 */
export function sortSpansByPrimary(spans: EntitySpanResponse[]): EntitySpanResponse[] {
  return [...spans].sort((a, b) => {
    const pa = labelPriority(a.label);
    const pb = labelPriority(b.label);
    if (pa !== pb) return pa - pb;
    const la = a.end - a.start;
    const lb = b.end - b.start;
    if (la !== lb) return lb - la;
    if (a.start !== b.start) return a.start - b.start;
    return a.label.localeCompare(b.label);
  });
}

export function pickPrimarySpan(spans: EntitySpanResponse[]): EntitySpanResponse {
  return sortSpansByPrimary(spans)[0]!;
}

/**
 * Collapse exact (start, end, label) duplicates produced by multiple detectors
 * agreeing on a span. Sources are concatenated with ``+`` (deduped, sorted) so
 * provenance survives. Confidence becomes the max of inputs; ``text`` falls back
 * to the first non-empty value.
 *
 * Spans with ``start >= end`` are dropped defensively. Output is sorted by
 * ``(start, end, label)`` so it has the same shape downstream code expects.
 *
 * Without this, two detectors that find the same span produce duplicate
 * ``entitySpanKey`` collisions in the SpanEditor (shared React keys, shared
 * selection state, post-resolution residue).
 */
export function normalizeAnnotations(spans: EntitySpanResponse[]): EntitySpanResponse[] {
  if (spans.length === 0) return spans;
  const byKey = new Map<string, EntitySpanResponse[]>();
  for (const s of spans) {
    if (s.start >= s.end) continue;
    const k = entitySpanKey(s);
    const list = byKey.get(k) ?? [];
    list.push(s);
    byKey.set(k, list);
  }
  const out: EntitySpanResponse[] = [];
  for (const list of byKey.values()) {
    if (list.length === 1) {
      out.push(list[0]!);
      continue;
    }
    const sources = new Set<string>();
    for (const s of list) {
      if (s.source) sources.add(s.source);
    }
    let confidence: number | null | undefined = list[0]!.confidence;
    for (const s of list) {
      const c = s.confidence;
      if (c == null) continue;
      if (confidence == null || c > confidence) confidence = c;
    }
    const text = list.find((s) => (s.text ?? '').length > 0)?.text ?? list[0]!.text;
    const merged: EntitySpanResponse = {
      ...list[0]!,
      text,
      confidence: confidence ?? null,
      source: sources.size > 0 ? [...sources].sort().join('+') : list[0]!.source,
    };
    out.push(merged);
  }
  out.sort((a, b) => a.start - b.start || a.end - b.end || a.label.localeCompare(b.label));
  return out;
}

/**
 * One span per exact range — the primary label wins for rendering the annotated source.
 * Retained for surrogate output rendering, which has its own ambiguity to resolve.
 */
export function dedupeSpansKeepPrimary(spans: EntitySpanResponse[]): EntitySpanResponse[] {
  const byRange = new Map<string, EntitySpanResponse[]>();
  for (const s of spans) {
    const k = spanRangeKey(s.start, s.end);
    const list = byRange.get(k) ?? [];
    list.push(s);
    byRange.set(k, list);
  }
  const out: EntitySpanResponse[] = [];
  for (const list of byRange.values()) {
    out.push(pickPrimarySpan(list));
  }
  out.sort((a, b) => a.start - b.start || a.end - b.end);
  return out;
}

// ---------------------------------------------------------------------------
// Overlap groups (connected components of the overlap graph)
// ---------------------------------------------------------------------------

export interface OverlapGroup {
  /** Stable id derived from extents + member set; remains valid as long as the same members exist. */
  id: string;
  members: EntitySpanResponse[];
  minStart: number;
  maxEnd: number;
  /** ``originalText.slice(minStart, maxEnd)`` — convenience for headers / titles. */
  excerpt: string;
}

/**
 * Connected-component grouping of *spans* by overlap. Groups with a single member
 * (i.e. spans that don't overlap anything) are dropped — only conflicts are returned.
 *
 * Uses a sweepline over span endpoints to merge overlapping intervals into the same
 * union-find component, so this runs in O(n log n).
 */
export function findOverlapGroups(
  spans: EntitySpanResponse[],
  originalText: string,
): OverlapGroup[] {
  if (spans.length < 2) return [];

  const indexed = spans.map((s, i) => ({ s, i }));
  // Sort by start asc, end desc — long-extent spans seen first within a coordinate.
  indexed.sort((a, b) => a.s.start - b.s.start || b.s.end - a.s.end);

  const parent = new Array(spans.length).fill(0).map((_, i) => i);
  const find = (x: number): number => {
    let cur = x;
    while (parent[cur] !== cur) {
      parent[cur] = parent[parent[cur]];
      cur = parent[cur];
    }
    return cur;
  };
  const union = (a: number, b: number) => {
    const ra = find(a);
    const rb = find(b);
    if (ra !== rb) parent[ra] = rb;
  };

  // Active set: spans we've started but not yet exited. We keep them ordered by end asc
  // so we can drop everything with end <= current.start cheaply.
  const active: { idx: number; end: number }[] = [];
  for (const { s, i } of indexed) {
    while (active.length > 0 && active[0]!.end <= s.start) {
      active.shift();
    }
    for (const a of active) union(a.idx, i);
    // Insert maintaining end-asc order.
    const insertAt = active.findIndex((a) => a.end > s.end);
    const node = { idx: i, end: s.end };
    if (insertAt < 0) active.push(node);
    else active.splice(insertAt, 0, node);
  }

  const components = new Map<number, number[]>();
  for (let i = 0; i < spans.length; i++) {
    const r = find(i);
    const list = components.get(r) ?? [];
    list.push(i);
    components.set(r, list);
  }

  const out: OverlapGroup[] = [];
  for (const memberIdxs of components.values()) {
    if (memberIdxs.length < 2) continue;
    const members = memberIdxs
      .map((i) => spans[i]!)
      .sort((a, b) => a.start - b.start || a.end - b.end || a.label.localeCompare(b.label));
    const minStart = members.reduce((m, x) => Math.min(m, x.start), Infinity);
    const maxEnd = members.reduce((m, x) => Math.max(m, x.end), -Infinity);
    const firstKey = entitySpanKey(members[0]!);
    out.push({
      id: `g${minStart}-${maxEnd}-${members.length}-${firstKey}`,
      members,
      minStart,
      maxEnd,
      excerpt: originalText.slice(minStart, maxEnd),
    });
  }
  out.sort((a, b) => a.minStart - b.minStart || a.maxEnd - b.maxEnd);
  return out;
}

function memberKeySet(group: OverlapGroup): Set<string> {
  return new Set(group.members.map((m) => entitySpanKey(m)));
}

/** Drop every member of *group* from *spans*, then re-add *kept*. */
export function keepInOverlapGroup(
  spans: EntitySpanResponse[],
  group: OverlapGroup,
  kept: EntitySpanResponse,
): EntitySpanResponse[] {
  const drop = memberKeySet(group);
  const keptKey = entitySpanKey(kept);
  const next = spans.filter((s) => !drop.has(entitySpanKey(s)));
  // Avoid a duplicate if *kept* somehow survived the filter (shouldn't, but defensive).
  if (!next.some((s) => entitySpanKey(s) === keptKey)) next.push(kept);
  next.sort(
    (a, b) => a.start - b.start || a.end - b.end || a.label.localeCompare(b.label),
  );
  return next;
}

/** Drop every member of *group* from *spans*. */
export function dropOverlapGroup(
  spans: EntitySpanResponse[],
  group: OverlapGroup,
): EntitySpanResponse[] {
  const drop = memberKeySet(group);
  return spans.filter((s) => !drop.has(entitySpanKey(s)));
}

// ---------------------------------------------------------------------------
// Coverage segments (highlighter substrate)
// ---------------------------------------------------------------------------

export type CoverageSegment =
  | { kind: 'plain'; start: number; end: number }
  | { kind: 'span'; start: number; end: number; span: EntitySpanResponse }
  | { kind: 'overlap'; start: number; end: number; spans: EntitySpanResponse[] };

/**
 * Sweepline over span endpoints. Returns a contiguous, non-overlapping list of
 * segments covering ``[0, textLength)``. Segments where two or more spans cover
 * the same characters are emitted with ``kind: 'overlap'``; this is the
 * substrate for the conflict-strip overlay.
 *
 * The output is order-stable — segments are sorted by ``start`` and adjacent
 * segments with the same kind are not merged (so callers can key by index).
 */
export function buildCoverageSegments(
  textLength: number,
  spans: EntitySpanResponse[],
): CoverageSegment[] {
  if (textLength <= 0) return [];
  if (spans.length === 0) {
    return [{ kind: 'plain', start: 0, end: textLength }];
  }

  // Boundaries: every span start, every span end, plus 0 and textLength.
  const boundarySet = new Set<number>([0, textLength]);
  for (const s of spans) {
    if (s.start >= 0 && s.start <= textLength) boundarySet.add(s.start);
    if (s.end >= 0 && s.end <= textLength) boundarySet.add(s.end);
  }
  const boundaries = [...boundarySet].sort((a, b) => a - b);

  const segments: CoverageSegment[] = [];
  for (let i = 0; i < boundaries.length - 1; i++) {
    const start = boundaries[i]!;
    const end = boundaries[i + 1]!;
    if (start === end) continue;
    const covering = spans.filter((s) => s.start <= start && s.end >= end);
    if (covering.length === 0) {
      segments.push({ kind: 'plain', start, end });
    } else if (covering.length === 1) {
      segments.push({ kind: 'span', start, end, span: covering[0]! });
    } else {
      segments.push({ kind: 'overlap', start, end, spans: covering });
    }
  }
  return segments;
}
