import { useState } from 'react';
import { clsx } from 'clsx';
import { Eye, EyeOff, Columns2 } from 'lucide-react';
import SpanHighlighter from './SpanHighlighter';
import RedactedView from '@shared/components/RedactedView';
import LabelBadge from '@shared/components/LabelBadge';
import type { EntitySpanResponse } from '../../api/types';

type ViewMode = 'annotated' | 'redacted' | 'side-by-side';

export interface AnnotatedViewerInteractiveProps {
  activeSpanKey?: string | null;
  onSpanHover?: (key: string | null) => void;
  onSpanClick?: (span: EntitySpanResponse, key: string, anchor: DOMRect) => void;
  onUncoveredSelection?: (sel: { start: number; end: number; text: string }) => void;
}

interface AnnotatedDocumentViewerProps {
  originalText: string;
  redactedText: string;
  spans: EntitySpanResponse[];
  processingTimeMs?: number;
  pipelineName?: string;
  interactive?: AnnotatedViewerInteractiveProps;
  className?: string;
  contentClassName?: string;
}

export default function AnnotatedDocumentViewer({
  originalText,
  redactedText,
  spans,
  processingTimeMs,
  pipelineName,
  interactive,
  className,
  contentClassName,
}: AnnotatedDocumentViewerProps) {
  const [mode, setMode] = useState<ViewMode>('annotated');

  const uniqueLabels = [...new Set(spans.map((s) => s.label))].sort();

  const MODES: { value: ViewMode; label: string; icon: typeof Eye }[] = [
    { value: 'annotated', label: 'Annotated', icon: Eye },
    { value: 'redacted', label: 'Redacted', icon: EyeOff },
    { value: 'side-by-side', label: 'Side by Side', icon: Columns2 },
  ];

  const highlighterProps = interactive
    ? {
        activeSpanKey: interactive.activeSpanKey,
        onSpanHover: interactive.onSpanHover,
        onSpanClick: interactive.onSpanClick,
        onUncoveredSelection: interactive.onUncoveredSelection,
      }
    : {};

  return (
    <div className={clsx('flex min-h-0 flex-1 flex-col rounded-lg border border-gray-200 bg-white', className)}>
      {/* Header */}
      <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-gray-200 px-4 py-2">
        {pipelineName && (
          <span className="text-xs font-medium text-gray-500">
            Pipeline: <span className="text-gray-900">{pipelineName}</span>
          </span>
        )}
        {processingTimeMs != null && (
          <span className="text-xs text-gray-400">{processingTimeMs.toFixed(0)}ms</span>
        )}
        <span className="text-xs text-gray-400">
          {spans.length} span{spans.length !== 1 ? 's' : ''}
        </span>

        <div className="ml-auto flex gap-1">
          {MODES.map(({ value, label, icon: Icon }) => (
            <button
              key={value}
              type="button"
              onClick={() => setMode(value)}
              className={clsx(
                'flex items-center gap-1 rounded px-2 py-1 text-xs font-medium transition-colors',
                mode === value ? 'bg-gray-900 text-white' : 'text-gray-500 hover:bg-gray-100',
              )}
            >
              <Icon size={13} />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Label legend */}
      {uniqueLabels.length > 0 && (
        <div className="flex shrink-0 flex-wrap gap-1.5 border-b border-gray-100 px-4 py-2">
          {uniqueLabels.map((l) => (
            <LabelBadge key={l} label={l} />
          ))}
        </div>
      )}

      {/* Content */}
      <div
        className={clsx(
          'min-h-0 flex-1 overflow-auto p-4',
          mode === 'side-by-side' && 'grid grid-cols-2 gap-4',
          contentClassName,
        )}
      >
        {(mode === 'annotated' || mode === 'side-by-side') && (
          <div className="min-h-0 min-w-0">
            {mode === 'side-by-side' && (
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-gray-400">
                Annotated
              </div>
            )}
            <SpanHighlighter text={originalText} spans={spans} {...highlighterProps} />
          </div>
        )}
        {(mode === 'redacted' || mode === 'side-by-side') && (
          <div className="min-h-0 min-w-0">
            {mode === 'side-by-side' && (
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-gray-400">
                Redacted
              </div>
            )}
            <RedactedView text={redactedText} />
          </div>
        )}
      </div>
    </div>
  );
}
