import { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import { clsx } from 'clsx';
import {
  Plus,
  RotateCcw,
  PanelRightClose,
  PanelRightOpen,
  Eye,
  EyeOff,
  Undo2,
  Redo2,
  Check,
  CheckCircle2,
  X,
  Tag,
} from 'lucide-react';
import SpanHighlighter, { type SpanHighlighterHandle } from '../shared/SpanHighlighter';
import LabelBadge from '../shared/LabelBadge';
import SpanEditor from '../shared/SpanEditor';
import ColorKeyPopover from '../shared/ColorKeyPopover';
import LabelCombobox from '../shared/LabelCombobox';
import { useConfirm } from '../shared/ConfirmDialog';
import PreviewColumn from './PreviewColumn';
import {
  effectiveSurrogateSeed,
  useProductionStore,
  type Dataset,
  type DatasetFile,
} from './store';
import { useAnnotationHistory } from './useAnnotationHistory';
import { entitySpanKey } from '../../lib/entitySpanKey';
import {
  findOverlapGroups,
  applyResolveStrategy,
  keepInOverlapGroup,
  dropOverlapGroup,
  pickPrimarySpan,
  type OverlapGroup,
  type ResolveStrategyId,
} from '../../lib/spanOverlapConflicts';
import type { EntitySpanResponse } from '../../api/types';

interface DocumentReviewerProps {
  datasetId: string;
  dataset: Dataset;
  file: DatasetFile;
  reviewer: string;
}

interface GhostSelection {
  start: number;
  end: number;
  text: string;
  left: number;
  top: number;
}

export default function DocumentReviewer({
  datasetId,
  dataset,
  file,
  reviewer,
}: DocumentReviewerProps) {
  const setFileSurrogateSeed = useProductionStore((s) => s.setFileSurrogateSeed);
  const setFileResolved = useProductionStore((s) => s.setFileResolved);
  const showSpanLabels = useProductionStore((s) => s.showSpanLabels);
  const setShowSpanLabels = useProductionStore((s) => s.setShowSpanLabels);
  const confirm = useConfirm();
  const history = useAnnotationHistory(datasetId, file.id);
  const { commit, undo, redo, canUndo, canRedo, lastChangeAt } = history;

  const [activeSpanKey, setActiveSpanKey] = useState<string | null>(null);
  const [flashSpanKey, setFlashSpanKey] = useState<string | null>(null);
  const [ghostSelection, setGhostSelection] = useState<GhostSelection | null>(null);
  const [pulseRange, setPulseRange] = useState<{ start: number; end: number } | null>(null);
  const [addLabel, setAddLabel] = useState<string>('OTHER');
  const [previewOpen, setPreviewOpen] = useState(false);
  const [editorOpen, setEditorOpen] = useState(true);
  const [spanPopover, setSpanPopover] = useState<{
    key: string;
    span: EntitySpanResponse;
    left: number;
    top: number;
  } | null>(null);
  const [conflictPopover, setConflictPopover] = useState<{
    groupId: string;
    keptKey: string | null;
    left: number;
    top: number;
  } | null>(null);
  const rootRef = useRef<HTMLElement | null>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const conflictPopoverRef = useRef<HTMLDivElement>(null);
  const ghostPopoverRef = useRef<HTMLDivElement>(null);
  const highlighterRef = useRef<SpanHighlighterHandle>(null);

  useEffect(() => {
    setActiveSpanKey(null);
    setFlashSpanKey(null);
    setGhostSelection(null);
    setPulseRange(null);
    setSpanPopover(null);
    setConflictPopover(null);
  }, [file.id]);

  useEffect(() => {
    if (!spanPopover) return;
    const onDown = (e: MouseEvent) => {
      if (popoverRef.current?.contains(e.target as Node)) return;
      setSpanPopover(null);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [spanPopover]);

  // When a span popover opens, move focus to its container. Without this,
  // focus often stays on a previously-focused input (e.g. a label combobox in
  // the rail), and ⌫ / Delete would edit that field instead of removing the
  // span. With focus on the popover div (not an input), the keydown handler
  // sees inField=false and runs the delete branch.
  useEffect(() => {
    if (!spanPopover) return;
    const id = window.requestAnimationFrame(() => {
      popoverRef.current?.focus();
    });
    return () => window.cancelAnimationFrame(id);
  }, [spanPopover?.key]);

  useEffect(() => {
    if (!ghostSelection) return;
    const onDown = (e: MouseEvent) => {
      if (ghostPopoverRef.current?.contains(e.target as Node)) return;
      // Selection-on-document path clears via SpanHighlighter's mouseup; this
      // covers clicks outside the document (rail, header, etc.).
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setGhostSelection(null);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [ghostSelection]);

  useEffect(() => {
    if (!conflictPopover) return;
    const onDown = (e: MouseEvent) => {
      if (conflictPopoverRef.current?.contains(e.target as Node)) return;
      setConflictPopover(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setConflictPopover(null);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [conflictPopover]);

  useEffect(() => {
    if (!flashSpanKey) return;
    const t = setTimeout(() => setFlashSpanKey(null), 1200);
    return () => clearTimeout(t);
  }, [flashSpanKey]);

  useEffect(() => {
    if (!pulseRange) return;
    const t = setTimeout(() => setPulseRange(null), 1200);
    return () => clearTimeout(t);
  }, [pulseRange]);

  const uniqueLabels = useMemo(
    () => [...new Set(file.annotations.map((s) => s.label))].sort(),
    [file.annotations],
  );

  const annotationsDiffer = useMemo(() => {
    const detected = file.detectedAt ?? [];
    if (file.annotations.length !== detected.length) return true;
    return file.annotations.some((s, i) => {
      const o = detected[i];
      return !o || s.start !== o.start || s.end !== o.end || s.label !== o.label;
    });
  }, [file.annotations, file.detectedAt]);

  const overlapGroups = useMemo(
    () => findOverlapGroups(file.annotations, file.originalText),
    [file.annotations, file.originalText],
  );

  const groupBySpanKey = useMemo(() => {
    const m = new Map<string, OverlapGroup>();
    for (const g of overlapGroups) {
      for (const s of g.members) m.set(entitySpanKey(s), g);
    }
    return m;
  }, [overlapGroups]);

  const handleChangeSpans = (spans: EntitySpanResponse[]) => {
    commit(spans);
  };

  const updateSpanByKey = (key: string, patch: Partial<EntitySpanResponse>) => {
    const next = file.annotations.map((s) => (entitySpanKey(s) === key ? { ...s, ...patch } : s));
    commit(next);
  };

  const deleteSpanByKey = (key: string) => {
    const next = file.annotations.filter((s) => entitySpanKey(s) !== key);
    commit(next);
    setSpanPopover(null);
    setActiveSpanKey((ak) => (ak === key ? null : ak));
  };

  const deleteSpanByKeyRef = useRef(deleteSpanByKey);
  deleteSpanByKeyRef.current = deleteSpanByKey;

  const handleSpanResize = useCallback(
    (key: string, start: number, end: number) => {
      const f = useProductionStore
        .getState()
        .datasets[datasetId]?.files.find((x) => x.id === file.id);
      if (!f) return;
      commit(
        f.annotations.map((s) =>
          entitySpanKey(s) === key
            ? { ...s, start, end, text: f.originalText.slice(start, end) }
            : s,
        ),
      );
    },
    [datasetId, file.id, commit],
  );

  const handleReset = useCallback(async () => {
    if (!file.detectedAt) return;
    const manualCount = file.annotations.filter((s) => s.source === 'manual').length;
    if (manualCount > 0) {
      const ok = await confirm({
        title: 'Discard manual edits?',
        message: `Reset will replace the current spans with the last detection output. ${manualCount} manually added span${
          manualCount === 1 ? '' : 's'
        } will be discarded. You can undo this afterwards.`,
        confirmLabel: 'Reset',
        danger: true,
      });
      if (!ok) return;
    }
    commit(file.detectedAt);
  }, [confirm, file.annotations, file.detectedAt, commit]);

  const clearTransientForKeys = useCallback((droppedKeys: Set<string>) => {
    if (droppedKeys.size === 0) return;
    setActiveSpanKey((prev) => (prev != null && droppedKeys.has(prev) ? null : prev));
    setFlashSpanKey((prev) => (prev != null && droppedKeys.has(prev) ? null : prev));
    setSpanPopover((prev) => (prev != null && droppedKeys.has(prev.key) ? null : prev));
    setPulseRange(null);
  }, []);

  const handleResolveGroupKeep = useCallback(
    (group: OverlapGroup, kept: EntitySpanResponse) => {
      const keptKey = entitySpanKey(kept);
      const dropped = new Set<string>();
      for (const m of group.members) {
        const k = entitySpanKey(m);
        if (k !== keptKey) dropped.add(k);
      }
      clearTransientForKeys(dropped);
      commit(keepInOverlapGroup(file.annotations, group, kept));
    },
    [file.annotations, commit, clearTransientForKeys],
  );

  const handleResolveGroupDrop = useCallback(
    (group: OverlapGroup) => {
      const dropped = new Set(group.members.map((m) => entitySpanKey(m)));
      clearTransientForKeys(dropped);
      commit(dropOverlapGroup(file.annotations, group));
    },
    [file.annotations, commit, clearTransientForKeys],
  );

  const handleResolveAllOverlaps = useCallback(
    (strategy: ResolveStrategyId) => {
      const next = applyResolveStrategy(file.annotations, strategy);
      const survivors = new Set(next.map((s) => entitySpanKey(s)));
      const dropped = new Set<string>();
      for (const s of file.annotations) {
        const k = entitySpanKey(s);
        if (!survivors.has(k)) dropped.add(k);
      }
      clearTransientForKeys(dropped);
      commit(next);
    },
    [file.annotations, commit, clearTransientForKeys],
  );

  const focusGroup = useCallback((group: OverlapGroup) => {
    const preferred = group.members[0];
    if (preferred) setActiveSpanKey(entitySpanKey(preferred));
    setPulseRange({ start: group.minStart, end: group.maxEnd });
    highlighterRef.current?.scrollToRange(group.minStart, group.maxEnd);
  }, []);

  const addSpanFromGhost = (labelOverride?: string) => {
    if (!ghostSelection) return;
    const label = (labelOverride ?? addLabel).trim() || 'OTHER';
    const exists = file.annotations.some(
      (s) =>
        s.start === ghostSelection.start &&
        s.end === ghostSelection.end &&
        s.label === label,
    );
    if (!exists) {
      const next: EntitySpanResponse = {
        start: ghostSelection.start,
        end: ghostSelection.end,
        label,
        text: ghostSelection.text,
        confidence: null,
        source: 'manual',
      };
      const merged = [...file.annotations, next].sort(
        (a, b) => a.start - b.start || a.end - b.end,
      );
      commit(merged);
      setFlashSpanKey(entitySpanKey(next));
    }
    if (labelOverride) setAddLabel(label);
    setGhostSelection(null);
  };

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const onKey = (e: KeyboardEvent) => {
      const activeEl = document.activeElement as HTMLElement | null;
      const inField =
        !!activeEl &&
        (activeEl.tagName === 'INPUT' ||
          activeEl.tagName === 'TEXTAREA' ||
          activeEl.tagName === 'SELECT' ||
          activeEl.isContentEditable);

      // Cmd/Ctrl+Z, Cmd/Ctrl+Shift+Z — annotation undo/redo. Skip when typing
      // in a field (the field's native undo wins).
      if ((e.metaKey || e.ctrlKey) && !e.altKey && (e.key === 'z' || e.key === 'Z')) {
        if (inField) return;
        e.preventDefault();
        if (e.shiftKey) {
          if (canRedo) redo();
        } else {
          if (canUndo) undo();
        }
        return;
      }

      // Backspace / Delete — remove the currently selected (popover) or
      // hovered span. Skip when typing in a field or when a ghost selection
      // is pending (Esc dismisses that first).
      if (
        (e.key === 'Backspace' || e.key === 'Delete') &&
        !inField &&
        !ghostSelection
      ) {
        const target = spanPopover?.key ?? activeSpanKey;
        if (target) {
          e.preventDefault();
          deleteSpanByKeyRef.current(target);
          return;
        }
      }

      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (!activeEl || !root.contains(activeEl)) return;
      if (inField) return;
      if ((e.key === 'Enter' || e.key === ' ') && ghostSelection) {
        e.preventDefault();
        addSpanFromGhost();
        return;
      }
      if (e.key === ']' || e.key === '[') {
        if (overlapGroups.length === 0) return;
        e.preventDefault();
        const direction: 1 | -1 = e.key === ']' ? 1 : -1;
        const currentIdx =
          activeSpanKey != null
            ? overlapGroups.findIndex((g) => g.id === groupBySpanKey.get(activeSpanKey)?.id)
            : -1;
        const nextIdx =
          currentIdx < 0
            ? direction > 0
              ? 0
              : overlapGroups.length - 1
            : (currentIdx + direction + overlapGroups.length) % overlapGroups.length;
        focusGroup(overlapGroups[nextIdx]!);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [
    activeSpanKey,
    overlapGroups,
    groupBySpanKey,
    ghostSelection,
    focusGroup,
    canUndo,
    canRedo,
    undo,
    redo,
    spanPopover,
  ]);

  const seed = effectiveSurrogateSeed(file, dataset);

  return (
    <section ref={rootRef} className="flex min-h-0 flex-1 flex-col" tabIndex={-1}>
      <header className="flex flex-wrap items-center gap-3 border-b border-gray-200 bg-white px-4 py-2 shadow-sm">
        <div className="flex min-w-0 flex-col">
          <span className="truncate text-sm font-medium text-gray-900">
            {file.sourceLabel}
          </span>
          <span className="text-[11px] text-gray-400">
            {file.originalText.length} chars · {file.annotations.length} spans
            {file.processingTimeMs != null && ` · ${file.processingTimeMs.toFixed(0)}ms detect`}
            {file.lastDetectionTarget && ` · via ${file.lastDetectionTarget}`}
          </span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <ColorKeyPopover />
          {uniqueLabels.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {uniqueLabels.slice(0, 5).map((l) => (
                <LabelBadge key={l} label={l} />
              ))}
              {uniqueLabels.length > 5 && (
                <span className="text-[10px] text-gray-400">+{uniqueLabels.length - 5}</span>
              )}
            </div>
          )}
          <SavedIndicator
            lastChangeAt={lastChangeAt}
            isDirty={annotationsDiffer}
          />
          <div className="flex items-center gap-0.5 rounded border border-gray-200 bg-white p-0.5">
            <button
              type="button"
              onClick={undo}
              disabled={!canUndo}
              className={clsx(
                'inline-flex items-center rounded px-1.5 py-1 text-xs font-medium',
                canUndo
                  ? 'text-gray-700 hover:bg-gray-100'
                  : 'cursor-not-allowed text-gray-300',
              )}
              title="Undo (⌘/Ctrl+Z)"
              aria-label="Undo last span edit"
            >
              <Undo2 size={12} />
            </button>
            <button
              type="button"
              onClick={redo}
              disabled={!canRedo}
              className={clsx(
                'inline-flex items-center rounded px-1.5 py-1 text-xs font-medium',
                canRedo
                  ? 'text-gray-700 hover:bg-gray-100'
                  : 'cursor-not-allowed text-gray-300',
              )}
              title="Redo (⌘/Ctrl+Shift+Z)"
              aria-label="Redo span edit"
            >
              <Redo2 size={12} />
            </button>
          </div>
          {annotationsDiffer && (
            <button
              type="button"
              onClick={() => void handleReset()}
              className="inline-flex items-center gap-1 rounded border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 shadow-sm hover:bg-gray-50"
              title="Reset spans to last detection output"
            >
              <RotateCcw size={12} />
              Reset
            </button>
          )}
          <button
            type="button"
            onClick={() => setFileResolved(datasetId, file.id, !file.resolved)}
            className={clsx(
              'inline-flex items-center gap-1 rounded border px-3 py-1.5 text-xs font-medium shadow-sm',
              file.resolved
                ? 'border-emerald-200 bg-emerald-50 text-emerald-800 hover:bg-emerald-100'
                : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50',
            )}
            title={
              file.resolved
                ? 'Resolved — click to mark unresolved (R)'
                : 'Mark this file resolved (R)'
            }
            aria-pressed={file.resolved}
          >
            <CheckCircle2
              size={12}
              className={file.resolved ? 'text-emerald-600' : 'text-gray-400'}
            />
            {file.resolved ? 'Resolved' : 'Mark resolved'}
          </button>
          <div className="flex items-center gap-1 rounded border border-gray-200 bg-white p-0.5">
            <button
              type="button"
              onClick={() => setShowSpanLabels(!showSpanLabels)}
              className={clsx(
                'inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium',
                showSpanLabels
                  ? 'bg-gray-100 text-gray-800'
                  : 'text-gray-500 hover:bg-gray-50',
              )}
              title={
                showSpanLabels
                  ? 'Hide label badges (color underline + hover tooltip stay)'
                  : 'Show label badges'
              }
              aria-pressed={showSpanLabels}
            >
              <Tag size={12} className={showSpanLabels ? '' : 'opacity-40'} />
              Labels
            </button>
            <button
              type="button"
              onClick={() => setEditorOpen((v) => !v)}
              className={`inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium ${
                editorOpen ? 'bg-gray-100 text-gray-800' : 'text-gray-500 hover:bg-gray-50'
              }`}
              title={editorOpen ? 'Hide span editor' : 'Show span editor'}
            >
              {editorOpen ? <PanelRightClose size={12} /> : <PanelRightOpen size={12} />}
              Editor
            </button>
            <button
              type="button"
              onClick={() => setPreviewOpen((v) => !v)}
              className={`inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium ${
                previewOpen ? 'bg-gray-100 text-gray-800' : 'text-gray-500 hover:bg-gray-50'
              }`}
              title={previewOpen ? 'Hide redacted / surrogate preview' : 'Show redacted / surrogate preview'}
            >
              {previewOpen ? <EyeOff size={12} /> : <Eye size={12} />}
              Preview
            </button>
          </div>
        </div>
      </header>

      <div className="flex min-h-0 min-w-0 flex-1 flex-row overflow-hidden">
        <div
          className={`relative flex min-h-0 min-w-0 flex-1 flex-col overflow-auto p-4 ${
            editorOpen && !previewOpen ? 'max-w-[860px]' : ''
          }`}
        >
          <SpanHighlighter
            ref={highlighterRef}
            text={file.originalText}
            spans={file.annotations}
            activeSpanKey={activeSpanKey}
            flashSpanKey={flashSpanKey}
            showLabels={showSpanLabels}
            onSpanHover={setActiveSpanKey}
            onSpanClick={(span, key, anchor) => {
              setConflictPopover(null);
              setSpanPopover({
                key,
                span,
                left: Math.max(8, Math.min(anchor.left, window.innerWidth - 240)),
                top: anchor.bottom + 6,
              });
            }}
            onUncoveredSelection={(sel, anchor) => {
              const POPOVER_W = 280;
              const POPOVER_H_BELOW = 96;
              const left = Math.max(
                8,
                Math.min(anchor.left, window.innerWidth - POPOVER_W - 8),
              );
              const fitsBelow =
                anchor.bottom + POPOVER_H_BELOW + 12 < window.innerHeight;
              const top = fitsBelow
                ? anchor.bottom + 6
                : Math.max(8, anchor.top - POPOVER_H_BELOW - 6);
              setGhostSelection({ ...sel, left, top });
            }}
            onClearPendingSelection={() => setGhostSelection(null)}
            pendingGhostRange={ghostSelection}
            pulseRange={pulseRange}
            onOverlapClick={(spans, anchor) => {
              const member = spans[0];
              if (!member) return;
              const group = groupBySpanKey.get(entitySpanKey(member));
              if (!group) return;
              setSpanPopover(null);
              focusGroup(group);
              const primary = pickPrimarySpan(group.members);
              setConflictPopover({
                groupId: group.id,
                keptKey: entitySpanKey(primary),
                left: Math.max(8, Math.min(anchor.left, window.innerWidth - 280)),
                top: anchor.bottom + 6,
              });
            }}
            onSpanResize={handleSpanResize}
          />
        </div>
        {editorOpen && (
          <aside
            className={`flex min-w-[280px] flex-col border-l border-gray-200 bg-gray-50/90 ${
              previewOpen
                ? 'w-[min(38%,520px)] max-w-[560px] shrink-0'
                : 'flex-1'
            }`}
          >
            <SpanEditor
              originalText={file.originalText}
              spans={file.annotations}
              onChange={handleChangeSpans}
              onReset={handleReset}
              isApplying={false}
              isDirty={annotationsDiffer}
              error={null}
              ghostSelection={ghostSelection}
              onClearGhostSelection={() => setGhostSelection(null)}
              onNavigateToGhost={() => {
                if (!ghostSelection) return;
                highlighterRef.current?.scrollToRange(ghostSelection.start, ghostSelection.end);
                setPulseRange({ start: ghostSelection.start, end: ghostSelection.end });
              }}
              activeSpanKey={activeSpanKey}
              onActiveSpanKeyChange={setActiveSpanKey}
              overlapGroups={overlapGroups}
              onResolveGroupKeep={handleResolveGroupKeep}
              onResolveGroupDrop={handleResolveGroupDrop}
              onResolveAllOverlaps={handleResolveAllOverlaps}
              showGhostPanel={false}
            />
          </aside>
        )}
        {previewOpen && (
          <div className="flex w-[min(40%,560px)] min-w-[300px] max-w-[640px] shrink-0">
            <PreviewColumn
              datasetId={datasetId}
              fileId={file.id}
              originalText={file.originalText}
              annotations={file.annotations}
              reviewer={reviewer}
              seed={seed}
              onSeedChange={(s) => setFileSurrogateSeed(datasetId, file.id, s)}
              onClose={() => setPreviewOpen(false)}
            />
          </div>
        )}
      </div>

      {ghostSelection && (
        <div
          ref={ghostPopoverRef}
          className="fixed z-50 w-[280px] rounded-lg border border-amber-300 bg-amber-50 p-2 shadow-lg"
          style={{ left: ghostSelection.left, top: ghostSelection.top }}
          role="dialog"
          aria-label="Add new span"
          onMouseDown={(e) => e.stopPropagation()}
        >
          <div className="mb-1.5 flex items-baseline justify-between gap-2">
            <span className="text-[10px] font-semibold uppercase text-amber-800">
              Add span
            </span>
            <span className="text-[9px] text-amber-700/70">
              [{ghostSelection.start}-{ghostSelection.end}]
            </span>
          </div>
          <div className="mb-2 line-clamp-2 break-all rounded border border-amber-200 bg-white/70 px-1.5 py-1 font-mono text-[10px] text-amber-950">
            {ghostSelection.text.length > 120
              ? `${ghostSelection.text.slice(0, 120)}…`
              : ghostSelection.text}
          </div>
          <div className="mb-2">
            <LabelCombobox
              value={addLabel}
              onCommit={(next) => addSpanFromGhost(next)}
              onCancel={() => setGhostSelection(null)}
              extraSuggestions={uniqueLabels}
              autoFocus
              ariaLabel="Label for new span"
              placeholder="Type label, then Enter"
            />
          </div>
          <div className="flex items-center justify-between gap-1">
            <button
              type="button"
              onClick={() => setGhostSelection(null)}
              className="text-[10px] text-amber-800/80 underline hover:text-amber-950"
            >
              Cancel (Esc)
            </button>
            <button
              type="button"
              onClick={() => addSpanFromGhost()}
              className="inline-flex items-center gap-1 rounded bg-amber-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-amber-700"
            >
              <Plus size={11} />
              Add span
            </button>
          </div>
        </div>
      )}

      {spanPopover && (
        <div
          ref={popoverRef}
          tabIndex={-1}
          className="fixed z-50 w-60 rounded-lg border border-gray-200 bg-white p-2 shadow-lg outline-none"
          style={{ left: spanPopover.left, top: spanPopover.top }}
        >
          <div className="mb-1.5 flex items-baseline justify-between gap-2">
            <span className="text-[10px] font-semibold uppercase text-gray-500">
              Span label
            </span>
            <span className="text-[9px] text-gray-400">
              [{spanPopover.span.start}-{spanPopover.span.end}]
            </span>
          </div>
          <div className="mb-2 truncate text-[11px] font-medium text-gray-800">
            {spanPopover.span.label}
          </div>
          <div className="mb-2">
            <LabelCombobox
              value={spanPopover.span.label}
              onCommit={(next) => {
                if (next === spanPopover.span.label) {
                  setSpanPopover(null);
                  return;
                }
                updateSpanByKey(spanPopover.key, { label: next });
                setSpanPopover((p) =>
                  p ? { ...p, span: { ...p.span, label: next } } : null,
                );
              }}
              onCancel={() => setSpanPopover(null)}
              extraSuggestions={uniqueLabels}
              ariaLabel="Change span label"
              placeholder="Change label…"
            />
          </div>
          <button
            type="button"
            onClick={() => deleteSpanByKey(spanPopover.key)}
            className="w-full rounded border border-red-100 bg-red-50 px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-100"
            title="Delete span (⌫ / Delete)"
          >
            Delete span
          </button>
        </div>
      )}

      {conflictPopover &&
        (() => {
          const group = overlapGroups.find((g) => g.id === conflictPopover.groupId);
          if (!group) return null;
          const dropMode = conflictPopover.keptKey === '__drop_all__';
          const excerpt =
            group.excerpt.length > 60 ? `${group.excerpt.slice(0, 60)}…` : group.excerpt;
          return (
            <div
              ref={conflictPopoverRef}
              className="fixed z-50 w-72 rounded-lg border border-amber-200 bg-white p-2 shadow-lg"
              style={{ left: conflictPopover.left, top: conflictPopover.top }}
              role="dialog"
              aria-label="Resolve overlap conflict"
            >
              <div className="mb-1.5 flex items-center justify-between">
                <span className="text-[10px] font-semibold uppercase text-amber-700">
                  Overlap conflict
                </span>
                <button
                  type="button"
                  onClick={() => setConflictPopover(null)}
                  className="rounded p-0.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                  aria-label="Close"
                >
                  <X size={12} />
                </button>
              </div>
              <div className="mb-2 font-mono text-[10px] text-gray-700">
                {excerpt}{' '}
                <span className="text-gray-400">
                  [{group.minStart}–{group.maxEnd}]
                </span>
              </div>
              <div className="mb-2 space-y-1">
                {group.members.map((s) => {
                  const id = entitySpanKey(s);
                  return (
                    <label
                      key={id}
                      className="flex cursor-pointer items-start gap-2 text-[11px] text-gray-700"
                    >
                      <input
                        type="radio"
                        name={`inline-conflict-${group.id}`}
                        className="mt-0.5"
                        checked={conflictPopover.keptKey === id}
                        onChange={() =>
                          setConflictPopover((p) => (p ? { ...p, keptKey: id } : null))
                        }
                      />
                      <span>
                        <span className="font-semibold">{s.label}</span>{' '}
                        <span className="text-gray-500">
                          [{s.start}–{s.end}]
                          {s.source && ` · ${s.source}`}
                        </span>
                      </span>
                    </label>
                  );
                })}
                <label className="flex cursor-pointer items-start gap-2 text-[11px] text-gray-700">
                  <input
                    type="radio"
                    name={`inline-conflict-${group.id}`}
                    className="mt-0.5"
                    checked={conflictPopover.keptKey === '__drop_all__'}
                    onChange={() =>
                      setConflictPopover((p) =>
                        p ? { ...p, keptKey: '__drop_all__' } : null,
                      )
                    }
                  />
                  <span className="text-red-700">
                    <span className="font-semibold">Keep none</span>{' '}
                    <span className="text-gray-500">(drop every span)</span>
                  </span>
                </label>
              </div>
              <button
                type="button"
                onClick={() => {
                  if (dropMode) {
                    handleResolveGroupDrop(group);
                  } else if (conflictPopover.keptKey) {
                    const kept = group.members.find(
                      (m) => entitySpanKey(m) === conflictPopover.keptKey,
                    );
                    if (kept) handleResolveGroupKeep(group, kept);
                  }
                  setConflictPopover(null);
                }}
                className={clsx(
                  'inline-flex w-full items-center justify-center gap-1 rounded px-2 py-1.5 text-[11px] font-medium text-white',
                  dropMode
                    ? 'bg-red-600 hover:bg-red-700'
                    : 'bg-amber-600 hover:bg-amber-700',
                )}
              >
                <Check size={12} />
                {dropMode ? 'Drop spans' : 'Confirm resolution'}
              </button>
            </div>
          );
        })()}
    </section>
  );
}

function SavedIndicator({
  lastChangeAt,
  isDirty,
}: {
  lastChangeAt: number | null;
  isDirty: boolean;
}) {
  const [, tick] = useState(0);
  useEffect(() => {
    if (lastChangeAt == null) return;
    const id = window.setInterval(() => tick((n) => n + 1), 10000);
    return () => window.clearInterval(id);
  }, [lastChangeAt]);

  if (!isDirty && lastChangeAt == null) {
    return (
      <span
        className="inline-flex items-center gap-1 text-[10px] text-gray-400"
        title="No edits in this session"
      >
        <Check size={11} />
        Saved
      </span>
    );
  }

  if (lastChangeAt == null) return null;

  const ago = Math.max(0, Date.now() - lastChangeAt);
  const label =
    ago < 4000
      ? 'just now'
      : ago < 60_000
        ? `${Math.floor(ago / 1000)}s ago`
        : ago < 3_600_000
          ? `${Math.floor(ago / 60_000)}m ago`
          : `${Math.floor(ago / 3_600_000)}h ago`;
  return (
    <span
      className="inline-flex items-center gap-1 text-[10px] text-emerald-700"
      title="Edits are stored locally — no server save needed"
    >
      <Check size={11} />
      Saved · {label}
    </span>
  );
}
