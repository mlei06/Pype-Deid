import { X } from 'lucide-react';
import DeltaBadge from './DeltaBadge';
import {
  delta,
  getMacro,
  getOverall,
  getRiskRecall,
  MATCHING_MODES,
  modeLabel,
  pct,
  rollupLabelDeltas,
} from './util';
import type { EvalRunDetail } from '../../../api/types';

interface CompareSummaryProps {
  runs: EvalRunDetail[];
  onRemove: (id: string) => void;
  onSelectSingle: (id: string) => void;
}

export default function CompareSummary({ runs, onRemove, onSelectSingle }: CompareSummaryProps) {
  if (runs.length === 0) return null;
  const baseline = runs[0];

  return (
    <div className="flex flex-col gap-4">
      <ImprovementHeadline runs={runs} />

      <div
        className="grid gap-3"
        style={{ gridTemplateColumns: `repeat(${runs.length}, minmax(260px, 1fr))` }}
      >
        {runs.map((run, idx) => (
          <RunSummaryCard
            key={run.id}
            run={run}
            baseline={idx === 0 ? null : baseline}
            isBaseline={idx === 0}
            onRemove={() => onRemove(run.id)}
            onSelectSingle={() => onSelectSingle(run.id)}
          />
        ))}
      </div>
    </div>
  );
}

function ImprovementHeadline({ runs }: { runs: EvalRunDetail[] }) {
  if (runs.length < 2) return null;
  const baseline = runs[0];
  const lines: string[] = [];
  for (let i = 1; i < runs.length; i++) {
    const r = runs[i];
    const stats = rollupLabelDeltas(r, baseline, 'strict');
    if (stats.netLabels === 0) continue;
    const avg = (stats.avgDelta * 100).toFixed(1);
    const direction = stats.avgDelta >= 0 ? '+' : '';
    lines.push(
      `${r.pipeline_name}: improves ${stats.improved} label(s), regresses ${stats.regressed}, ${stats.unchanged} flat — avg ${direction}${avg}% F1 vs ${baseline.pipeline_name}.`,
    );
  }
  if (lines.length === 0) return null;
  return (
    <div className="rounded-md border border-indigo-100 bg-indigo-50/40 px-3 py-2 text-xs text-indigo-950">
      <div className="font-semibold text-indigo-900">Headline</div>
      <ul className="mt-1 space-y-0.5">
        {lines.map((l, i) => (
          <li key={i}>{l}</li>
        ))}
      </ul>
    </div>
  );
}

function RunSummaryCard({
  run,
  baseline,
  isBaseline,
  onRemove,
  onSelectSingle,
}: {
  run: EvalRunDetail;
  baseline: EvalRunDetail | null;
  isBaseline: boolean;
  onRemove: () => void;
  onSelectSingle: () => void;
}) {
  const overall = getOverall(run);
  const baseOverall = baseline ? getOverall(baseline) : null;
  const macro = getMacro(run);
  const baseMacro = baseline ? getMacro(baseline) : undefined;
  const rwr = getRiskRecall(run);
  const baseRwr = baseline ? getRiskRecall(baseline) : undefined;

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-gray-200 bg-white p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <button
            type="button"
            onClick={onSelectSingle}
            className="block truncate text-left text-sm font-semibold text-gray-900 hover:text-gray-700"
            title="View this run on its own"
          >
            {run.pipeline_name}
          </button>
          <div className="truncate text-[11px] text-gray-500">{run.dataset_source}</div>
          <div className="text-[10px] text-gray-400">
            {run.document_count} docs · {new Date(run.created_at).toLocaleDateString()}
          </div>
        </div>
        <button
          type="button"
          onClick={onRemove}
          className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          aria-label={`Remove ${run.pipeline_name} from compare`}
        >
          <X size={14} />
        </button>
      </div>

      {isBaseline && (
        <span className="w-fit rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
          Baseline
        </span>
      )}

      <div className="space-y-2 border-t border-gray-100 pt-2">
        <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
          Matching modes (overall)
        </div>
        {MATCHING_MODES.map((mode) => {
          const m = overall[mode];
          const baseM = baseOverall?.[mode];
          return (
            <ModeRow
              key={mode}
              label={modeLabel(mode)}
              precision={m.precision}
              recall={m.recall}
              f1={m.f1}
              baselineF1={baseM?.f1}
              highlightF1={mode === 'strict'}
            />
          );
        })}
      </div>

      {macro && (
        <div className="space-y-2 border-t border-gray-100 pt-2">
          <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-gray-400">
            <span>Macro F1</span>
            <span className="font-normal lowercase tracking-normal text-gray-400">
              over {macro.strict.label_count} labels
            </span>
          </div>
          <ModeRow
            label="strict"
            precision={macro.strict.precision}
            recall={macro.strict.recall}
            f1={macro.strict.f1}
            baselineF1={baseMacro?.strict.f1}
          />
          <ModeRow
            label="partial"
            precision={macro.partial_overlap.precision}
            recall={macro.partial_overlap.recall}
            f1={macro.partial_overlap.f1}
            baselineF1={baseMacro?.partial_overlap.f1}
          />
          <ModeRow
            label="token-level"
            precision={macro.token_level.precision}
            recall={macro.token_level.recall}
            f1={macro.token_level.f1}
            baselineF1={baseMacro?.token_level.f1}
          />
        </div>
      )}

      <div className="border-t border-gray-100 pt-2">
        <div className="flex items-baseline justify-between">
          <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
            Risk Recall
          </span>
          <span className="flex items-baseline gap-1.5">
            <span className="text-base font-semibold text-gray-900">{pct(rwr)}</span>
            <DeltaBadge delta={baseline ? delta(rwr, baseRwr) : null} />
          </span>
        </div>
      </div>
    </div>
  );
}

function ModeRow({
  label,
  precision,
  recall,
  f1,
  baselineF1,
  highlightF1,
}: {
  label: string;
  precision: number;
  recall: number;
  f1: number;
  baselineF1?: number;
  highlightF1?: boolean;
}) {
  return (
    <div className="text-xs">
      <div className="flex items-baseline justify-between">
        <span className="text-gray-500">{label}</span>
        <span className="flex items-baseline gap-1.5">
          <span
            className={highlightF1 ? 'text-base font-semibold text-gray-900' : 'font-semibold text-gray-700'}
          >
            {pct(f1)}
          </span>
          <DeltaBadge delta={baselineF1 != null ? delta(f1, baselineF1) : null} compact />
        </span>
      </div>
      <div className="flex items-baseline justify-between text-[10px] text-gray-400">
        <span>P {pct(precision)}</span>
        <span>R {pct(recall)}</span>
      </div>
    </div>
  );
}
