import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { AlertTriangle, CheckCircle2, ExternalLink } from 'lucide-react';
import { clsx } from 'clsx';
import { useDataset } from '../../hooks/useDatasets';
import { usePipeline } from '../../hooks/usePipelines';
import { useHealth } from '../../hooks/useHealth';
import { previewCorpusLabels } from '../../api/datasets';
import type { HealthResponse, PipelineDetail } from '../../api/types';

type SourceMode = 'registered' | 'path';

function LabelChips({
  title,
  explainer,
  labels,
  className,
}: {
  title: string;
  explainer?: string;
  labels: string[];
  className: string;
}) {
  const header = (
    <div className="flex items-baseline gap-1.5">
      <span className="text-[10px] font-medium uppercase tracking-wide text-gray-500">{title}</span>
      <span className="text-[10px] font-mono text-gray-400">{labels.length}</span>
    </div>
  );
  return (
    <div>
      {header}
      {explainer && <p className="mt-0.5 text-[11px] text-gray-500">{explainer}</p>}
      {labels.length === 0 ? (
        <p className="mt-1 text-xs text-gray-400">—</p>
      ) : (
        <div className="mt-1 flex flex-wrap gap-1">
          {labels.map((l) => (
            <span
              key={l}
              className={clsx('rounded px-1.5 py-0.5 text-[11px] font-mono', className)}
            >
              {l}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function CollapsedLabelList({
  title,
  labels,
  className,
}: {
  title: string;
  labels: string[];
  className: string;
}) {
  return (
    <details className="group rounded border border-gray-100 bg-gray-50/60 px-2 py-1.5">
      <summary className="cursor-pointer list-none text-[11px] font-medium text-gray-600 hover:text-gray-900">
        <span className="mr-1 inline-block transition-transform group-open:rotate-90">▸</span>
        {title} <span className="font-mono text-gray-400">({labels.length})</span>
      </summary>
      {labels.length === 0 ? (
        <p className="mt-1 text-xs text-gray-400">—</p>
      ) : (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {labels.map((l) => (
            <span
              key={l}
              className={clsx('rounded px-1.5 py-0.5 text-[11px] font-mono', className)}
            >
              {l}
            </span>
          ))}
        </div>
      )}
    </details>
  );
}

function setDiff(a: Set<string>, b: Set<string>) {
  const onlyA: string[] = [];
  const onlyB: string[] = [];
  const both: string[] = [];
  for (const x of Array.from(a).sort((x, y) => x.localeCompare(y))) {
    if (b.has(x)) both.push(x);
    else onlyA.push(x);
  }
  for (const x of Array.from(b).sort((x, y) => x.localeCompare(y))) {
    if (!a.has(x)) onlyB.push(x);
  }
  return { onlyA, onlyB, both };
}

interface EvalLabelAlignmentProps {
  sourceMode: SourceMode;
  datasetName: string;
  /** Raw path string for "path on server" mode (not resolved client-side). */
  datasetPath: string;
  pipelineName: string;
  tempPredLabelRemap?: Record<string, string>;
  onTempPredLabelRemapChange?: (mapping: Record<string, string>) => void;
  /**
   * When true, render nothing unless we detect a real misalignment between gold
   * and pipeline label sets. Loading / empty / error placeholders are
   * suppressed too — the widget only "pops up" when the user has something to
   * fix.
   */
  autoHide?: boolean;
}

function GoldPipelineDiff({
  goldLabels,
  goldSubtitle,
  health,
  pipelineName,
  pipelineQuery,
  tempPredLabelRemap,
  onTempPredLabelRemapChange,
  autoHide,
}: {
  goldLabels: string[];
  goldSubtitle?: string;
  health: HealthResponse | undefined;
  pipelineName: string;
  pipelineQuery: UseQueryResult<PipelineDetail, Error>;
  tempPredLabelRemap?: Record<string, string>;
  onTempPredLabelRemapChange?: (mapping: Record<string, string>) => void;
  autoHide?: boolean;
}) {
  const p = pipelineQuery.data;
  const outSpace = p?.config?.output_label_space;
  const pipelineLabels = Array.isArray(outSpace) ? outSpace : [];
  const goldSet = new Set(goldLabels);
  const pipeSet = new Set(pipelineLabels);
  const { onlyA, onlyB, both } = setDiff(goldSet, pipeSet);
  const currentRemap = tempPredLabelRemap ?? {};

  useEffect(() => {
    if (!onTempPredLabelRemapChange || !p) return;
    const allowedKeys = new Set(onlyB);
    const allowedTargets = new Set(goldLabels);
    const next: Record<string, string> = {};
    for (const [k, v] of Object.entries(currentRemap)) {
      if (!allowedKeys.has(k)) continue;
      const target = v.trim();
      if (!target || !allowedTargets.has(target)) continue;
      next[k] = target;
    }
    const same =
      Object.keys(next).length === Object.keys(currentRemap).length &&
      Object.entries(next).every(([k, v]) => currentRemap[k] === v);
    if (!same) onTempPredLabelRemapChange(next);
  }, [currentRemap, goldLabels, onlyB, onTempPredLabelRemapChange, p]);

  if (pipelineQuery.isLoading) {
    if (autoHide) return null;
    return (
      <p className="text-xs text-gray-400" aria-live="polite">
        Loading pipeline…
      </p>
    );
  }
  if (pipelineQuery.isError) {
    if (autoHide) return null;
    return (
      <p className="text-xs text-red-600">
        Could not load pipeline: {(pipelineQuery.error as Error).message}
      </p>
    );
  }
  if (!p) return null;

  const mismatch = onlyA.length > 0 || onlyB.length > 0;
  const missingOutput = pipelineLabels.length === 0;
  if (autoHide && !mismatch && !missingOutput) return null;
  const loadHref = `/create?load=${encodeURIComponent(pipelineName.trim())}`;
  const hasRemapEditor = typeof onTempPredLabelRemapChange === 'function' && onlyB.length > 0;
  const normalizedGoldLabels = goldLabels.slice().sort((a, b) => a.localeCompare(b));

  const updateOneMapping = (source: string, target: string) => {
    if (!onTempPredLabelRemapChange) return;
    const next = { ...currentRemap };
    const trimmed = target.trim();
    if (!trimmed) delete next[source];
    else next[source] = trimmed;
    onTempPredLabelRemapChange(next);
  };

  const clearMappings = () => {
    if (!onTempPredLabelRemapChange) return;
    onTempPredLabelRemapChange({});
  };

  return (
    <div className="space-y-3 rounded-lg border border-gray-200 bg-white p-3 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <h4 className="text-xs font-bold uppercase tracking-wider text-gray-500">Label alignment (raw)</h4>
        {mismatch || missingOutput ? (
          <span className="inline-flex items-center gap-1 rounded bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-900">
            <AlertTriangle size={12} />
            Check labels
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-800">
            <CheckCircle2 size={12} />
            Sets match
          </span>
        )}
      </div>

      {goldSubtitle && <p className="text-[11px] text-gray-500">{goldSubtitle}</p>}

      <p className="text-xs leading-relaxed text-gray-600">
        Evaluation uses <strong>exact</strong> string labels on gold vs predicted spans (and boundaries). It does
        <strong> not</strong> use <code className="rounded bg-gray-100 px-0.5">PYPEDEID_LABEL_SPACE_NAME</code> at
        eval time. If gold and pipeline disagree, add a <strong>label_mapper</strong> (or change the corpus) so
        names match. See the repo&apos;s <code className="rounded bg-gray-100 px-0.5">docs/pipes-and-pipelines.md</code> for
        pipe types.
      </p>

      {health && (
        <p className="text-[11px] text-gray-500">
          <strong>Inference</strong> <code className="rounded bg-gray-100 px-0.5">POST /process</code> normalizes
          response labels with label space <span className="font-mono">{health.label_space_name}</span> (and default
          risk profile <span className="font-mono">{health.risk_profile_name}</span> for risk-weighted eval metrics);
          that is separate from this comparison.
        </p>
      )}

      {missingOutput && (
        <p className="text-xs text-amber-800">
          Pipeline has no <code className="rounded bg-amber-100 px-0.5">output_label_space</code> in config — save
          or validate the pipeline in the builder to refresh computed labels, or the chain could not be folded
          symbolically.
        </p>
      )}

      <div className="grid gap-3 sm:grid-cols-3">
        <LabelChips
          title="Gold only"
          explainer="In this gold, not in pipeline output."
          labels={onlyA}
          className="bg-rose-100/90 text-rose-900"
        />
        <LabelChips
          title="In pipeline only"
          explainer="Predicted by pipeline, not in this gold."
          labels={onlyB}
          className="bg-sky-100/80 text-sky-900"
        />
        <LabelChips
          title="In both"
          explainer="Compared on strict string match during eval."
          labels={both}
          className="bg-gray-100 text-gray-800"
        />
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <CollapsedLabelList
          title="All gold labels"
          labels={goldLabels.slice().sort((a, b) => a.localeCompare(b))}
          className="bg-white text-gray-700 ring-1 ring-gray-200"
        />
        <CollapsedLabelList
          title="Full output_label_space (symbolic)"
          labels={pipelineLabels}
          className="bg-violet-50 text-violet-900 ring-1 ring-violet-100"
        />
      </div>

      {hasRemapEditor && (
        <div className="rounded-md border border-indigo-100 bg-indigo-50/40 p-2.5">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h5 className="text-xs font-semibold text-indigo-950">Temporary eval label remap</h5>
              <p className="text-[11px] text-indigo-900/80">
                Run-scoped only. This does not modify the saved pipeline config.
              </p>
            </div>
            <button
              type="button"
              onClick={clearMappings}
              className="rounded border border-indigo-200 bg-white px-2 py-1 text-[11px] font-medium text-indigo-900 hover:bg-indigo-50"
            >
              Clear mappings
            </button>
          </div>
          <div className="space-y-1.5">
            {onlyB.map((sourceLabel) => (
              <div key={sourceLabel} className="flex flex-wrap items-center gap-2 text-xs">
                <span className="rounded bg-sky-100/80 px-1.5 py-0.5 font-mono text-sky-900">
                  {sourceLabel}
                </span>
                <span className="text-indigo-900/70">→</span>
                <select
                  value={currentRemap[sourceLabel] ?? ''}
                  onChange={(e) => updateOneMapping(sourceLabel, e.target.value)}
                  className="min-w-[11rem] rounded border border-indigo-200 bg-white px-2 py-1 text-xs text-gray-800 shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
                >
                  <option value="">No mapping</option>
                  {normalizedGoldLabels.map((goldLabel) => (
                    <option key={goldLabel} value={goldLabel}>
                      {goldLabel}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-indigo-900/80">
            Unmapped labels keep their original names during evaluation.
          </p>
        </div>
      )}

      {(mismatch || missingOutput) && (
        <div className="flex flex-wrap items-center gap-2 border-t border-gray-100 pt-2">
          <Link
            to={loadHref}
            className="inline-flex items-center gap-1 text-xs font-medium text-gray-900 underline decoration-gray-300 underline-offset-2 hover:decoration-gray-500"
          >
            Open pipeline in builder
            <ExternalLink size={12} className="opacity-60" />
          </Link>
        </div>
      )}
    </div>
  );
}

/**
 * Compare raw gold label set with symbolic pipeline `output_label_space` before running eval.
 */
export default function EvalLabelAlignment({
  sourceMode,
  datasetName,
  datasetPath,
  pipelineName,
  tempPredLabelRemap,
  onTempPredLabelRemapChange,
  autoHide,
}: EvalLabelAlignmentProps) {
  const { data: health } = useHealth();
  const [debouncedPath, setDebouncedPath] = useState('');

  useEffect(() => {
    const t = setTimeout(() => setDebouncedPath(datasetPath.trim()), 450);
    return () => clearTimeout(t);
  }, [datasetPath]);

  const pathLooksJsonl = debouncedPath.toLowerCase().endsWith('.jsonl');
  const previewQuery = useQuery({
    queryKey: ['datasets', 'preview-labels', debouncedPath],
    queryFn: () => previewCorpusLabels({ path: debouncedPath }),
    enabled:
      sourceMode === 'path' && pathLooksJsonl && debouncedPath.length > 0,
    retry: false,
  });

  const detailQuery = useDataset(sourceMode === 'registered' && datasetName.trim() ? datasetName.trim() : null);
  const pipelineQuery = usePipeline(pipelineName.trim() ? pipelineName.trim() : null);

  if (sourceMode === 'path') {
    if (!pipelineName.trim()) {
      return null;
    }
    if (!datasetPath.trim()) {
      if (autoHide) return null;
      return (
        <p className="text-xs text-gray-500">
          Enter a <code className="rounded bg-gray-100 px-0.5">.jsonl</code> path under the server corpora root to
          preview gold labels, or switch to a registered dataset.
        </p>
      );
    }
    if (!pathLooksJsonl) {
      if (autoHide) return null;
      return (
        <p className="text-xs text-amber-800">
          Path should end in <code className="rounded bg-amber-100 px-0.5">.jsonl</code> (same as eval). Example:{' '}
          <code className="font-mono text-[10px]">my-dataset/corpus.jsonl</code> relative to corpora.
        </p>
      );
    }
    if (previewQuery.isLoading) {
      if (autoHide) return null;
      return <p className="text-xs text-gray-400">Scanning gold labels from JSONL…</p>;
    }
    if (previewQuery.isError) {
      if (autoHide) return null;
      return (
        <div className="rounded-md border border-red-200 bg-red-50/80 px-3 py-2 text-xs text-red-800">
          <p className="font-medium">Could not load labels for path</p>
          <p className="mt-0.5">{(previewQuery.error as Error).message}</p>
          <p className="mt-1.5 text-red-700/90">
            Path must be under the corpora root.{' '}
            <Link to="/datasets" className="font-medium underline">
              Datasets
            </Link>
          </p>
        </div>
      );
    }
    if (!previewQuery.data) {
      return null;
    }
    return (
      <GoldPipelineDiff
        goldLabels={previewQuery.data.labels}
        goldSubtitle={
          previewQuery.data.resolved_path
            ? `Gold from POST /datasets/preview-labels — ${previewQuery.data.document_count} document(s) — ${previewQuery.data.resolved_path}`
            : undefined
        }
        health={health}
        pipelineName={pipelineName}
        pipelineQuery={pipelineQuery}
        tempPredLabelRemap={tempPredLabelRemap}
        onTempPredLabelRemapChange={onTempPredLabelRemapChange}
        autoHide={autoHide}
      />
    );
  }

  if (!datasetName.trim() || !pipelineName.trim()) {
    return null;
  }

  if (detailQuery.isLoading || pipelineQuery.isLoading) {
    if (autoHide) return null;
    return (
      <p className="text-xs text-gray-400" aria-live="polite">
        Loading label alignment…
      </p>
    );
  }

  if (detailQuery.isError) {
    if (autoHide) return null;
    return (
      <p className="text-xs text-red-600">
        Could not load dataset: {(detailQuery.error as Error).message}
      </p>
    );
  }

  return (
    <GoldPipelineDiff
      goldLabels={detailQuery.data?.labels ?? []}
      health={health}
      pipelineName={pipelineName}
      pipelineQuery={pipelineQuery}
      tempPredLabelRemap={tempPredLabelRemap}
      onTempPredLabelRemapChange={onTempPredLabelRemapChange}
      autoHide={autoHide}
    />
  );
}
