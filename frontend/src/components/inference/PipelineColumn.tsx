import { forwardRef, type ReactNode } from 'react';
import { Loader2, X, AlertTriangle, Clock } from 'lucide-react';
import SpanHighlighter from '../shared/SpanHighlighter';
import { entitySpanKey } from '@shared/lib/entitySpanKey';
import type { CompareEntry } from '../../hooks/useCompareInference';

interface PipelineColumnProps {
  pipelineName: string;
  entry: CompareEntry | undefined;
  onRemove?: () => void;
  pulseRange: { start: number; end: number } | null;
  onHoverRange: (range: { start: number; end: number } | null) => void;
  /** Optional ribbon below the header — used for compare summary chips. */
  headerExtra?: ReactNode;
}

const PipelineColumn = forwardRef<HTMLDivElement, PipelineColumnProps>(
  function PipelineColumn(
    { pipelineName, entry, onRemove, pulseRange, onHoverRange, headerExtra },
    scrollRef,
  ) {
    const status = entry?.status ?? 'idle';
    const result = entry?.result;
    const spans = result?.spans ?? [];

    return (
      <div className="flex min-h-0 min-w-0 flex-col rounded-md border border-gray-200 bg-white">
        <header className="flex shrink-0 items-center justify-between gap-2 border-b border-gray-100 bg-gray-50 px-2.5 py-1.5">
          <div className="flex min-w-0 items-center gap-2">
            <span
              className="truncate text-xs font-semibold text-gray-800"
              title={pipelineName}
            >
              {pipelineName}
            </span>
            {status === 'pending' && (
              <Loader2 size={11} className="animate-spin text-gray-400" />
            )}
            {status === 'success' && (
              <span className="flex items-center gap-1.5 text-[10px] tabular-nums text-gray-500">
                <span>
                  {spans.length} span{spans.length !== 1 ? 's' : ''}
                </span>
                {entry?.elapsedMs != null && (
                  <span className="flex items-center gap-0.5">
                    <Clock size={9} />
                    {entry.elapsedMs.toFixed(0)}ms
                  </span>
                )}
              </span>
            )}
            {status === 'error' && (
              <span className="flex items-center gap-1 text-[10px] text-red-600">
                <AlertTriangle size={11} /> error
              </span>
            )}
          </div>
          {onRemove && (
            <button
              type="button"
              onClick={onRemove}
              title="Remove this pipeline from comparison"
              className="rounded p-0.5 text-gray-400 hover:bg-gray-200 hover:text-gray-700"
            >
              <X size={12} />
            </button>
          )}
        </header>

        {headerExtra}

        <div
          ref={scrollRef}
          data-pipeline-doc-scroll={pipelineName}
          className="min-h-0 flex-1 overflow-auto px-3 py-2"
          onMouseLeave={() => onHoverRange(null)}
        >
          {status === 'pending' && (
            <div className="flex h-full items-center justify-center text-xs text-gray-400">
              <Loader2 size={14} className="mr-1.5 animate-spin" />
              Running…
            </div>
          )}
          {status === 'error' && (
            <div className="rounded border border-red-100 bg-red-50 px-2 py-1.5 text-xs text-red-700">
              {entry?.error ?? 'Run failed'}
            </div>
          )}
          {status === 'success' && result && (
            <SpanHighlighter
              text={result.original_text}
              spans={spans}
              pulseRange={pulseRange}
              onSpanHover={(key) => {
                if (!key) {
                  onHoverRange(null);
                  return;
                }
                const span = spans.find((s) => entitySpanKey(s) === key);
                if (span) onHoverRange({ start: span.start, end: span.end });
              }}
            />
          )}
          {status === 'idle' && (
            <p className="text-xs text-gray-400">Press Run to inference.</p>
          )}
        </div>
      </div>
    );
  },
);

export default PipelineColumn;
