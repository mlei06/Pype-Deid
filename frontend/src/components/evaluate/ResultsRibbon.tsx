import { Link } from 'react-router-dom';
import { clsx } from 'clsx';
import { Database } from 'lucide-react';
import type {
  EvalRunDetail,
  MacroMetrics,
  MatchMetrics,
} from '../../api/types';

interface ResultsRibbonProps {
  run: EvalRunDetail;
}

function pct(value: number | undefined | null): string {
  if (value == null || Number.isNaN(value)) return '—';
  return (value * 100).toFixed(1) + '%';
}

export default function ResultsRibbon({ run }: ResultsRibbonProps) {
  const metrics = run.metrics ?? {};
  const overall =
    metrics.overall && typeof metrics.overall === 'object'
      ? (metrics.overall as Record<string, MatchMetrics>)
      : {};
  const macro =
    metrics.macro && typeof metrics.macro === 'object'
      ? (metrics.macro as MacroMetrics)
      : undefined;
  const strictF1 = overall.strict?.f1 ?? run.strict_f1;
  const macroF1 = macro?.strict.f1;
  const riskRecall =
    typeof metrics.risk_weighted_recall === 'number'
      ? metrics.risk_weighted_recall
      : run.risk_weighted_recall;
  const sample = metrics.sample as
    | { sample_size: number; sample_of_total: number; sample_seed_used: number; saved_dataset_name?: string }
    | undefined;
  const evalPredLabelRemap =
    metrics.eval_pred_label_remap && typeof metrics.eval_pred_label_remap === 'object'
      ? (metrics.eval_pred_label_remap as Record<string, string>)
      : undefined;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2 rounded-lg border border-gray-200 bg-white p-4">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm">
          <span className="text-base font-semibold text-gray-900">{run.pipeline_name}</span>
          <span className="text-gray-400">·</span>
          <span className="text-gray-600">{run.dataset_source}</span>
          <span className="text-gray-400">·</span>
          <span className="text-gray-500">{run.document_count} docs</span>
          <span className="text-gray-400">·</span>
          <span className="text-gray-400">{new Date(run.created_at).toLocaleString()}</span>
        </div>
        <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1 text-sm">
          <Stat title="Strict F1" value={strictF1} highlight />
          {macroF1 != null && <Stat title="Macro F1" value={macroF1} />}
          <Stat title="Risk Recall" value={riskRecall} />
        </div>
      </div>

      {sample && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-indigo-100 bg-indigo-50/50 px-3 py-1.5 text-xs text-indigo-900">
          <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide">
            Sampled
          </span>
          <span>
            {sample.sample_size} of {sample.sample_of_total} documents
          </span>
          <span className="text-indigo-700/80">·</span>
          <span>
            seed <code className="rounded bg-white/80 px-1 font-mono">{sample.sample_seed_used}</code>
          </span>
          {sample.saved_dataset_name && (
            <>
              <span className="text-indigo-700/80">·</span>
              <span className="text-indigo-800">saved as</span>
              <Link
                to="/datasets"
                className="inline-flex items-center gap-1 rounded bg-white px-1.5 py-0.5 font-mono text-[11px] text-indigo-900 ring-1 ring-indigo-200 hover:bg-indigo-50"
              >
                <Database size={11} className="opacity-70" />
                {sample.saved_dataset_name}
              </Link>
            </>
          )}
        </div>
      )}

      {evalPredLabelRemap && Object.keys(evalPredLabelRemap).length > 0 && (
        <div className="flex flex-wrap items-start gap-2 rounded-md border border-indigo-100 bg-indigo-50/60 px-3 py-2 text-xs text-indigo-950">
          <span className="font-semibold">Eval remap applied</span>
          {Object.entries(evalPredLabelRemap)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([source, target]) => (
              <code key={source} className="rounded bg-white/80 px-1 py-0.5 font-mono text-[11px]">
                {source} -&gt; {target}
              </code>
            ))}
        </div>
      )}
    </div>
  );
}

function Stat({
  title,
  value,
  highlight,
}: {
  title: string;
  value: number | undefined | null;
  highlight?: boolean;
}) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">{title}</span>
      <span className={clsx('font-semibold', highlight ? 'text-gray-900' : 'text-gray-700')}>
        {pct(value)}
      </span>
    </div>
  );
}
