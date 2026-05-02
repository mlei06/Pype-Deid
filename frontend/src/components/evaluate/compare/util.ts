import type {
  EvalRunDetail,
  LabelMetricsDetail,
  MacroMetrics,
  MatchMetrics,
} from '../../../api/types';

export type MatchingMode = 'strict' | 'exact_boundary' | 'partial_overlap' | 'token_level';

export const MATCHING_MODES: MatchingMode[] = [
  'strict',
  'exact_boundary',
  'partial_overlap',
  'token_level',
];

export function modeLabel(mode: MatchingMode): string {
  return mode.replace(/_/g, ' ');
}

export function pct(value: number | null | undefined, digits = 1): string {
  if (value == null || Number.isNaN(value)) return '—';
  return (value * 100).toFixed(digits) + '%';
}

export function delta(value: number | null | undefined, baseline: number | null | undefined): number | null {
  if (value == null || baseline == null) return null;
  if (Number.isNaN(value) || Number.isNaN(baseline)) return null;
  return value - baseline;
}

export function getOverall(run: EvalRunDetail): Record<MatchingMode, MatchMetrics> {
  const raw = (run.metrics?.overall as Record<string, MatchMetrics> | undefined) ?? {};
  return {
    strict: raw.strict ?? emptyMatch(),
    exact_boundary: raw.exact_boundary ?? emptyMatch(),
    partial_overlap: raw.partial_overlap ?? emptyMatch(),
    token_level: raw.token_level ?? emptyMatch(),
  };
}

export function getMacro(run: EvalRunDetail): MacroMetrics | undefined {
  return run.metrics?.macro as MacroMetrics | undefined;
}

export function getRiskRecall(run: EvalRunDetail): number {
  const m = run.metrics?.risk_weighted_recall;
  if (typeof m === 'number') return m;
  return run.risk_weighted_recall;
}

export function getPerLabel(run: EvalRunDetail): Record<string, LabelMetricsDetail> {
  return (run.metrics?.per_label as Record<string, LabelMetricsDetail> | undefined) ?? {};
}

export function getLabelMetric(
  lm: LabelMetricsDetail | undefined,
  mode: MatchingMode,
): MatchMetrics | undefined {
  if (!lm) return undefined;
  if (mode === 'exact_boundary') return undefined; // not tracked per-label
  return lm[mode];
}

export function getConfusion(run: EvalRunDetail): Record<string, Record<string, number>> | undefined {
  const c = run.metrics?.label_confusion;
  if (!c || typeof c !== 'object') return undefined;
  return c as Record<string, Record<string, number>>;
}

function emptyMatch(): MatchMetrics {
  return { precision: 0, recall: 0, f1: 0, tp: 0, fp: 0, fn: 0 };
}

export function summarizeRun(run: EvalRunDetail): string {
  return `${run.pipeline_name} · ${run.dataset_source}`;
}

/**
 * Roll up per-label F1 deltas for a run vs the baseline.
 *
 * Used by the Summary panel to surface a "Run B improves N labels, regresses K" sentence
 * — both numbers and the average delta size give a feel for the move.
 */
export function rollupLabelDeltas(
  run: EvalRunDetail,
  baseline: EvalRunDetail,
  mode: MatchingMode = 'strict',
): {
  improved: number;
  regressed: number;
  unchanged: number;
  netLabels: number;
  avgDelta: number;
} {
  if (mode === 'exact_boundary') {
    return { improved: 0, regressed: 0, unchanged: 0, netLabels: 0, avgDelta: 0 };
  }
  const base = getPerLabel(baseline);
  const cur = getPerLabel(run);
  const labels = new Set([...Object.keys(base), ...Object.keys(cur)]);
  let improved = 0;
  let regressed = 0;
  let unchanged = 0;
  let total = 0;
  let sum = 0;
  for (const l of labels) {
    const a = base[l]?.[mode]?.f1 ?? 0;
    const b = cur[l]?.[mode]?.f1 ?? 0;
    const d = b - a;
    if (Math.abs(d) < 0.005) unchanged += 1;
    else if (d > 0) improved += 1;
    else regressed += 1;
    sum += d;
    total += 1;
  }
  return {
    improved,
    regressed,
    unchanged,
    netLabels: labels.size,
    avgDelta: total > 0 ? sum / total : 0,
  };
}
