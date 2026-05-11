import { useState, useMemo } from 'react';
import { clsx } from 'clsx';
import { ChevronRight, ChevronDown, Clock } from 'lucide-react';
import SpanHighlighter from '../shared/SpanHighlighter';
import LabelBadge from '@shared/components/LabelBadge';
import { labelColor } from '@shared/lib/labelColors';
import {
  diffSpans,
  diffTextWords,
  buildSpanDiffUnits,
  buildSpanDiffSegments,
  computeFrameDiffStats,
  type SpanDiffUnit,
  type FrameDiffStats,
  type TextSeg,
} from '../../lib/traceDiff';
import type { TraceFrame, EntitySpanResponse } from '../../api/types';

interface TraceTimelineProps {
  frames: TraceFrame[];
}

type ViewMode = 'diff' | 'absolute';

function traceSpansToResponse(
  frame: TraceFrame,
): { text: string; spans: EntitySpanResponse[] } | null {
  if (!frame.document) return null;
  const text = frame.document.document.text;
  const spans: EntitySpanResponse[] = frame.document.spans.map((s) => ({
    ...s,
    text: text.slice(s.start, s.end),
  }));
  return { text, spans };
}

function DiffStatsBadge({ stats }: { stats: FrameDiffStats }) {
  const { addedSpans, removedSpans, textChanged, charDelta } = stats;
  const nothing = !addedSpans && !removedSpans && !textChanged;
  if (nothing) {
    return <span className="text-xs text-gray-300">no change</span>;
  }
  return (
    <span className="flex items-center gap-1.5 text-xs">
      {addedSpans > 0 && (
        <span className="rounded bg-emerald-100 px-1 text-[10px] font-medium text-emerald-800">
          +{addedSpans}
        </span>
      )}
      {removedSpans > 0 && (
        <span className="rounded bg-rose-100 px-1 text-[10px] font-medium text-rose-800">
          −{removedSpans}
        </span>
      )}
      {textChanged && (
        <span className="rounded bg-amber-100 px-1 text-[10px] font-medium text-amber-800">
          {charDelta >= 0 ? `+${charDelta}` : charDelta} chars
        </span>
      )}
    </span>
  );
}

function describeKept(span: EntitySpanResponse): string {
  const conf = span.confidence != null ? ` (${(span.confidence * 100).toFixed(0)}%)` : '';
  const src = span.source ? ` — ${span.source}` : '';
  return `${span.label}${conf}${src}`;
}

function describeAdded(span: EntitySpanResponse, currentPipe: string): string {
  const rule = span.source && span.source !== currentPipe ? ` — rule: ${span.source}` : '';
  return `${span.label} — added by ${currentPipe}${rule}`;
}

function describeRemoved(span: EntitySpanResponse, currentPipe: string): string {
  const origin = span.source ? ` — was detected by ${span.source}` : '';
  return `${span.label} — removed by ${currentPipe}${origin}`;
}

function describePrimary(unit: SpanDiffUnit<EntitySpanResponse>, currentPipe: string): string {
  switch (unit.status) {
    case 'kept':
      return describeKept(unit.primary);
    case 'added':
      return describeAdded(unit.primary, currentPipe);
    case 'removed':
      return describeRemoved(unit.primary, currentPipe);
  }
}

interface DiffMarkProps {
  unit: SpanDiffUnit<EntitySpanResponse>;
  currentPipe: string;
  text: string;
}

/**
 * One ``<mark>`` per diff unit. Uses the canonical category color so the
 * highlight matches stage-1 ``SpanHighlighter`` exactly. ``removed`` units
 * apply ``line-through`` and ``opacity: 0.5`` to the entire mark — text and
 * label badge inherit both, keeping the strike on the document text and the
 * badge text in sync.
 */
function DiffMark({ unit, currentPipe, text }: DiffMarkProps) {
  const c = labelColor(unit.primary.label);
  const isRemoved = unit.status === 'removed';
  /** Single ``diff-removed`` cascade lives on the ``<mark>``: opacity-50 +
   *  line-through dims and strikes everything inside (bg, border, document
   *  text, label badge) by the same amount, using the *same* category colors
   *  the absolute view uses for kept spans. The badge container also gets the
   *  line-through class explicitly so the strike crosses absolutely-positioned
   *  text in browsers that don't propagate text-decoration through abs boxes. */
  return (
    <mark
      className={clsx(
        'relative inline rounded-sm border px-0.5',
        isRemoved && 'opacity-50 line-through',
      )}
      style={{
        backgroundColor: c.bg,
        borderColor: c.border,
        color: c.text,
      }}
      title={describePrimary(unit, currentPipe)}
    >
      <span
        className={clsx(
          'absolute -top-4 left-0 flex items-center gap-1 whitespace-nowrap',
          isRemoved && 'line-through',
        )}
      >
        {unit.removedSiblings.map((r, j) => (
          <span
            key={`sib-${j}-${r.label}`}
            /** When the mark itself is already removed, siblings inherit the
             *  cascade. Apply our own dim/strike only when the primary is an
             *  *added* span at the same range (a reclassification). */
            className={isRemoved ? undefined : 'opacity-50 line-through'}
          >
            <LabelBadge label={r.label} title={describeRemoved(r, currentPipe)} />
          </span>
        ))}
        <LabelBadge label={unit.primary.label} title={describePrimary(unit, currentPipe)} />
      </span>
      {text}
    </mark>
  );
}

interface SpanDiffViewProps {
  text: string;
  currentSpans: EntitySpanResponse[];
  added: EntitySpanResponse[];
  removed: EntitySpanResponse[];
  currentPipe: string;
}

function SpanDiffView({ text, currentSpans, added, removed, currentPipe }: SpanDiffViewProps) {
  const units = useMemo(
    () => buildSpanDiffUnits(currentSpans, added, removed),
    [currentSpans, added, removed],
  );
  const segments = useMemo(
    () => buildSpanDiffSegments(text, units),
    [text, units],
  );
  return (
    <pre className="whitespace-pre-wrap break-words font-mono text-sm leading-relaxed">
      {segments.map((seg, i) => {
        if (seg.kind === 'plain') {
          return <span key={i}>{seg.text}</span>;
        }
        return (
          <DiffMark
            key={i}
            unit={seg.unit}
            currentPipe={currentPipe}
            text={seg.text}
          />
        );
      })}
    </pre>
  );
}

function TextDiffView({ segs }: { segs: TextSeg[] }) {
  return (
    <div className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-gray-700">
      {segs.map((seg, i) => (
        <span
          key={i}
          className={clsx(
            seg.kind === 'add' && 'rounded bg-emerald-100 px-0.5 text-emerald-900',
            seg.kind === 'remove' &&
              'rounded bg-rose-100 px-0.5 text-rose-800 line-through',
          )}
        >
          {seg.text}
        </span>
      ))}
    </div>
  );
}

export default function TraceTimeline({ frames }: TraceTimelineProps) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [mode, setMode] = useState<ViewMode>('diff');

  const toggle = (i: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  };

  const frameStats = useMemo(() => {
    return frames.map((frame, i) => {
      if (!frame.document) return null;
      const prior = i > 0 ? frames[i - 1] : null;
      /** First stage has no predecessor — treat its full output as "added" so
       *  the diff badge reads ``+N`` instead of falling back to the gray
       *  span-count label. */
      if (!prior?.document) {
        return {
          addedSpans: frame.document.spans.length,
          removedSpans: 0,
          textChanged: false,
          charDelta: 0,
        };
      }
      return computeFrameDiffStats(
        prior.document.document.text,
        prior.document.spans,
        frame.document.document.text,
        frame.document.spans,
      );
    });
  }, [frames]);

  return (
    <div className="rounded-lg border border-gray-200 bg-white">
      <div className="flex items-center justify-between border-b border-gray-200 px-4 py-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">
          Pipeline Trace ({frames.length} steps)
        </span>
        <div
          role="radiogroup"
          aria-label="Trace view mode"
          className="inline-flex items-center gap-0.5 rounded border border-gray-200 bg-white p-0.5"
        >
          {(['diff', 'absolute'] as const).map((m) => (
            <button
              key={m}
              type="button"
              role="radio"
              aria-checked={mode === m}
              onClick={() => setMode(m)}
              className={clsx(
                'rounded px-1.5 py-0.5 text-[10px] font-medium transition-colors',
                mode === m
                  ? 'bg-gray-900 text-white'
                  : 'text-gray-600 hover:bg-gray-100',
              )}
            >
              {m === 'diff' ? 'Diff' : 'Absolute'}
            </button>
          ))}
        </div>
      </div>
      <div className="divide-y divide-gray-100">
        {frames.map((frame, i) => {
          const isOpen = expanded.has(i);
          const doc = traceSpansToResponse(frame);
          const prior = i > 0 ? frames[i - 1] : null;
          const priorDoc = prior ? traceSpansToResponse(prior) : null;
          const stats = frameStats[i];
          /** First frame has no predecessor; render as absolute regardless of the toggle. */
          const effectiveMode: ViewMode = mode === 'diff' && stats ? 'diff' : 'absolute';

          return (
            <div key={i}>
              <button
                onClick={() => toggle(i)}
                className="flex w-full items-center gap-2 px-4 py-2.5 text-left hover:bg-gray-50"
              >
                {isOpen ? (
                  <ChevronDown size={14} className="text-gray-400" />
                ) : (
                  <ChevronRight size={14} className="text-gray-400" />
                )}
                <span className="flex-1 truncate text-sm font-medium text-gray-700">
                  {frame.pipe_type}
                </span>
                {mode === 'diff' && stats ? (
                  <DiffStatsBadge stats={stats} />
                ) : (
                  doc && (
                    <span className="text-xs text-gray-400">
                      {doc.spans.length} span{doc.spans.length !== 1 ? 's' : ''}
                    </span>
                  )
                )}
                {frame.elapsed_ms != null && (
                  <span className="flex items-center gap-0.5 text-xs text-gray-400">
                    <Clock size={11} />
                    {frame.elapsed_ms.toFixed(1)}ms
                  </span>
                )}
              </button>
              {isOpen && doc && (
                <div className="border-t border-gray-100 bg-gray-50 p-4">
                  {effectiveMode === 'diff' && priorDoc && stats ? (
                    stats.textChanged ? (
                      <TextDiffView segs={diffTextWords(priorDoc.text, doc.text)} />
                    ) : (
                      (() => {
                        const { added, removed } = diffSpans(priorDoc.spans, doc.spans);
                        return (
                          <SpanDiffView
                            text={doc.text}
                            currentSpans={doc.spans}
                            added={added}
                            removed={removed}
                            currentPipe={frame.pipe_type}
                          />
                        );
                      })()
                    )
                  ) : (
                    <SpanHighlighter text={doc.text} spans={doc.spans} />
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
