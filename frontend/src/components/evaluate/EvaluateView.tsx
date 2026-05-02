import { useCallback, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Plus } from 'lucide-react';
import EvalModeNav from './EvalModeNav';
import { type EvalMode, parseEvalMode, parseRunIds, serializeRunIds } from './evalMode';
import EvalRunForm from './EvalRunForm';
import EvalDashboard from './EvalDashboard';
import HistorySidebar from './HistorySidebar';
import ComparePanel from './compare/ComparePanel';
import { useEvalRun } from '../../hooks/useEvalRuns';
import type { EvalRunDetail } from '../../api/types';

const SIDEBAR_STORAGE_KEY = 'evaluate.sidebar.collapsed';

function readInitialCollapsed(): boolean {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === '1';
}

export default function EvaluateView() {
  const [searchParams, setSearchParams] = useSearchParams();
  const mode = parseEvalMode(searchParams.get('mode'));
  // Results uses ``?run=`` (singular). Compare uses ``?runs=`` (plural). The two
  // selections are independent — switching modes does not cross-pollinate them.
  const resultsRunId = searchParams.get('run');
  const compareRunIds = parseRunIds(searchParams.get('runs'));

  const [latestRunResult, setLatestRunResult] = useState<EvalRunDetail | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(readInitialCollapsed);

  const { data: persistedRun } = useEvalRun(
    mode === 'results' ? resultsRunId : null,
  );
  const runForDashboard =
    latestRunResult && resultsRunId === latestRunResult.id ? latestRunResult : persistedRun;

  const updateParams = useCallback(
    (patch: Record<string, string | null>) => {
      setSearchParams(
        (prev) => {
          const params = new URLSearchParams(prev);
          for (const [k, v] of Object.entries(patch)) {
            if (v == null) params.delete(k);
            else params.set(k, v);
          }
          return params;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const setMode = useCallback(
    (next: EvalMode) => updateParams({ mode: next }),
    [updateParams],
  );

  const handleRunFinished = useCallback(
    (run: EvalRunDetail) => {
      setLatestRunResult(run);
      // Newly finished run lands in Results; keep Compare's selection alone.
      updateParams({ mode: 'results', run: run.id, tab: null });
    },
    [updateParams],
  );

  // Results sidebar — single select. Click a row → that's the active run.
  const handleResultsSelect = useCallback(
    (id: string) => updateParams({ run: id, tab: null }),
    [updateParams],
  );
  const handleResultsClear = useCallback(
    () => updateParams({ run: null, tab: null }),
    [updateParams],
  );

  // Compare sidebar — multi-select via checkboxes / row toggle.
  const handleCompareToggle = useCallback(
    (id: string) => {
      const idx = compareRunIds.indexOf(id);
      const next =
        idx >= 0
          ? [...compareRunIds.slice(0, idx), ...compareRunIds.slice(idx + 1)]
          : [...compareRunIds, id];
      updateParams({ runs: serializeRunIds(next) });
    },
    [compareRunIds, updateParams],
  );
  const handleCompareSingleSelect = useCallback(
    (id: string) => {
      // In Compare, ``onSingleSelect`` fires when a result-card name is clicked
      // ("view solo") — jump to Results with that run as the focus.
      updateParams({ mode: 'results', run: id, tab: null });
    },
    [updateParams],
  );
  const handleCompareClear = useCallback(
    () => updateParams({ runs: null, ctab: null }),
    [updateParams],
  );

  const handleSidebarCollapseChange = useCallback((collapsed: boolean) => {
    setSidebarCollapsed(collapsed);
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(SIDEBAR_STORAGE_KEY, collapsed ? '1' : '0');
    }
  }, []);

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-gray-200 bg-white px-6 pt-6 pb-3">
        <EvalModeNav
          mode={mode}
          onChange={setMode}
          resultsDisabled={!resultsRunId}
          compareDisabled={compareRunIds.length < 2}
          compareBadge={compareRunIds.length >= 2 ? compareRunIds.length : undefined}
        />
      </div>

      {mode === 'new' && (
        <div className="flex flex-1 flex-col gap-4 overflow-auto px-6 py-4">
          <EvalRunForm onResult={handleRunFinished} />
        </div>
      )}

      {mode === 'results' && (
        <div className="flex flex-1 overflow-hidden">
          <HistorySidebar
            selectedRunIds={resultsRunId ? [resultsRunId] : []}
            selectionMode="single"
            onSingleSelect={handleResultsSelect}
            onToggle={handleResultsSelect}
            onClear={handleResultsClear}
            collapsed={sidebarCollapsed}
            onCollapseChange={handleSidebarCollapseChange}
          />
          <div className="flex flex-1 flex-col gap-4 overflow-auto px-6 py-4">
            {!resultsRunId ? (
              <EmptyResultsState onNew={() => setMode('new')} />
            ) : runForDashboard ? (
              <EvalDashboard run={runForDashboard} />
            ) : (
              <div className="flex h-40 items-center justify-center text-sm text-gray-400">
                Loading run…
              </div>
            )}
          </div>
        </div>
      )}

      {mode === 'compare' && (
        <div className="flex flex-1 overflow-hidden">
          <HistorySidebar
            selectedRunIds={compareRunIds}
            selectionMode="multi"
            onSingleSelect={handleCompareSingleSelect}
            onToggle={handleCompareToggle}
            onClear={handleCompareClear}
            collapsed={sidebarCollapsed}
            onCollapseChange={handleSidebarCollapseChange}
          />
          <div className="flex flex-1 flex-col gap-4 overflow-auto px-6 py-4">
            <ComparePanel
              runIds={compareRunIds}
              onRemove={handleCompareToggle}
              onSelectSingle={handleCompareSingleSelect}
              onStartNewRun={() => setMode('new')}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function EmptyResultsState({ onNew }: { onNew: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-gray-200 bg-white py-16 text-sm text-gray-500">
      <p>Click a run in the sidebar — or start a new one.</p>
      <button
        type="button"
        onClick={onNew}
        className="inline-flex items-center gap-1.5 rounded-md bg-gray-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-gray-800"
      >
        <Plus size={12} />
        Start a new run
      </button>
    </div>
  );
}
