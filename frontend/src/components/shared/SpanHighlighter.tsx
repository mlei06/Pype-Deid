import {
  useEffect,
  useMemo,
  useRef,
  useCallback,
  useImperativeHandle,
  forwardRef,
  type MouseEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from 'react';
import { clsx } from 'clsx';
import { labelColor } from '../../lib/labelColors';
import { entitySpanKey, isRangeUncovered } from '../../lib/entitySpanKey';
import {
  buildCoverageSegments,
  findOverlapGroups,
  spanRangeKey,
  type CoverageSegment,
  type OverlapGroup,
} from '../../lib/spanOverlapConflicts';
import { scrollTextRangeIntoView } from '../../lib/scrollRangeIntoView';
import type { SpanLabelConflict } from '../../lib/traceConflicts';
import LabelBadge from './LabelBadge';
import type { EntitySpanResponse } from '../../api/types';

export interface SpanHighlighterHandle {
  scrollToRange: (start: number, end: number) => void;
  scrollToSpanKey: (key: string) => void;
}

interface SpanHighlighterProps {
  text: string;
  spans: EntitySpanResponse[];
  activeSpanKey?: string | null;
  flashSpanKey?: string | null;
  onSpanHover?: (key: string | null) => void;
  onSpanClick?: (span: EntitySpanResponse, key: string, anchor: DOMRect) => void;
  onUncoveredSelection?: (
    sel: { start: number; end: number; text: string },
    anchor: DOMRect,
  ) => void;
  onClearPendingSelection?: () => void;
  pendingGhostRange?: { start: number; end: number } | null;
  pulseRange?: { start: number; end: number } | null;
  conflictBySpanKey?: Map<string, SpanLabelConflict>;
  onConflictClick?: (c: SpanLabelConflict, anchor: DOMRect) => void;
  /**
   * Click handler for overlap-conflict strips (regions where 2+ spans cover the
   * same characters). Receives the *covering* spans for that strip, plus the
   * client rect of the click target so the consumer can position a popover or
   * focus the corresponding group.
   */
  onOverlapClick?: (spans: EntitySpanResponse[], anchor: DOMRect) => void;
  onSpanResize?: (key: string, start: number, end: number) => void;
}

function overlapsRange(a0: number, a1: number, b0: number, b1: number): boolean {
  return Math.max(a0, b0) < Math.min(a1, b1);
}

function offsetUpTo(root: HTMLElement, container: Node, offset: number): number {
  const r = document.createRange();
  r.setStart(root, 0);
  try {
    r.setEnd(container, offset);
  } catch {
    return 0;
  }
  const frag = r.cloneContents();
  frag.querySelectorAll('[data-no-offset="true"]').forEach((el) => el.remove());
  const holder = document.createElement('div');
  holder.appendChild(frag);
  return holder.textContent?.length ?? 0;
}

function rangeToTextOffsets(root: HTMLElement, range: Range): { start: number; end: number } | null {
  if (!root.contains(range.commonAncestorContainer)) return null;
  const start = offsetUpTo(root, range.startContainer, range.startOffset);
  const end = offsetUpTo(root, range.endContainer, range.endOffset);
  if (start > end) return null;
  return { start, end };
}

interface CaretPosResult {
  offsetNode: Node;
  offset: number;
}

function caretFromPoint(doc: Document, x: number, y: number): CaretPosResult | null {
  const anyDoc = doc as unknown as {
    caretPositionFromPoint?: (x: number, y: number) => CaretPosResult | null;
    caretRangeFromPoint?: (x: number, y: number) => Range | null;
  };
  if (typeof anyDoc.caretPositionFromPoint === 'function') {
    return anyDoc.caretPositionFromPoint(x, y);
  }
  if (typeof anyDoc.caretRangeFromPoint === 'function') {
    const r = anyDoc.caretRangeFromPoint(x, y);
    if (!r) return null;
    return { offsetNode: r.startContainer, offset: r.startOffset };
  }
  return null;
}

function textOffsetFromPoint(root: HTMLElement, x: number, y: number): number | null {
  const pos = caretFromPoint(root.ownerDocument, x, y);
  if (!pos || !root.contains(pos.offsetNode)) return null;
  return offsetUpTo(root, pos.offsetNode, pos.offset);
}

/**
 * Map client coordinates to a text offset, robust to pointer leaving the pre, thin hit targets,
 * and ``caretFromPoint`` returning null for points on padding / handles.
 * Clamps to the pre box and tries small horizontal/vertical nudges; for edge drags, biases
 * nudges so the caret lands in character cells (not on ``data-no-offset`` chrome).
 */
function textOffsetFromClientResilient(
  root: HTMLElement,
  clientX: number,
  clientY: number,
  side: 'left' | 'right' | null,
): number | null {
  const r = root.getBoundingClientRect();
  if (r.width <= 0 || r.height <= 0) return null;
  const preferX = side === 'left' ? 6 : side === 'right' ? -6 : 0;
  const nudgeXs = [0, preferX, 4, -4, 8, -8, 2, -2, 10, -10, 12, -12, 1, -1];
  const nudgeYs = [0, 1, -1, 2, -2, 3, -3, 4, -4];
  const seen = new Set<string>();
  for (const dy of nudgeYs) {
    for (const dx of nudgeXs) {
      const k = `${dx},${dy}`;
      if (seen.has(k)) continue;
      seen.add(k);
      const x = Math.min(Math.max(clientX + dx, r.left + 0.5), r.right - 0.5);
      const y = Math.min(Math.max(clientY + dy, r.top + 0.5), r.bottom - 0.5);
      const o = textOffsetFromPoint(root, x, y);
      if (o != null) return o;
    }
  }
  return null;
}

function PlainWithGhost({
  text,
  g0,
  g1,
  ghost,
  pulse,
}: {
  text: string;
  g0: number;
  g1: number;
  ghost: { start: number; end: number } | null | undefined;
  pulse?: { start: number; end: number } | null;
}) {
  if (!ghost && !pulse) return <>{text}</>;

  const cuts = new Set<number>([g0, g1]);
  if (ghost) {
    cuts.add(Math.max(g0, ghost.start));
    cuts.add(Math.min(g1, ghost.end));
  }
  if (pulse) {
    cuts.add(Math.max(g0, pulse.start));
    cuts.add(Math.min(g1, pulse.end));
  }
  const xs = [...cuts].filter((x) => x >= g0 && x <= g1).sort((a, b) => a - b);

  const out: ReactNode[] = [];
  for (let i = 0; i < xs.length - 1; i++) {
    const a = xs[i];
    const b = xs[i + 1];
    if (a >= b) continue;
    const slice = text.slice(a - g0, b - g0);
    const g = Boolean(ghost && overlapsRange(a, b, ghost.start, ghost.end));
    const p = Boolean(pulse && overlapsRange(a, b, pulse.start, pulse.end));
    out.push(
      <span
        key={`${a}-${b}`}
        className={clsx(
          g && 'rounded-sm bg-amber-100/90 ring-1 ring-amber-300/70',
          p && 'ring-2 ring-blue-500 ring-offset-1 animate-pulse',
        )}
      >
        {slice}
      </span>,
    );
  }
  return <>{out}</>;
}

const SpanHighlighter = forwardRef<SpanHighlighterHandle, SpanHighlighterProps>(
  function SpanHighlighter(
    {
      text,
      spans,
      activeSpanKey,
      flashSpanKey,
      onSpanHover,
      onSpanClick,
      onUncoveredSelection,
      onClearPendingSelection,
      pendingGhostRange,
      pulseRange,
      conflictBySpanKey,
      onConflictClick,
      onOverlapClick,
      onSpanResize,
    },
    ref,
  ) {
    const rootRef = useRef<HTMLPreElement>(null);
    const segments = useMemo<CoverageSegment[]>(
      () => buildCoverageSegments(text.length, spans),
      [text, spans],
    );

    const spanByKey = useMemo(() => {
      const m = new Map<string, EntitySpanResponse>();
      for (const s of spans) m.set(entitySpanKey(s), s);
      return m;
    }, [spans]);

    const siblingBounds = useMemo(() => {
      // Adjacency for resize handles. Two regimes:
      //  - Span is a member of an overlap group → clamp to the group's outer
      //    extent. Resize stays inside the visible conflict strip; the user
      //    can shrink to escape the conflict but can't expand past the group
      //    (which would silently absorb more spans or split the group).
      //  - Span is not in a group → clamp to the nearest non-overlapping
      //    sibling's edge (clean adjacency).
      const sorted = [...spans].sort((a, b) => a.start - b.start || a.end - b.end);
      const groups = findOverlapGroups(spans, text);
      const groupBySpanKey = new Map<string, OverlapGroup>();
      for (const g of groups) {
        for (const m of g.members) groupBySpanKey.set(entitySpanKey(m), g);
      }
      const m = new Map<string, { minStart: number; maxEnd: number }>();
      for (let i = 0; i < sorted.length; i++) {
        const s = sorted[i]!;
        const key = entitySpanKey(s);
        const g = groupBySpanKey.get(key);
        if (g) {
          m.set(key, { minStart: g.minStart, maxEnd: g.maxEnd });
          continue;
        }
        let minStart = 0;
        for (let j = i - 1; j >= 0; j--) {
          if (sorted[j]!.end <= s.start) {
            minStart = sorted[j]!.end;
            break;
          }
        }
        let maxEnd = text.length;
        for (let j = i + 1; j < sorted.length; j++) {
          if (sorted[j]!.start >= s.end) {
            maxEnd = sorted[j]!.start;
            break;
          }
        }
        m.set(key, { minStart, maxEnd });
      }
      return m;
    }, [spans, text]);

    /**
     * Drag state is a ref rather than state so pointermove doesn't re-run
     * effects. ``key`` is the *current* span key (rotates after each update
     * since the span's key is derived from start/end).
     */
    const dragRef = useRef<{
      key: string;
      side: 'left' | 'right';
      anchorStart: number;
      anchorEnd: number;
      label: string;
      minStart: number;
      maxEnd: number;
    } | null>(null);

    const onSpanResizeRef = useRef(onSpanResize);
    useEffect(() => {
      onSpanResizeRef.current = onSpanResize;
    }, [onSpanResize]);

    const beginResize = useCallback(
      (side: 'left' | 'right', span: EntitySpanResponse) => (e: ReactPointerEvent<HTMLSpanElement>) => {
        if (!onSpanResizeRef.current) return;
        e.stopPropagation();
        e.preventDefault();
        const key = entitySpanKey(span);
        const b = siblingBounds.get(key);
        if (!b) return;
        const el = e.currentTarget;
        el.setPointerCapture(e.pointerId);
        document.body.style.userSelect = 'none';
        dragRef.current = {
          key,
          side,
          anchorStart: span.start,
          anchorEnd: span.end,
          label: span.label,
          minStart: b.minStart,
          maxEnd: b.maxEnd,
        };
        const onMove = (ev: PointerEvent) => {
          const drag = dragRef.current;
          const root = rootRef.current;
          const cb = onSpanResizeRef.current;
          if (!drag || !root || !cb) return;
          const off = textOffsetFromClientResilient(root, ev.clientX, ev.clientY, drag.side);
          if (off == null) return;
          let newStart = drag.anchorStart;
          let newEnd = drag.anchorEnd;
          if (drag.side === 'left') {
            newStart = Math.min(drag.anchorEnd - 1, Math.max(drag.minStart, off));
          } else {
            newEnd = Math.max(drag.anchorStart + 1, Math.min(drag.maxEnd, off));
          }
          if (newStart === drag.anchorStart && newEnd === drag.anchorEnd) return;
          cb(drag.key, newStart, newEnd);
          /** Span key is derived from start:end:label — rotate it so the next call targets the updated span. */
          drag.key = `${newStart}-${newEnd}-${drag.label}`;
          if (drag.side === 'left') drag.anchorStart = newStart;
          else drag.anchorEnd = newEnd;
        };
        const onUp = (ev: PointerEvent) => {
          el.removeEventListener('pointermove', onMove);
          el.removeEventListener('pointerup', onUp);
          el.removeEventListener('pointercancel', onUp);
          try {
            if (el.hasPointerCapture(ev.pointerId)) {
              el.releasePointerCapture(ev.pointerId);
            }
          } catch {
            /* already released */
          }
          document.body.style.userSelect = '';
          dragRef.current = null;
        };
        el.addEventListener('pointermove', onMove);
        el.addEventListener('pointerup', onUp);
        el.addEventListener('pointercancel', onUp);
      },
      [siblingBounds],
    );

    useImperativeHandle(
      ref,
      () => ({
        scrollToRange: (start: number, end: number) => {
          if (!rootRef.current) return;
          scrollTextRangeIntoView(rootRef.current, text, start, end);
        },
        scrollToSpanKey: (key: string) => {
          const s = spanByKey.get(key);
          if (!s || !rootRef.current) return;
          scrollTextRangeIntoView(rootRef.current, text, s.start, s.end);
        },
      }),
      [text, spanByKey],
    );

    const handleMouseUp = useCallback(() => {
      if (!rootRef.current) return;
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed) {
        onClearPendingSelection?.();
        return;
      }
      const range = sel.getRangeAt(0);
      const offsets = rangeToTextOffsets(rootRef.current, range);
      if (!offsets) {
        onClearPendingSelection?.();
        return;
      }
      const { start, end } = offsets;
      const slice = text.slice(start, end);
      if (!slice.trim()) {
        onClearPendingSelection?.();
        return;
      }
      if (!isRangeUncovered(start, end, spans)) {
        onClearPendingSelection?.();
        return;
      }
      if (!onUncoveredSelection) return;
      const rect = range.getBoundingClientRect();
      onUncoveredSelection({ start, end, text: slice }, rect);
    }, [onClearPendingSelection, onUncoveredSelection, spans, text]);

    return (
      <pre
        ref={rootRef}
        onMouseUp={handleMouseUp}
        className="block w-full whitespace-pre-wrap break-words font-mono text-sm leading-relaxed"
      >
        {segments.map((seg, i) => {
          const sliceText = text.slice(seg.start, seg.end);
          if (seg.kind === 'plain') {
            return (
              <span key={i}>
                <PlainWithGhost
                  text={sliceText}
                  g0={seg.start}
                  g1={seg.end}
                  ghost={pendingGhostRange}
                  pulse={pulseRange}
                />
              </span>
            );
          }
          if (seg.kind === 'overlap') {
            const labels = [...new Set(seg.spans.map((s) => s.label))];
            const title = `Overlap conflict — ${labels.join(', ')}. Click to resolve.`;
            return (
              <mark
                key={i}
                data-overlap="true"
                className="group relative inline cursor-pointer rounded-sm px-0.5 ring-1 ring-rose-400/70 bg-rose-100/80"
                style={{
                  backgroundImage:
                    'repeating-linear-gradient(45deg, rgba(244,63,94,0.18) 0 4px, rgba(244,63,94,0.06) 4px 8px)',
                  borderBottom: '2px dashed rgb(225 29 72)',
                }}
                title={title}
                onClick={(e: MouseEvent<HTMLElement>) => {
                  e.stopPropagation();
                  if (!onOverlapClick) return;
                  const rect = e.currentTarget.getBoundingClientRect();
                  onOverlapClick(seg.spans, rect);
                }}
              >
                {sliceText}
              </mark>
            );
          }
          // seg.kind === 'span'
          const s = seg.span;
          const c = labelColor(s.label);
          const key = entitySpanKey(s);
          const rangeK = spanRangeKey(s.start, s.end);
          const isActive = activeSpanKey != null && activeSpanKey === key;
          const isFlash = flashSpanKey != null && flashSpanKey === key;
          const traceConflict = conflictBySpanKey?.get(key);
          const isLeftEdge = seg.start === s.start;
          const isRightEdge = seg.end === s.end;

          const baseTitle = `${s.label}${s.confidence != null ? ` (${(s.confidence * 100).toFixed(0)}%)` : ''}${s.source ? ` — ${s.source}` : ''}`;
          const title = traceConflict
            ? `Conflict: ${traceConflict.pipeA} → ${traceConflict.labelA} vs ${traceConflict.pipeB} → ${traceConflict.labelB}`
            : baseTitle;

          return (
            <mark
              key={i}
              data-span-key={key}
              data-range-key={rangeK}
              className={clsx(
                'group relative inline cursor-pointer rounded-sm px-0.5 transition-shadow',
                isActive && 'ring-2 ring-blue-500 ring-offset-1',
                isFlash && 'animate-pulse ring-2 ring-amber-400 ring-offset-1',
                traceConflict && 'border-2 border-dashed border-amber-500 bg-amber-50',
              )}
              style={
                traceConflict
                  ? undefined
                  : { backgroundColor: c.bg, borderBottom: `2px solid ${c.border}` }
              }
              title={title}
              onMouseEnter={() => onSpanHover?.(key)}
              onMouseLeave={() => onSpanHover?.(null)}
              onClick={(e: MouseEvent<HTMLElement>) => {
                e.stopPropagation();
                const rect = e.currentTarget.getBoundingClientRect();
                if (traceConflict && onConflictClick) {
                  onConflictClick(traceConflict, rect);
                  return;
                }
                onSpanClick?.(s, key, rect);
              }}
            >
              {isLeftEdge && (
                <LabelBadge label={s.label} className="absolute -top-4 left-0" data-no-offset="true" />
              )}
              {onSpanResize && isLeftEdge && (
                <span
                  data-no-offset="true"
                  aria-hidden="true"
                  onPointerDown={beginResize('left', s)}
                  className="absolute -left-1.5 top-0 bottom-0 z-10 w-3 min-w-[12px] cursor-ew-resize touch-none opacity-0 group-hover:opacity-100 bg-blue-500/60 rounded-sm"
                />
              )}
              {sliceText}
              {onSpanResize && isRightEdge && (
                <span
                  data-no-offset="true"
                  aria-hidden="true"
                  onPointerDown={beginResize('right', s)}
                  className="absolute -right-1.5 top-0 bottom-0 z-10 w-3 min-w-[12px] cursor-ew-resize touch-none opacity-0 group-hover:opacity-100 bg-blue-500/60 rounded-sm"
                />
              )}
            </mark>
          );
        })}
      </pre>
    );
  },
);

export default SpanHighlighter;
