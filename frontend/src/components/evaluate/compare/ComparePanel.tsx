import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQueries } from '@tanstack/react-query';
import { clsx } from 'clsx';
import { BarChart3, FileText, Grid3x3, Layers, Loader2 } from 'lucide-react';
import * as api from '../../../api/evaluation';
import CompareSummary from './CompareSummary';
import ComparePerLabel from './ComparePerLabel';
import CompareConfusion from './CompareConfusion';
import ComparePerDoc from './ComparePerDoc';
import type { EvalRunDetail } from '../../../api/types';

export type CompareTab = 'summary' | 'perlabel' | 'confusion' | 'perdoc';
const COMPARE_TABS: CompareTab[] = ['summary', 'perlabel', 'confusion', 'perdoc'];

function parseTab(value: string | null): CompareTab {
  return COMPARE_TABS.includes(value as CompareTab) ? (value as CompareTab) : 'summary';
}

interface ComparePanelProps {
  runIds: string[];
  onRemove: (id: string) => void;
  onSelectSingle: (id: string) => void;
  onStartNewRun: () => void;
}

export default function ComparePanel({
  runIds,
  onRemove,
  onSelectSingle,
  onStartNewRun,
}: ComparePanelProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = parseTab(searchParams.get('ctab'));
  const setActiveTab = (next: CompareTab) =>
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        params.set('ctab', next);
        return params;
      },
      { replace: true },
    );

  const queries = useQueries({
    queries: runIds.map((id) => ({
      queryKey: ['eval-runs', id],
      queryFn: () => api.getEvalRun(id),
    })),
  });
  const runs = useMemo(
    () => queries.map((q) => q.data).filter((r): r is EvalRunDetail => !!r),
    [queries],
  );
  const isLoading = queries.some((q) => q.isLoading);
  const errors = queries.filter((q) => q.isError).map((q) => q.error as Error);

  if (runIds.length < 2) {
    return <NotEnoughRuns count={runIds.length} onStartNewRun={onStartNewRun} />;
  }

  if (isLoading && runs.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center gap-2 text-sm text-gray-500">
        <Loader2 size={16} className="animate-spin" />
        Loading runs…
      </div>
    );
  }

  if (runs.length < 2) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-3 text-xs text-red-800">
        Could not load enough runs to compare. Errors:
        <ul className="mt-1 list-disc pl-4">
          {errors.map((e, i) => (
            <li key={i}>{e.message}</li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2 text-[11px] text-gray-500">
        <span>
          Comparing <span className="font-semibold text-gray-700">{runs.length}</span> runs · deltas
          relative to{' '}
          <span className="font-semibold text-gray-700">{runs[0].pipeline_name}</span> (first
          selected; click any run name to view solo)
        </span>
      </div>

      <div className="flex w-fit overflow-hidden rounded-lg border border-gray-200 bg-white">
        <CompareTabButton
          id="summary"
          activeTab={activeTab}
          onSelect={setActiveTab}
          icon={<BarChart3 size={14} />}
          label="Summary"
        />
        <CompareTabButton
          id="perlabel"
          activeTab={activeTab}
          onSelect={setActiveTab}
          icon={<Layers size={14} />}
          label="Per-label"
        />
        <CompareTabButton
          id="confusion"
          activeTab={activeTab}
          onSelect={setActiveTab}
          icon={<Grid3x3 size={14} />}
          label="Confusion"
        />
        <CompareTabButton
          id="perdoc"
          activeTab={activeTab}
          onSelect={setActiveTab}
          icon={<FileText size={14} />}
          label="Per-document"
        />
      </div>

      {activeTab === 'summary' && (
        <CompareSummary runs={runs} onRemove={onRemove} onSelectSingle={onSelectSingle} />
      )}
      {activeTab === 'perlabel' && <ComparePerLabel runs={runs} />}
      {activeTab === 'confusion' && <CompareConfusion runs={runs} />}
      {activeTab === 'perdoc' && <ComparePerDoc runs={runs} />}
    </div>
  );
}

function NotEnoughRuns({ count, onStartNewRun }: { count: number; onStartNewRun: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-gray-200 bg-white py-16 text-sm text-gray-500">
      <p>
        Pick at least <span className="font-semibold text-gray-700">two runs</span> from the
        sidebar checkboxes to compare.
      </p>
      <p className="text-[11px] text-gray-400">
        {count === 0
          ? 'Nothing selected yet.'
          : '1 run currently selected — tick a second to enable side-by-side analysis.'}
      </p>
      <button
        type="button"
        onClick={onStartNewRun}
        className="rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
      >
        Or start a new run
      </button>
    </div>
  );
}

function CompareTabButton({
  id,
  activeTab,
  onSelect,
  icon,
  label,
}: {
  id: CompareTab;
  activeTab: CompareTab;
  onSelect: (tab: CompareTab) => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(id)}
      className={clsx(
        'flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-colors',
        activeTab === id ? 'bg-gray-900 text-white' : 'text-gray-600 hover:bg-gray-50',
      )}
    >
      {icon}
      {label}
    </button>
  );
}
