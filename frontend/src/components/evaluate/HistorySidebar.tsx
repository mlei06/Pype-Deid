import { useMemo } from 'react';
import { clsx } from 'clsx';
import { ChevronLeft, ChevronRight, Clock, X } from 'lucide-react';
import { useEvalRuns } from '../../hooks/useEvalRuns';
import type { EvalRunSummary } from '../../api/types';

type SelectionMode = 'single' | 'multi';

interface HistorySidebarProps {
  /**
   * In ``single`` mode: the first id is the active run; subsequent ids are ignored.
   * In ``multi`` mode: all ids participate in compare.
   */
  selectedRunIds: string[];
  selectionMode: SelectionMode;
  onSingleSelect: (id: string) => void;
  onToggle: (id: string) => void;
  onClear: () => void;
  collapsed: boolean;
  onCollapseChange: (collapsed: boolean) => void;
}

export default function HistorySidebar({
  selectedRunIds,
  selectionMode,
  onSingleSelect,
  onToggle,
  onClear,
  collapsed,
  onCollapseChange,
}: HistorySidebarProps) {
  const { data: runs, isLoading } = useEvalRuns();
  const selectedSet = useMemo(() => new Set(selectedRunIds), [selectedRunIds]);
  const showCheckboxes = selectionMode === 'multi';

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={() => onCollapseChange(false)}
        className="flex h-full w-9 flex-col items-center justify-start gap-3 border-r border-gray-200 bg-white py-3 text-gray-500 hover:bg-gray-50"
        aria-label="Expand history sidebar"
      >
        <ChevronRight size={16} />
        <span
          className="text-[10px] font-bold uppercase tracking-wider text-gray-400"
          style={{ writingMode: 'vertical-rl' }}
        >
          History
        </span>
      </button>
    );
  }

  return (
    <aside className="flex h-full w-72 flex-col border-r border-gray-200 bg-white">
      <div className="flex items-center justify-between border-b border-gray-200 px-3 py-2">
        <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-gray-500">
          <Clock size={12} />
          History
        </div>
        <button
          type="button"
          onClick={() => onCollapseChange(true)}
          className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          aria-label="Collapse history sidebar"
        >
          <ChevronLeft size={14} />
        </button>
      </div>

      <div className="flex items-center justify-between border-b border-gray-100 bg-gray-50/60 px-3 py-1.5 text-[11px] text-gray-600">
        <span>
          {selectionMode === 'single'
            ? selectedRunIds.length === 0
              ? 'No run selected'
              : 'Click a row to view'
            : selectedRunIds.length === 0
              ? 'Tick rows to compare'
              : selectedRunIds.length === 1
                ? '1 run selected · pick a second'
                : `${selectedRunIds.length} runs · compare view`}
        </span>
        {selectedRunIds.length > 0 && (
          <button
            type="button"
            onClick={onClear}
            className="inline-flex items-center gap-0.5 rounded text-[11px] font-medium text-gray-500 hover:text-gray-900"
          >
            <X size={11} />
            Clear
          </button>
        )}
      </div>

      <div className="flex-1 overflow-auto">
        {isLoading && (
          <p className="px-3 py-3 text-xs text-gray-400">Loading runs…</p>
        )}
        {!isLoading && runs && runs.length === 0 && (
          <p className="px-3 py-3 text-xs text-gray-400">No evaluation runs yet.</p>
        )}
        {runs && runs.length > 0 && (
          <ul className="divide-y divide-gray-100">
            {runs.map((r) => (
              <RunRow
                key={r.id}
                run={r}
                checked={selectedSet.has(r.id)}
                isPrimary={selectedRunIds[0] === r.id}
                showCheckbox={showCheckboxes}
                onSingleSelect={onSingleSelect}
                onToggle={onToggle}
              />
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}

interface RunRowProps {
  run: EvalRunSummary;
  checked: boolean;
  isPrimary: boolean;
  showCheckbox: boolean;
  onSingleSelect: (id: string) => void;
  onToggle: (id: string) => void;
}

function RunRow({
  run,
  checked,
  isPrimary,
  showCheckbox,
  onSingleSelect,
  onToggle,
}: RunRowProps) {
  // In multi-select (Compare), clicking the row body toggles inclusion — same as
  // the checkbox — so users can hit a wider target. In single-select (Results),
  // clicking the row replaces the selection.
  const handleRowClick = showCheckbox ? () => onToggle(run.id) : () => onSingleSelect(run.id);
  return (
    <li
      className={clsx(
        'group cursor-pointer px-3 py-2 transition-colors',
        isPrimary ? 'bg-blue-50' : checked ? 'bg-blue-50/40' : 'hover:bg-gray-50',
      )}
      onClick={handleRowClick}
    >
      <div className="flex items-start gap-2">
        {showCheckbox && (
          <input
            type="checkbox"
            checked={checked}
            onChange={() => onToggle(run.id)}
            onClick={(e) => e.stopPropagation()}
            className="mt-1 h-3.5 w-3.5 cursor-pointer"
            aria-label={`Toggle ${run.pipeline_name} for compare`}
          />
        )}
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs font-medium text-gray-800">{run.pipeline_name}</div>
          <div className="truncate text-[11px] text-gray-500">{run.dataset_source}</div>
          <div className="mt-1 flex items-center gap-2 text-[10px] text-gray-400">
            <span className="font-mono">{(run.strict_f1 * 100).toFixed(1)}% F1</span>
            <span>·</span>
            <span>{run.document_count} docs</span>
            <span>·</span>
            <span>{new Date(run.created_at).toLocaleDateString()}</span>
          </div>
        </div>
      </div>
    </li>
  );
}
