import { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import {
  Play,
  Loader2,
  Save,
  FolderOpen,
  FileJson,
  FileText,
  Trash2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  PanelTop,
  PanelRightClose,
  PanelRightOpen,
  Pencil,
  Plus,
  Shuffle,
  Database,
} from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import PipelineSelector from '../shared/PipelineSelector';
import TextInput from './TextInput';
import SpanHighlighter, { type SpanHighlighterHandle } from '../shared/SpanHighlighter';
import RedactedView from '../shared/RedactedView';
import SpanEditor from './SpanEditor';
import ConflictResolutionPopover from './ConflictResolutionPopover';
import InferenceDualPane from './InferenceDualPane';
import InferenceRightPanel, { type InferenceRightTab } from './InferenceRightPanel';
import InferencePipelineTab from './InferencePipelineTab';
import OutputModeToggle from '../shared/OutputModeToggle';
import EditableSource from './EditableSource';
import { useProcessText, useRedactDocument } from '../../hooks/useProcess';
import { useDatasets } from '../../hooks/useDatasets';
import { previewDataset, getDocument } from '../../api/datasets';
import {
  listInferenceRuns,
  saveInferenceSnapshot,
  getInferenceRun,
  deleteInferenceRun,
} from '../../api/inference';
import { downloadBlob } from '../../lib/download';
import { entitySpanKey } from '../../lib/entitySpanKey';
import { CANONICAL_LABELS } from '../../lib/canonicalLabels';
import { usePipeline } from '../../hooks/usePipelines';
import ColorKeyPopover from '../shared/ColorKeyPopover';
import {
  buildConflictMapFromTrace,
  conflictsForFinalSpans,
  type SpanLabelConflict,
} from '../../lib/traceConflicts';
import {
  applyResolveStrategy,
  dedupeSpansKeepPrimary,
  dropOverlapGroup,
  findOverlapGroups,
  keepInOverlapGroup,
  normalizeAnnotations,
  type OverlapGroup,
  type ResolveStrategyId,
} from '../../lib/spanOverlapConflicts';
import type {
  OutputMode,
  EntitySpanResponse,
  ProcessResponse,
  SavedInferenceRunDetail,
} from '../../api/types';

function toProcessResponse(d: SavedInferenceRunDetail): ProcessResponse {
  const { id: _id, saved_at: _saved, ...rest } = d;
  return rest;
}

function exportFilenameBase(pipelineName: string): string {
  const safe = pipelineName.replace(/[^a-zA-Z0-9._-]+/g, '_').slice(0, 64) || 'inference';
  const day = new Date().toISOString().slice(0, 10);
  return `${safe}_${day}`;
}

export default function InferenceView() {
  const [pipeline, setPipeline] = useState('');
  const [text, setText] = useState('');
  const [viewMode, setViewMode] = useState<OutputMode>('redacted');
  const [result, setResult] = useState<ProcessResponse | null>(null);
  const [snapshotMeta, setSnapshotMeta] = useState<{ id: string; saved_at: string } | null>(null);
  const [selectedRunId, setSelectedRunId] = useState('');
  const [editedSpans, setEditedSpans] = useState<EntitySpanResponse[] | null>(null);
  const [redactError, setRedactError] = useState<string | null>(null);
  const [activeSpanKey, setActiveSpanKey] = useState<string | null>(null);
  const [ghostSelection, setGhostSelection] = useState<{
    start: number;
    end: number;
    text: string;
  } | null>(null);
  const [pulseRange, setPulseRange] = useState<{ start: number; end: number } | null>(null);
  const [selectionMenu, setSelectionMenu] = useState<{
    start: number;
    end: number;
    text: string;
    left: number;
    top: number;
  } | null>(null);
  const [spanPopover, setSpanPopover] = useState<{
    key: string;
    span: EntitySpanResponse;
    left: number;
    top: number;
  } | null>(null);
  const [conflictUI, setConflictUI] = useState<{
    c: SpanLabelConflict;
    spanKey: string;
    left: number;
    top: number;
  } | null>(null);
  const [overlapConflictPopover, setOverlapConflictPopover] = useState<{
    group: OverlapGroup;
    anchor: DOMRect;
  } | null>(null);
  const [inputExpanded, setInputExpanded] = useState(true);
  const [rightTab, setRightTab] = useState<InferenceRightTab>('spans');
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const [outputCollapsed, setOutputCollapsed] = useState(false);
  const [asideCollapsed, setAsideCollapsed] = useState(false);
  const [sourceEditDraft, setSourceEditDraft] = useState<string | null>(null);
  const [sampleDataset, setSampleDataset] = useState('');
  const [isSampling, setIsSampling] = useState(false);

  const highlighterRef = useRef<SpanHighlighterHandle>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const selectionMenuRef = useRef<HTMLDivElement>(null);
  const conflictRef = useRef<HTMLDivElement>(null);
  const exportMenuRef = useRef<HTMLDivElement>(null);

  const clearPendingSelection = useCallback(() => {
    setGhostSelection(null);
    setSelectionMenu(null);
    setOverlapConflictPopover(null);
    window.getSelection()?.removeAllRanges();
  }, []);

  const queryClient = useQueryClient();
  const mutation = useProcessText();
  const redactMutation = useRedactDocument();

  useEffect(() => {
    setEditedSpans(null);
    setRedactError(null);
    setGhostSelection(null);
    setSelectionMenu(null);
    setActiveSpanKey(null);
    setPulseRange(null);
    setSpanPopover(null);
    setConflictUI(null);
    setSourceEditDraft(null);
    if (result) {
      setInputExpanded(false);
    } else {
      setInputExpanded(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result?.request_id, result?.pipeline_name]);

  useEffect(() => {
    if (!pulseRange) return;
    const t = window.setTimeout(() => setPulseRange(null), 1600);
    return () => window.clearTimeout(t);
  }, [pulseRange]);

  useEffect(() => {
    if (!spanPopover) return;
    const onDown = (e: MouseEvent) => {
      if (popoverRef.current?.contains(e.target as Node)) return;
      setSpanPopover(null);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [spanPopover]);

  useEffect(() => {
    if (!exportMenuOpen) return;
    const onDown = (e: MouseEvent) => {
      if (exportMenuRef.current?.contains(e.target as Node)) return;
      setExportMenuOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [exportMenuOpen]);

  useEffect(() => {
    if (!ghostSelection && !selectionMenu) return;
    const onDocClick = (e: MouseEvent) => {
      const t = e.target;
      if (!(t instanceof Node)) return;
      const host =
        t instanceof Element ? t : (t.parentNode instanceof Element ? t.parentNode : null);
      if (host?.closest('[data-inference-annotate-pane]')) return;
      if (selectionMenuRef.current?.contains(t)) return;
      if (host?.closest('[data-pending-selection-ui]')) return;
      clearPendingSelection();
    };
    document.addEventListener('click', onDocClick);
    return () => document.removeEventListener('click', onDocClick);
  }, [ghostSelection, selectionMenu, clearPendingSelection]);

  useEffect(() => {
    if (!ghostSelection && !selectionMenu) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      e.preventDefault();
      clearPendingSelection();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [ghostSelection, selectionMenu, clearPendingSelection]);

  useEffect(() => {
    if (!conflictUI) return;
    const onDown = (e: MouseEvent) => {
      if (conflictRef.current?.contains(e.target as Node)) return;
      setConflictUI(null);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [conflictUI]);

  const { data: savedRuns = [], isLoading: runsLoading } = useQuery({
    queryKey: ['inference-runs'],
    queryFn: listInferenceRuns,
  });

  const saveMutation = useMutation({
    mutationFn: saveInferenceSnapshot,
    onSuccess: (detail) => {
      queryClient.invalidateQueries({ queryKey: ['inference-runs'] });
      setResult(toProcessResponse(detail));
      setSnapshotMeta({ id: detail.id, saved_at: detail.saved_at });
      setPipeline(detail.pipeline_name);
      setText(detail.original_text);
    },
  });

  const loadMutation = useMutation({
    mutationFn: getInferenceRun,
    onSuccess: (detail) => {
      setResult(toProcessResponse(detail));
      setSnapshotMeta({ id: detail.id, saved_at: detail.saved_at });
      setPipeline(detail.pipeline_name);
      setText(detail.original_text);
      setSelectedRunId(detail.id);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteInferenceRun,
    onSuccess: (_, runId) => {
      queryClient.invalidateQueries({ queryKey: ['inference-runs'] });
      if (snapshotMeta?.id === runId) {
        setSnapshotMeta(null);
        setResult(null);
      }
      if (selectedRunId === runId) {
        setSelectedRunId('');
      }
    },
  });

  const handleRun = () => {
    if (!pipeline || !text.trim()) return;
    setSnapshotMeta(null);
    setSelectedRunId('');
    mutation.mutate(
      { pipelineName: pipeline, req: { text }, trace: true, outputMode: viewMode },
      { onSuccess: setResult },
    );
  };

  /** Start a fresh scratchpad: clear text, result, and any loaded snapshot. */
  const handleNewFreeText = () => {
    setText('');
    setResult(null);
    setSnapshotMeta(null);
    setSelectedRunId('');
    setEditedSpans(null);
    setSourceEditDraft(null);
    setInputExpanded(true);
  };

  const handleStartEditSource = () => {
    if (!result) return;
    setSourceEditDraft(result.original_text);
  };

  const handleCancelEditSource = () => {
    setSourceEditDraft(null);
  };

  /** Commit edited text: update input, discard stale detections, reopen input panel. */
  const handleCommitEditSource = () => {
    if (sourceEditDraft === null) return;
    setText(sourceEditDraft);
    setResult(null);
    setSnapshotMeta(null);
    setSelectedRunId('');
    setEditedSpans(null);
    setSourceEditDraft(null);
    setInputExpanded(true);
  };

  const { data: datasets = [] } = useDatasets();

  const handleSampleFromDataset = async () => {
    const ds = datasets.find((d) => d.name === sampleDataset);
    if (!ds || ds.document_count === 0) return;
    setIsSampling(true);
    try {
      const offset = Math.floor(Math.random() * ds.document_count);
      const preview = await previewDataset(sampleDataset, { limit: 1, offset });
      if (preview.items.length === 0) return;
      const doc = await getDocument(sampleDataset, preview.items[0].document_id);
      setText(doc.text);
    } finally {
      setIsSampling(false);
    }
  };

  const canSave = result && !saveMutation.isPending;
  const exportPayload = useMemo(() => {
    if (!result) return null;
    if (snapshotMeta) {
      return { ...result, id: snapshotMeta.id, saved_at: snapshotMeta.saved_at };
    }
    return result;
  }, [result, snapshotMeta]);

  const handleDownloadJson = () => {
    if (!exportPayload || !result) return;
    const base = exportFilenameBase(result.pipeline_name);
    downloadBlob(
      `${base}_snapshot.json`,
      JSON.stringify(exportPayload, null, 2),
      'application/json',
    );
  };

  const handleDownloadRedacted = () => {
    if (!result) return;
    const base = exportFilenameBase(result.pipeline_name);
    downloadBlob(`${base}_redacted.txt`, result.redacted_text, 'text/plain; charset=utf-8');
  };

  /**
   * Single chokepoint that collapses exact (start, end, label) duplicates.
   * Detectors can independently agree on the same span, and resolution paths
   * can leave residue; without normalization here, ``entitySpanKey`` collisions
   * surface as broken React keys / shared selection state in SpanEditor.
   */
  const effectiveSpans = useMemo<EntitySpanResponse[]>(
    () => normalizeAnnotations(editedSpans ?? result?.spans ?? []),
    [editedSpans, result?.spans],
  );

  const { data: pipelineDetail } = usePipeline(pipeline || null);
  const mapTargetLabels = useMemo(() => {
    const set = new Set<string>(CANONICAL_LABELS);
    for (const s of effectiveSpans) set.add(s.label);
    for (const l of pipelineDetail?.config?.output_label_space ?? []) {
      if (l) set.add(l);
    }
    return [...set].sort((a, b) => a.localeCompare(b));
  }, [effectiveSpans, pipelineDetail?.config?.output_label_space]);

  const overlapGroups = useMemo(() => {
    if (!result) return [] as OverlapGroup[];
    return findOverlapGroups(effectiveSpans, result.original_text);
  }, [effectiveSpans, result]);

  /** Rotates through overlap groups via ``[`` / ``]``; scrolls + pulses each one. Skips when an editor/menu has focus. */
  const overlapNavIdxRef = useRef(-1);
  // Reset whenever the group set changes (new result OR span edits regenerate
  // groups). Keeps `]` semantically "go to the first/next group from here."
  useEffect(() => {
    overlapNavIdxRef.current = -1;
  }, [overlapGroups]);
  useEffect(() => {
    if (overlapGroups.length === 0) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== '[' && e.key !== ']') return;
      const t = e.target;
      if (
        t instanceof HTMLInputElement ||
        t instanceof HTMLTextAreaElement ||
        t instanceof HTMLSelectElement ||
        (t instanceof HTMLElement && t.isContentEditable)
      ) {
        return;
      }
      e.preventDefault();
      const n = overlapGroups.length;
      const cur = overlapNavIdxRef.current;
      const nextIdx = e.key === ']' ? (cur + 1 + n) % n : (cur - 1 + n) % n;
      overlapNavIdxRef.current = nextIdx;
      const g = overlapGroups[nextIdx]!;
      highlighterRef.current?.scrollToRange(g.minStart, g.maxEnd);
      setPulseRange({ start: g.minStart, end: g.maxEnd });
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [overlapGroups]);

  const displaySpansForHighlighter = useMemo(
    () => dedupeSpansKeepPrimary(effectiveSpans),
    [effectiveSpans],
  );

  const isDirty =
    editedSpans !== null &&
    result !== null &&
    (editedSpans.length !== result.spans.length ||
      editedSpans.some((s, i) => {
        const orig = result.spans[i];
        return !orig || s.start !== orig.start || s.end !== orig.end || s.label !== orig.label;
      }));

  const conflictBySpanKey = useMemo(() => {
    if (!result?.intermediary_trace) return new Map<string, SpanLabelConflict>();
    const rangeMap = buildConflictMapFromTrace(result.intermediary_trace);
    return conflictsForFinalSpans(rangeMap, effectiveSpans);
  }, [result?.intermediary_trace, effectiveSpans]);

  const handleEditedSpansChange = (spans: EntitySpanResponse[]) => {
    setEditedSpans(spans);
    setRedactError(null);
  };

  const handleResetEdits = () => {
    setEditedSpans(null);
    setRedactError(null);
  };

  const handleUpdateOutput = () => {
    if (!result) return;
    /** Snapshot before apply so open conflicts remain editable after success. */
    const snapshot = [...effectiveSpans];
    const hadOpenConflicts =
      findOverlapGroups(snapshot, result.original_text).length > 0;
    /** One span per range for the API; unresolved overlaps use canonical primary for this run. */
    const spansPayload = dedupeSpansKeepPrimary(effectiveSpans);
    setRedactError(null);

    redactMutation.mutate(
      {
        text: result.original_text,
        spans: spansPayload.map((s) => ({ start: s.start, end: s.end, label: s.label })),
        output_mode: viewMode,
      },
      {
        onSuccess: (res) => {
          setResult({
            ...result,
            redacted_text: res.output_text,
            spans: spansPayload,
          });
          if (hadOpenConflicts) {
            setEditedSpans(snapshot);
          } else {
            setEditedSpans(null);
          }
          setSnapshotMeta(null);
          clearPendingSelection();
        },
        onError: (err: unknown) =>
          setRedactError(err instanceof Error ? err.message : 'Redaction failed'),
      },
    );
  };

  /** Toggle the output view mode; re-render the Output pane using current spans. */
  const handleViewModeChange = (mode: OutputMode) => {
    setViewMode(mode);
    if (!result) return;

    const spansPayload = dedupeSpansKeepPrimary(effectiveSpans);
    if (spansPayload.length === 0) {
      setResult((prev) =>
        prev ? { ...prev, redacted_text: prev.original_text } : prev,
      );
      return;
    }

    setRedactError(null);
    redactMutation.mutate(
      {
        text: result.original_text,
        spans: spansPayload.map((s) => ({ start: s.start, end: s.end, label: s.label })),
        output_mode: mode,
      },
      {
        onSuccess: (res) => {
          setResult((prev) =>
            prev ? { ...prev, redacted_text: res.output_text } : prev,
          );
        },
        onError: (err: unknown) =>
          setRedactError(err instanceof Error ? err.message : 'Redaction failed'),
      },
    );
  };

  const replaceSpans = (next: EntitySpanResponse[]) => {
    setEditedSpans(next);
    setRedactError(null);
  };

  /** Functional update avoids stale ``effectiveSpans`` when resolving from the popover after other edits. */
  const handleResolveGroupKeep = useCallback(
    (group: OverlapGroup, kept: EntitySpanResponse) => {
      setEditedSpans((prev) => {
        const base = prev ?? result?.spans ?? [];
        return keepInOverlapGroup(base, group, kept);
      });
      setRedactError(null);
      setOverlapConflictPopover(null);
      setConflictUI(null);
    },
    [result?.spans],
  );

  /** Drop every member of an overlap group — user decided none of the labels apply here. */
  const handleResolveGroupDrop = useCallback(
    (group: OverlapGroup) => {
      setEditedSpans((prev) => {
        const base = prev ?? result?.spans ?? [];
        return dropOverlapGroup(base, group);
      });
      setRedactError(null);
      setOverlapConflictPopover(null);
      setConflictUI(null);
    },
    [result?.spans],
  );

  /** Bulk-resolve every overlap group with the chosen strategy (see ``span_merge`` in the backend). */
  const handleResolveAllOverlaps = useCallback(
    (strategy: ResolveStrategyId) => {
      setEditedSpans((prev) => {
        const base = prev ?? result?.spans ?? [];
        return applyResolveStrategy(base, strategy);
      });
      setRedactError(null);
      setOverlapConflictPopover(null);
      setConflictUI(null);
    },
    [result?.spans],
  );

  /**
   * Highlighter clicks emit the spans covering the overlap segment under the
   * cursor. Find the overlap group whose members cover those spans and open
   * the popover anchored to the click target.
   */
  const handleOverlapClick = (overlapSpans: EntitySpanResponse[], anchor: DOMRect) => {
    if (overlapSpans.length < 2) return;
    const keys = new Set(overlapSpans.map((s) => entitySpanKey(s)));
    const group = overlapGroups.find((g) =>
      overlapSpans.every((s) => g.members.some((m) => entitySpanKey(m) === entitySpanKey(s))) &&
      g.members.some((m) => keys.has(entitySpanKey(m))),
    );
    if (!group) return;
    setSpanPopover(null);
    setOverlapConflictPopover({ group, anchor });
  };

  const updateSpanByKey = (key: string, patch: Partial<EntitySpanResponse>) => {
    replaceSpans(effectiveSpans.map((s) => (entitySpanKey(s) === key ? { ...s, ...patch } : s)));
  };

  const deleteSpanByKey = (key: string) => {
    replaceSpans(effectiveSpans.filter((s) => entitySpanKey(s) !== key));
    setSpanPopover(null);
    if (activeSpanKey === key) setActiveSpanKey(null);
  };

  const addManualSpan = (label: string, sel: { start: number; end: number; text: string }) => {
    const next: EntitySpanResponse = {
      start: sel.start,
      end: sel.end,
      label,
      text: sel.text,
      confidence: null,
      source: 'manual',
    };
    const k = entitySpanKey(next);
    if (effectiveSpans.some((s) => entitySpanKey(s) === k)) {
      clearPendingSelection();
      return;
    }
    const merged = [...effectiveSpans, next].sort((a, b) => a.start - b.start || a.end - b.end);
    replaceSpans(merged);
    clearPendingSelection();
  };

  const onUncoveredSelection = (
    sel: { start: number; end: number; text: string },
    anchor: DOMRect,
  ) => {
    setGhostSelection(sel);
    setSelectionMenu({
      ...sel,
      left: Math.max(8, Math.min(anchor.left, window.innerWidth - 220)),
      top: anchor.bottom + 6,
    });
  };

  const runDisabled = !pipeline || !text.trim() || mutation.isPending;

  const traceFrames = result?.intermediary_trace;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Top bar */}
      <header className="flex shrink-0 flex-wrap items-end gap-2 border-b border-gray-200 bg-white px-3 py-2 shadow-sm">
        <div className="flex min-w-[180px] max-w-[340px] flex-1 items-end gap-1.5 rounded-md border border-gray-200 bg-gray-50 px-1.5 py-1">
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <span className="text-[10px] font-medium text-gray-500">Pipeline</span>
            <PipelineSelector value={pipeline} onChange={setPipeline} />
          </div>
          <button
            type="button"
            onClick={handleRun}
            disabled={runDisabled}
            className="flex shrink-0 items-center gap-1.5 rounded-md bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-40"
          >
            {mutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
            Run
          </button>
        </div>
        <button
          type="button"
          onClick={() => setInputExpanded((e) => !e)}
          className="flex items-center gap-1 rounded-md border border-gray-200 bg-gray-50 px-2 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-100"
          title="Show or hide input text"
        >
          <PanelTop size={14} />
          Input
          {inputExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        <button
          type="button"
          onClick={handleNewFreeText}
          className="flex items-center gap-1 rounded-md border border-gray-200 bg-gray-50 px-2 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-100"
          title="Clear text and result to start a fresh free-text entry"
        >
          <Plus size={14} />
          New
        </button>

        {result && (
          <>
            <div className="mx-1 h-8 w-px self-stretch bg-gray-200" />
            <div className="flex flex-wrap items-center gap-0 rounded-lg border border-gray-200 bg-slate-50/90 p-0.5 shadow-sm">
              <button
                type="button"
                disabled={!canSave}
                onClick={() => result && saveMutation.mutate(result)}
                className="flex items-center gap-1 rounded-md border border-transparent bg-white px-2 py-1.5 text-sm font-medium text-gray-700 hover:bg-white/80 disabled:opacity-40"
              >
                {saveMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                Save snapshot
              </button>
              <div className="mx-0.5 h-6 w-px self-center bg-gray-200" />
              <div className="relative" ref={exportMenuRef}>
                <button
                  type="button"
                  onClick={() => setExportMenuOpen((o) => !o)}
                  className="flex items-center gap-1 rounded-md border border-transparent bg-white px-2 py-1.5 text-sm font-medium text-gray-700 hover:bg-white/80"
                  aria-expanded={exportMenuOpen}
                  aria-haspopup="menu"
                >
                  Export
                  <ChevronDown size={14} className="text-gray-500" />
                </button>
                {exportMenuOpen && (
                  <div
                    role="menu"
                    className="absolute right-0 top-full z-50 mt-1 min-w-[200px] rounded-md border border-gray-200 bg-white py-1 shadow-lg"
                  >
                    <button
                      type="button"
                      role="menuitem"
                      className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-gray-800 hover:bg-gray-50"
                      onClick={() => {
                        handleDownloadJson();
                        setExportMenuOpen(false);
                      }}
                    >
                      <FileJson size={14} className="shrink-0 text-gray-500" />
                      Export as JSON
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-gray-800 hover:bg-gray-50"
                      onClick={() => {
                        handleDownloadRedacted();
                        setExportMenuOpen(false);
                      }}
                    >
                      <FileText size={14} className="shrink-0 text-gray-500" />
                      Download output text
                    </button>
                  </div>
                )}
              </div>
            </div>
          </>
        )}

        <div className="flex min-h-8 min-w-0 flex-1 flex-wrap items-center justify-end gap-1.5">
          {runsLoading && <Loader2 size={12} className="animate-spin text-gray-400" />}
          <FolderOpen size={12} className="text-gray-400" />
          <select
            className="max-w-[200px] rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-800"
            value={selectedRunId}
            disabled={runsLoading || loadMutation.isPending || savedRuns.length === 0}
            onChange={(e) => setSelectedRunId(e.target.value)}
          >
            <option value="">{savedRuns.length === 0 ? 'No snapshots' : 'Load snapshot…'}</option>
            {savedRuns.map((r) => (
              <option key={r.id} value={r.id}>
                {r.pipeline_name} · {r.saved_at.slice(0, 16)}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={!selectedRunId || loadMutation.isPending}
            onClick={() => selectedRunId && loadMutation.mutate(selectedRunId)}
            className="rounded border border-gray-200 bg-white px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-40"
          >
            {loadMutation.isPending ? <Loader2 size={12} className="animate-spin" /> : 'Load'}
          </button>
          {selectedRunId && (
            <button
              type="button"
              title="Delete snapshot"
              disabled={deleteMutation.isPending}
              onClick={() => {
                if (selectedRunId && confirm('Delete this saved snapshot?')) {
                  deleteMutation.mutate(selectedRunId);
                }
              }}
              className="rounded border border-red-100 p-1 text-red-600 hover:bg-red-50"
            >
              <Trash2 size={12} />
            </button>
          )}
        </div>
      </header>

      {inputExpanded && (
        <div className="shrink-0 border-b border-gray-100 bg-gray-50/50 px-3 py-2">
          <div className="mx-auto max-w-5xl">
            <div className="mb-1 text-xs font-medium text-gray-600">Input text</div>
            <TextInput value={text} onChange={setText} />
            {datasets.length > 0 && (
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <Database size={12} className="shrink-0 text-gray-400" />
                <span className="text-xs text-gray-400">Sample from dataset:</span>
                <select
                  className="rounded border border-gray-200 bg-white px-1.5 py-0.5 text-xs text-gray-700"
                  value={sampleDataset}
                  onChange={(e) => setSampleDataset(e.target.value)}
                >
                  <option value="">Choose dataset…</option>
                  {datasets.map((d) => (
                    <option key={d.name} value={d.name}>
                      {d.name} ({d.document_count} docs)
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={handleSampleFromDataset}
                  disabled={!sampleDataset || isSampling}
                  className="flex items-center gap-1 rounded border border-gray-200 bg-white px-2 py-0.5 text-xs text-gray-700 hover:bg-gray-50 disabled:opacity-40"
                >
                  {isSampling ? (
                    <Loader2 size={11} className="animate-spin" />
                  ) : (
                    <Shuffle size={11} />
                  )}
                  Sample
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {mutation.isError && (
        <div className="shrink-0 border-b border-red-100 bg-red-50 px-4 py-2 text-sm text-red-700">
          {(mutation.error as Error).message}
        </div>
      )}
      {loadMutation.isError && (
        <div className="shrink-0 border-b border-red-100 bg-red-50 px-4 py-2 text-xs text-red-700">
          {(loadMutation.error as Error).message}
        </div>
      )}
      {saveMutation.isError && (
        <div className="shrink-0 border-b border-red-100 bg-red-50 px-4 py-2 text-xs text-red-700">
          {(saveMutation.error as Error).message}
        </div>
      )}

      <div className="flex min-h-0 flex-1 flex-row overflow-hidden">
        <section className="flex min-h-0 min-w-0 flex-1 flex-col">
          {result ? (
            <>
              <InferenceDualPane
                outputCollapsed={outputCollapsed}
                leftHeader={
                  <div className="flex w-full items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-semibold uppercase tracking-wide text-gray-500">
                        {sourceEditDraft !== null ? 'Editing source' : 'Annotated source'}
                      </span>
                      {sourceEditDraft === null && <ColorKeyPopover />}
                    </div>
                    <div className="flex items-center gap-1">
                      {sourceEditDraft === null && (
                        <button
                          type="button"
                          onClick={handleStartEditSource}
                          className="inline-flex items-center gap-1 rounded border border-gray-200 bg-white px-1.5 py-0.5 text-[10px] font-medium text-gray-600 hover:bg-gray-50"
                          title="Edit the source text — clears current detections"
                        >
                          <Pencil size={11} />
                          Edit
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => setOutputCollapsed((v) => !v)}
                        className="inline-flex items-center gap-1 rounded border border-gray-200 bg-white px-1.5 py-0.5 text-[10px] font-medium text-gray-600 hover:bg-gray-50"
                        title={outputCollapsed ? 'Show output pane' : 'Hide output pane'}
                      >
                        {outputCollapsed ? (
                          <>
                            <PanelRightOpen size={11} />
                            Show output
                          </>
                        ) : (
                          <>
                            <PanelRightClose size={11} />
                            Hide output
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                }
                rightHeader={
                  <div className="flex w-full items-center justify-between gap-2">
                    <span className="text-[10px] font-semibold uppercase tracking-wide text-gray-500">
                      Output
                    </span>
                    <OutputModeToggle
                      value={viewMode}
                      onChange={handleViewModeChange}
                      disabled={redactMutation.isPending}
                    />
                  </div>
                }
                left={
                  sourceEditDraft !== null ? (
                    <EditableSource
                      value={sourceEditDraft}
                      onChange={setSourceEditDraft}
                      onCommit={handleCommitEditSource}
                      onCancel={handleCancelEditSource}
                    />
                  ) : (
                  <SpanHighlighter
                    ref={highlighterRef}
                    text={result.original_text}
                    spans={displaySpansForHighlighter}
                    activeSpanKey={activeSpanKey}
                    onSpanHover={setActiveSpanKey}
                    onSpanClick={(_span, key, anchor) => {
                      setSpanPopover({
                        key,
                        span: _span,
                        left: Math.max(8, Math.min(anchor.left, window.innerWidth - 220)),
                        top: anchor.bottom + 6,
                      });
                    }}
                    onUncoveredSelection={onUncoveredSelection}
                    onClearPendingSelection={clearPendingSelection}
                    pendingGhostRange={ghostSelection}
                    pulseRange={pulseRange}
                    conflictBySpanKey={conflictBySpanKey}
                    onConflictClick={(c, anchor) => {
                      const span = effectiveSpans.find((s) => s.start === c.start && s.end === c.end);
                      if (!span) return;
                      setConflictUI({
                        c,
                        spanKey: entitySpanKey(span),
                        left: Math.max(8, Math.min(anchor.left, window.innerWidth - 280)),
                        top: anchor.bottom + 6,
                      });
                    }}
                    onOverlapClick={handleOverlapClick}
                    onSpanResize={(key, start, end) => {
                      updateSpanByKey(key, {
                        start,
                        end,
                        text: result.original_text.slice(start, end),
                      });
                    }}
                  />
                  )
                }
                right={<RedactedView text={result.redacted_text} />}
              />
            </>
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center text-sm text-gray-500">
              <p className="font-medium text-gray-700">No run yet</p>
              <p className="max-w-md text-xs text-gray-400">
                Set pipeline and input above, then Run. The annotated / output panes and tools appear
                here.
              </p>
            </div>
          )}
        </section>

        {result && asideCollapsed && (
          <aside className="flex w-9 shrink-0 flex-col items-center border-l border-gray-200 bg-white py-1">
            <button
              type="button"
              onClick={() => setAsideCollapsed(false)}
              className="rounded p-1.5 text-gray-500 hover:bg-gray-100 hover:text-gray-800"
              title="Expand side panel"
              aria-label="Expand side panel"
            >
              <ChevronLeft size={14} />
            </button>
          </aside>
        )}
        {result && !asideCollapsed && (
          <aside className="flex w-[min(38%,520px)] min-w-[280px] max-w-[560px] shrink-0 flex-col border-l border-gray-200 bg-white">
            <InferenceRightPanel
              tab={rightTab}
              onTabChange={setRightTab}
              onCollapse={() => setAsideCollapsed(true)}
              spansContent={
                <SpanEditor
                  originalText={result.original_text}
                  spans={effectiveSpans}
                  onChange={handleEditedSpansChange}
                  onReset={handleResetEdits}
                  isApplying={redactMutation.isPending}
                  isDirty={isDirty}
                  error={redactError}
                  mapTargetLabels={mapTargetLabels}
                  ghostSelection={ghostSelection}
                  onClearGhostSelection={clearPendingSelection}
                  onNavigateToGhost={() => {
                    if (!ghostSelection) return;
                    highlighterRef.current?.scrollToRange(ghostSelection.start, ghostSelection.end);
                    setPulseRange({
                      start: ghostSelection.start,
                      end: ghostSelection.end,
                    });
                  }}
                  activeSpanKey={activeSpanKey}
                  onActiveSpanKeyChange={setActiveSpanKey}
                  overlapGroups={overlapGroups}
                  onResolveGroupKeep={handleResolveGroupKeep}
                  onResolveGroupDrop={handleResolveGroupDrop}
                  onResolveAllOverlaps={handleResolveAllOverlaps}
                  onUpdateOutput={handleUpdateOutput}
                />
              }
              pipelineContent={
                <InferencePipelineTab
                  pipelineName={pipeline}
                  spans={effectiveSpans}
                  frames={traceFrames}
                />
              }
            />
          </aside>
        )}
      </div>

      {/* Floating label menu for unflagged selection */}
      {selectionMenu && result && (
        <div
          ref={selectionMenuRef}
          className="fixed z-50 w-56 rounded-lg border border-gray-200 bg-white p-2 shadow-xl"
          style={{ left: selectionMenu.left, top: selectionMenu.top }}
        >
          <div className="mb-1 text-[10px] font-semibold uppercase text-gray-500">Add PHI label</div>
          <select
            className="mb-2 w-full rounded border border-gray-200 px-2 py-1.5 text-xs text-gray-800"
            defaultValue=""
            onChange={(e) => {
              const v = e.target.value;
              if (!v) return;
              addManualSpan(v, {
                start: selectionMenu.start,
                end: selectionMenu.end,
                text: selectionMenu.text,
              });
              e.target.value = '';
            }}
          >
            <option value="">Choose label…</option>
            {mapTargetLabels.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => clearPendingSelection()}
            className="w-full rounded border border-gray-200 py-1 text-[11px] text-gray-600 hover:bg-gray-50"
          >
            Cancel
          </button>
        </div>
      )}

      <ConflictResolutionPopover
        open={Boolean(overlapConflictPopover && result)}
        onClose={() => setOverlapConflictPopover(null)}
        anchorRect={overlapConflictPopover?.anchor ?? null}
        originalText={result?.original_text ?? ''}
        group={overlapConflictPopover?.group ?? null}
        onKeep={handleResolveGroupKeep}
        onDropAll={handleResolveGroupDrop}
      />

      {spanPopover && result && (
        <div
          ref={popoverRef}
          className="fixed z-50 w-52 rounded-lg border border-gray-200 bg-white p-2 shadow-lg"
          style={{ left: spanPopover.left, top: spanPopover.top }}
        >
          <div className="mb-1.5 text-[10px] font-semibold uppercase text-gray-500">Span</div>
          {(() => {
            const raw = spanPopover.span.label;
            const upper = raw.toUpperCase();
            const isCanonical = (CANONICAL_LABELS as readonly string[]).includes(upper);
            return (
              <select
                value={isCanonical ? upper : '__custom__'}
                onChange={(e) => {
                  if (e.target.value === '__custom__') return;
                  updateSpanByKey(spanPopover.key, { label: e.target.value });
                  setSpanPopover((p) =>
                    p ? { ...p, span: { ...p.span, label: e.target.value } } : null,
                  );
                }}
                className="mb-2 w-full rounded border border-gray-200 px-2 py-1 text-xs text-gray-800"
              >
                {!isCanonical && (
                  <option value="__custom__">{raw} (custom)</option>
                )}
                {CANONICAL_LABELS.map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </select>
            );
          })()}
          <button
            type="button"
            onClick={() => deleteSpanByKey(spanPopover.key)}
            className="w-full rounded border border-red-100 bg-red-50 px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-100"
          >
            Delete span
          </button>
        </div>
      )}

      {conflictUI && result && (
        <div
          ref={conflictRef}
          className="fixed z-50 max-w-xs rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs shadow-xl"
          style={{ left: conflictUI.left, top: conflictUI.top }}
        >
          <div className="mb-1 font-semibold text-amber-950">Label conflict</div>
          <p className="mb-2 text-amber-900/90">
            <span className="font-mono text-[10px]">{conflictUI.c.pipeA}</span>:{' '}
            <strong>{conflictUI.c.labelA}</strong>
            <br />
            <span className="font-mono text-[10px]">{conflictUI.c.pipeB}</span>:{' '}
            <strong>{conflictUI.c.labelB}</strong>
          </p>
          <div className="flex flex-col gap-1">
            <button
              type="button"
              className="rounded bg-white px-2 py-1 text-left text-[11px] hover:bg-amber-100"
              onClick={() => {
                updateSpanByKey(conflictUI.spanKey, { label: conflictUI.c.labelA });
                setConflictUI(null);
              }}
            >
              Keep: {conflictUI.c.labelA}
            </button>
            <button
              type="button"
              className="rounded bg-white px-2 py-1 text-left text-[11px] hover:bg-amber-100"
              onClick={() => {
                updateSpanByKey(conflictUI.spanKey, { label: conflictUI.c.labelB });
                setConflictUI(null);
              }}
            >
              Keep: {conflictUI.c.labelB}
            </button>
          </div>
        </div>
      )}

      {result && snapshotMeta && (
        <div className="flex shrink-0 justify-end border-t border-gray-100 bg-gray-50/80 px-3 py-1.5 text-[10px] text-gray-400">
          <span className="truncate">
            Snapshot <code>{snapshotMeta.id}</code>
          </span>
        </div>
      )}
    </div>
  );
}
