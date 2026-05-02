import { clsx } from 'clsx';
import { Plus, BarChart3, GitCompare } from 'lucide-react';
import type { EvalMode } from './evalMode';

interface EvalModeNavProps {
  mode: EvalMode;
  onChange: (mode: EvalMode) => void;
  /** When true, render the Results pill in a muted style — used when nothing is selected. */
  resultsDisabled?: boolean;
  /** When true, render the Compare pill in a muted style — used when fewer than 2 runs are selected. */
  compareDisabled?: boolean;
  /** Optional badge — shown on Compare to surface the selected run count. */
  compareBadge?: number;
}

const MODE_ITEMS: { id: EvalMode; label: string; icon: React.ReactNode }[] = [
  { id: 'new', label: 'New Run', icon: <Plus size={14} /> },
  { id: 'results', label: 'Results', icon: <BarChart3 size={14} /> },
  { id: 'compare', label: 'Compare', icon: <GitCompare size={14} /> },
];

export default function EvalModeNav({
  mode,
  onChange,
  resultsDisabled,
  compareDisabled,
  compareBadge,
}: EvalModeNavProps) {
  return (
    <div className="flex w-fit overflow-hidden rounded-lg border border-gray-200 bg-white">
      {MODE_ITEMS.map((m) => {
        const muted =
          (m.id === 'results' && resultsDisabled && mode !== 'results') ||
          (m.id === 'compare' && compareDisabled && mode !== 'compare');
        return (
          <button
            key={m.id}
            type="button"
            onClick={() => onChange(m.id)}
            className={clsx(
              'flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-colors',
              mode === m.id
                ? 'bg-gray-900 text-white'
                : muted
                  ? 'text-gray-300 hover:bg-gray-50'
                  : 'text-gray-600 hover:bg-gray-50',
            )}
          >
            {m.icon}
            {m.label}
            {m.id === 'compare' && compareBadge && compareBadge > 0 ? (
              <span
                className={clsx(
                  'ml-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px] font-semibold',
                  mode === m.id
                    ? 'bg-white/20 text-white'
                    : 'bg-indigo-100 text-indigo-800',
                )}
              >
                {compareBadge}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
