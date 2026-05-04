import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react';
import TraceTimeline from './TraceTimeline';
import type { CompareEntry } from '../../hooks/useCompareInference';

interface TraceColumnProps {
  pipelineName: string;
  entry: CompareEntry | undefined;
  collapsed: boolean;
  onToggleCollapsed: () => void;
}

export default function TraceColumn({
  pipelineName,
  entry,
  collapsed,
  onToggleCollapsed,
}: TraceColumnProps) {
  const status = entry?.status ?? 'idle';
  const frames = entry?.result?.intermediary_trace ?? null;
  const stepCount = frames?.length ?? 0;

  return (
    <div className="flex min-h-0 min-w-0 flex-col rounded-md border border-gray-200 bg-white">
      <button
        type="button"
        onClick={onToggleCollapsed}
        className="flex shrink-0 items-center justify-between gap-2 border-b border-gray-100 bg-gray-50 px-2.5 py-1.5 text-left hover:bg-gray-100"
      >
        <div className="flex min-w-0 items-center gap-1.5">
          {collapsed ? (
            <ChevronRight size={12} className="text-gray-500" />
          ) : (
            <ChevronDown size={12} className="text-gray-500" />
          )}
          <span
            className="truncate text-xs font-semibold text-gray-700"
            title={pipelineName}
          >
            Trace · {pipelineName}
          </span>
        </div>
        <span className="text-[10px] tabular-nums text-gray-500">
          {status === 'pending' && (
            <Loader2 size={10} className="inline animate-spin" />
          )}
          {status === 'success' &&
            `${stepCount} step${stepCount !== 1 ? 's' : ''}`}
          {status === 'error' && 'error'}
        </span>
      </button>

      {!collapsed && (
        <div className="min-h-0 flex-1 overflow-auto p-2">
          {status === 'pending' && (
            <div className="flex items-center gap-1.5 text-xs text-gray-400">
              <Loader2 size={12} className="animate-spin" />
              Running…
            </div>
          )}
          {status === 'error' && (
            <p className="text-xs text-red-600">{entry?.error ?? 'Run failed'}</p>
          )}
          {status === 'success' && frames && frames.length > 0 ? (
            <TraceTimeline frames={frames} />
          ) : (
            status === 'success' && (
              <p className="text-xs text-gray-400">No trace for this run.</p>
            )
          )}
          {status === 'idle' && (
            <p className="text-xs text-gray-400">Press Run to inference.</p>
          )}
        </div>
      )}
    </div>
  );
}
