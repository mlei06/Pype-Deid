import { useMemo, useState, useCallback, useEffect } from 'react';
import { clsx } from 'clsx';
import {
  Trash2,
  RotateCcw,
  ChevronDown,
  ChevronRight,
  Crosshair,
  Copy,
  AlertTriangle,
  ArrowRightLeft,
} from 'lucide-react';
import LabelBadge from './LabelBadge';
import LabelCombobox from './LabelCombobox';
import { entitySpanKey } from '../../lib/entitySpanKey';
import {
  pickPrimarySpan,
  RESOLVE_STRATEGY_LABEL,
  type OverlapGroup,
  type ResolveStrategyId,
} from '../../lib/spanOverlapConflicts';
import type { EntitySpanResponse } from '../../api/types';

interface SpanEditorProps {
  originalText: string;
  spans: EntitySpanResponse[];
  onChange: (spans: EntitySpanResponse[]) => void;
  onReset: () => void;
  isApplying: boolean;
  isDirty: boolean;
  error?: string | null;
  ghostSelection?: { start: number; end: number; text: string } | null;
  onClearGhostSelection?: () => void;
  onNavigateToGhost?: () => void;
  activeSpanKey?: string | null;
  onActiveSpanKeyChange?: (key: string | null) => void;
  overlapGroups?: OverlapGroup[];
  onResolveGroupKeep?: (group: OverlapGroup, kept: EntitySpanResponse) => void;
  onResolveGroupDrop?: (group: OverlapGroup) => void;
  onResolveAllOverlaps?: (strategy: ResolveStrategyId) => void;
  showGhostPanel?: boolean;
}

const RESOLVE_STRATEGIES: ResolveStrategyId[] = [
  'label_priority',
  'longest_wins',
  'leftmost_first',
];

export default function SpanEditor({
  originalText,
  spans,
  onChange,
  onReset,
  isApplying,
  isDirty,
  error,
  ghostSelection = null,
  onClearGhostSelection = () => {},
  onNavigateToGhost,
  activeSpanKey = null,
  onActiveSpanKeyChange = () => {},
  overlapGroups = [],
  onResolveGroupKeep,
  onResolveGroupDrop,
  onResolveAllOverlaps,
  showGhostPanel = true,
}: SpanEditorProps) {
  const DROP_ALL_CHOICE = '__drop_all__';
  const [collapsedLabels, setCollapsedLabels] = useState<Set<string>>(new Set());
  const [collapsedConflicts, setCollapsedConflicts] = useState(false);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [conflictChoice, setConflictChoice] = useState<Record<string, string>>({});
  const [bulkStrategy, setBulkStrategy] = useState<ResolveStrategyId>('label_priority');
  const [openMapGroup, setOpenMapGroup] = useState<string | null>(null);
  const [groupLabelDraft, setGroupLabelDraft] = useState('');

  const toggleLabel = (label: string) => {
    setCollapsedLabels((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  };

  const grouped = useMemo(() => {
    const map = new Map<string, EntitySpanResponse[]>();
    for (const s of spans) {
      const list = map.get(s.label) ?? [];
      list.push(s);
      map.set(s.label, list);
    }
    for (const list of map.values()) {
      list.sort((a, b) => a.start - b.start || a.end - b.end);
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [spans]);

  const uniqueLabels = useMemo(() => grouped.map(([label]) => label), [grouped]);

  const conflictedSpanKeys = useMemo(() => {
    const s = new Set<string>();
    for (const g of overlapGroups) {
      for (const m of g.members) s.add(entitySpanKey(m));
    }
    return s;
  }, [overlapGroups]);

  useEffect(() => {
    setConflictChoice((prev) => {
      const next: Record<string, string> = {};
      for (const g of overlapGroups) {
        const primary = pickPrimarySpan(g.members);
        const pk = entitySpanKey(primary);
        const prior = prev[g.id];
        const stillValid =
          prior === DROP_ALL_CHOICE ||
          (prior != null && g.members.some((m) => entitySpanKey(m) === prior));
        next[g.id] = stillValid ? prior! : pk;
      }
      return next;
    });
  }, [overlapGroups]);

  const toggleSelect = useCallback((key: string) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const selectAllInLabel = (items: EntitySpanResponse[]) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      const keys = items.map((s) => entitySpanKey(s));
      const allOn = keys.every((k) => next.has(k));
      if (allOn) keys.forEach((k) => next.delete(k));
      else keys.forEach((k) => next.add(k));
      return next;
    });
  };

  const handleDelete = (key: string) => {
    onChange(spans.filter((s) => entitySpanKey(s) !== key));
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      next.delete(key);
      return next;
    });
    if (activeSpanKey === key) onActiveSpanKeyChange(null);
  };

  const handleLabelChange = (key: string, newLabel: string) => {
    onChange(spans.map((s) => (entitySpanKey(s) === key ? { ...s, label: newLabel } : s)));
  };

  const deleteSelected = () => {
    if (selectedKeys.size === 0) return;
    onChange(spans.filter((s) => !selectedKeys.has(entitySpanKey(s))));
    setSelectedKeys(new Set());
    onActiveSpanKeyChange(null);
  };

  const deleteAllInLabel = (_label: string, items: EntitySpanResponse[]) => {
    const keys = new Set(items.map((s) => entitySpanKey(s)));
    onChange(spans.filter((s) => !keys.has(entitySpanKey(s))));
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      keys.forEach((k) => next.delete(k));
      return next;
    });
  };

  const remapGroup = (fromLabel: string, toLabelRaw: string) => {
    const toLabel = toLabelRaw.trim();
    if (!toLabel || fromLabel === toLabel) return;
    onChange(spans.map((s) => (s.label === fromLabel ? { ...s, label: toLabel } : s)));
    setOpenMapGroup(null);
    setGroupLabelDraft('');
  };

  const confirmGroupResolution = (group: OverlapGroup) => {
    const key = conflictChoice[group.id];
    if (!key) return;
    if (key === DROP_ALL_CHOICE) {
      if (!onResolveGroupDrop) return;
      onResolveGroupDrop(group);
      return;
    }
    if (!onResolveGroupKeep) return;
    const kept = group.members.find((m) => entitySpanKey(m) === key);
    if (!kept) return;
    onResolveGroupKeep(group, kept);
  };

  const copyTermsForBlacklist = async () => {
    const terms = spans
      .filter((s) => selectedKeys.has(entitySpanKey(s)))
      .map((s) => (s.text || originalText.slice(s.start, s.end)).trim())
      .filter(Boolean);
    const unique = [...new Set(terms)];
    if (unique.length === 0) return;
    try {
      await navigator.clipboard.writeText(unique.join('\n'));
    } catch {
      /* ignore */
    }
  };

  return (
    <div
      className="flex h-full min-h-0 flex-col gap-2 text-xs"
      onMouseLeave={() => onActiveSpanKeyChange(null)}
    >
      <div className="shrink-0 space-y-1.5">
        <div className="flex items-center gap-2">
          <span className="font-medium text-gray-800">Spans</span>
          <span className="text-gray-400">{spans.length} total</span>
          {isDirty && (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-800">
              edited
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={onReset}
          disabled={!isDirty || isApplying}
          className="w-full rounded border border-gray-200 bg-white px-2 py-1.5 font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-40"
          title="Revert to the spans detected by the pipeline"
        >
          <span className="inline-flex items-center justify-center gap-1">
            <RotateCcw size={12} />
            Reset span edits
          </span>
        </button>
      </div>

      {error && (
        <div className="shrink-0 rounded border border-red-200 bg-red-50 px-2 py-1.5 text-red-700">
          {error}
        </div>
      )}

      {showGhostPanel && ghostSelection && (
        <div
          data-pending-selection-ui
          className="shrink-0 space-y-1 rounded border border-amber-200 bg-amber-50/80 px-2 py-2 text-[11px] text-amber-950"
        >
          <button
            type="button"
            onClick={() => onNavigateToGhost?.()}
            className="w-full text-left hover:opacity-90"
          >
            <div className="mb-0.5 flex items-center gap-1 font-medium">
              <Crosshair size={12} />
              Pending selection
            </div>
            <div className="line-clamp-2 break-all font-mono text-[10px] text-amber-900/90">
              {ghostSelection.text.length > 100
                ? `${ghostSelection.text.slice(0, 100)}…`
                : ghostSelection.text}
            </div>
            <div className="mt-1 text-[10px] text-amber-700/80">
              Click to scroll & highlight in source
            </div>
          </button>
          <button
            type="button"
            onClick={() => onClearGhostSelection()}
            className="text-[10px] text-amber-800/80 underline hover:text-amber-950"
          >
            Dismiss
          </button>
        </div>
      )}

      {overlapGroups.length > 0 && (
        <div className="shrink-0 space-y-2 rounded border border-amber-200 bg-amber-50/50 px-2 py-2">
          <button
            type="button"
            onClick={() => setCollapsedConflicts((v) => !v)}
            className="flex w-full items-center gap-1 text-left text-[11px] font-semibold text-amber-950"
          >
            {collapsedConflicts ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
            <AlertTriangle size={14} className="shrink-0 text-amber-600" />
            <span>Resolve conflicts ({overlapGroups.length})</span>
          </button>
          {onResolveAllOverlaps && (
            <div className="flex items-stretch gap-1">
              <select
                value={bulkStrategy}
                onChange={(e) => setBulkStrategy(e.target.value as ResolveStrategyId)}
                className="min-w-0 flex-1 rounded border border-amber-300 bg-white px-1.5 py-1 text-[10px] text-amber-950"
                title="Strategy to apply when resolving all conflicts at once"
              >
                {RESOLVE_STRATEGIES.map((s) => (
                  <option key={s} value={s}>
                    {RESOLVE_STRATEGY_LABEL[s]}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => onResolveAllOverlaps(bulkStrategy)}
                className="shrink-0 rounded border border-amber-300 bg-white px-2 py-1 text-[10px] font-medium text-amber-950 hover:bg-amber-100/80"
              >
                Resolve all
              </button>
            </div>
          )}
          {!collapsedConflicts && (
            <div className="space-y-3 pl-1">
              {overlapGroups.map((g) => {
                const excerpt =
                  g.excerpt.length > 48 ? `${g.excerpt.slice(0, 48)}…` : g.excerpt;
                return (
                  <div
                    key={g.id}
                    className="rounded border border-amber-100 bg-white/90 px-2 py-2 shadow-sm"
                  >
                    <div className="mb-2 font-mono text-[10px] text-gray-800">
                      {excerpt}{' '}
                      <span className="text-gray-400">
                        [{g.minStart}–{g.maxEnd}]
                      </span>
                    </div>
                    <div className="space-y-1.5">
                      {g.members.map((s) => {
                        const id = entitySpanKey(s);
                        return (
                          <label
                            key={id}
                            className="flex cursor-pointer items-start gap-2 text-[10px] text-gray-700"
                          >
                            <input
                              type="radio"
                              name={`conflict-${g.id}`}
                              className="mt-0.5"
                              checked={conflictChoice[g.id] === id}
                              onChange={() =>
                                setConflictChoice((prev) => ({ ...prev, [g.id]: id }))
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
                      {onResolveGroupDrop && (
                        <label className="flex cursor-pointer items-start gap-2 text-[10px] text-gray-700">
                          <input
                            type="radio"
                            name={`conflict-${g.id}`}
                            className="mt-0.5"
                            checked={conflictChoice[g.id] === DROP_ALL_CHOICE}
                            onChange={() =>
                              setConflictChoice((prev) => ({
                                ...prev,
                                [g.id]: DROP_ALL_CHOICE,
                              }))
                            }
                          />
                          <span className="text-red-700">
                            <span className="font-semibold">Keep none</span>
                            <span className="text-gray-500">
                              {' '}
                              (drop every span in this group)
                            </span>
                          </span>
                        </label>
                      )}
                    </div>
                    {(() => {
                      const dropMode = conflictChoice[g.id] === DROP_ALL_CHOICE;
                      return (
                        <button
                          type="button"
                          onClick={() => confirmGroupResolution(g)}
                          disabled={dropMode ? !onResolveGroupDrop : !onResolveGroupKeep}
                          className={clsx(
                            'mt-2 w-full rounded px-2 py-1.5 text-[10px] font-medium text-white disabled:opacity-40',
                            dropMode
                              ? 'bg-red-600 hover:bg-red-700'
                              : 'bg-amber-600 hover:bg-amber-700',
                          )}
                        >
                          {dropMode ? 'Drop spans' : 'Confirm resolution'}
                        </button>
                      );
                    })()}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {selectedKeys.size > 0 && (
        <div className="flex shrink-0 flex-wrap gap-1">
          <button
            type="button"
            onClick={deleteSelected}
            className="rounded bg-red-600 px-2 py-1 text-[10px] font-medium text-white hover:bg-red-700"
          >
            Delete ({selectedKeys.size})
          </button>
          <button
            type="button"
            onClick={() => void copyTermsForBlacklist()}
            className="flex items-center gap-0.5 rounded border border-gray-300 bg-white px-2 py-1 text-[10px] font-medium text-gray-700 hover:bg-gray-50"
            title="Copy selected surface texts to clipboard (paste into a blacklist dictionary)"
          >
            <Copy size={10} />
            Copy for blacklist
          </button>
          <button
            type="button"
            onClick={() => setSelectedKeys(new Set())}
            className="text-[10px] text-gray-500 underline"
          >
            Clear selection
          </button>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto pr-0.5">
        {grouped.length > 0 ? (
          <div className="flex flex-col gap-2">
            {grouped.map(([label, items]) => {
              const collapsed = collapsedLabels.has(label);
              const labelHasConflict = items.some((s) =>
                conflictedSpanKeys.has(entitySpanKey(s)),
              );
              return (
                <div key={label} className="rounded border border-gray-200 bg-white shadow-sm">
                  <div className="sticky top-0 z-10 flex items-center gap-1 rounded-t bg-gray-100/90 px-1.5 py-1 backdrop-blur-sm">
                    <button
                      type="button"
                      onClick={() => toggleLabel(label)}
                      className="flex min-w-0 flex-1 items-center gap-1 text-left text-[11px] font-semibold text-gray-700"
                    >
                      {collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                      {labelHasConflict && (
                        <span
                          className="inline-flex shrink-0"
                          title="This group includes a range with conflicting labels — use Resolve conflicts above"
                        >
                          <AlertTriangle size={12} className="text-amber-600" />
                        </span>
                      )}
                      <LabelBadge label={label} />
                      <span className="text-gray-400">({items.length})</span>
                    </button>
                    <div className="relative flex shrink-0">
                      <button
                        type="button"
                        onClick={() => {
                          setOpenMapGroup((g) => (g === label ? null : label));
                          setGroupLabelDraft('');
                        }}
                        className="inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] font-medium text-gray-600 hover:bg-gray-200/80"
                        title="Map all spans in this group to a typed label"
                      >
                        <ArrowRightLeft size={12} className="shrink-0" />
                        <span className="hidden min-[360px]:inline">Map group</span>
                      </button>
                      {openMapGroup === label && (
                        <div className="absolute right-0 top-full z-20 mt-0.5 min-w-[14rem] rounded border border-gray-200 bg-white p-2 shadow-lg">
                          <div className="mb-1 text-[10px] font-semibold text-gray-500">
                            Map {label} to
                          </div>
                          <LabelCombobox
                            value={groupLabelDraft}
                            onCommit={(next) => remapGroup(label, next)}
                            onCancel={() => {
                              setOpenMapGroup(null);
                              setGroupLabelDraft('');
                            }}
                            extraSuggestions={uniqueLabels.filter((l) => l !== label)}
                            placeholder="Type target label"
                            autoFocus
                            ariaLabel={`Remap ${label} to`}
                          />
                        </div>
                      )}
                    </div>
                    {!collapsed && (
                      <button
                        type="button"
                        onClick={() => deleteAllInLabel(label, items)}
                        className="shrink-0 rounded px-1.5 py-0.5 text-[10px] text-red-600 hover:bg-red-50"
                        title={`Delete all ${label} spans`}
                      >
                        Delete all
                      </button>
                    )}
                  </div>
                  {!collapsed && (
                    <ul className="divide-y divide-gray-100">
                      <li className="group/row flex items-center gap-1 px-1.5 py-1 text-[10px] text-gray-500">
                        <input
                          type="checkbox"
                          className="rounded border-gray-300"
                          checked={
                            items.length > 0 &&
                            items.every((s) => selectedKeys.has(entitySpanKey(s)))
                          }
                          onChange={() => selectAllInLabel(items)}
                        />
                        <span>Select group</span>
                      </li>
                      {items.map((s) => {
                        const key = entitySpanKey(s);
                        const rowActive = activeSpanKey === key;
                        const sel = selectedKeys.has(key);
                        const rowConflict = conflictedSpanKeys.has(key);
                        return (
                          <li
                            key={key}
                            className={clsx(
                              'group/row flex flex-col gap-0.5 px-1.5 py-1 transition-colors',
                              rowActive && 'bg-blue-50',
                              sel && 'bg-slate-50',
                            )}
                            onMouseEnter={() => onActiveSpanKeyChange(key)}
                          >
                            <div className="flex items-start gap-1">
                              <input
                                type="checkbox"
                                className="mt-0.5 rounded border-gray-300"
                                checked={sel}
                                onChange={() => toggleSelect(key)}
                              />
                              <code className="min-w-0 flex-1 break-all text-[10px] leading-snug text-gray-800">
                                {rowConflict && (
                                  <span
                                    className="mr-0.5 inline-flex shrink-0"
                                    title="Conflicting labels at this range"
                                  >
                                    <AlertTriangle size={10} className="text-amber-600" />
                                  </span>
                                )}
                                {s.text || originalText.slice(s.start, s.end)}
                              </code>
                              <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover/row:opacity-100 group-focus-within/row:opacity-100">
                                <div className="w-[120px]">
                                  <LabelCombobox
                                    value={s.label}
                                    onCommit={(next) => {
                                      if (next !== s.label) handleLabelChange(key, next);
                                    }}
                                    extraSuggestions={uniqueLabels}
                                    size="sm"
                                    commitOnBlur
                                    ariaLabel="Span label"
                                  />
                                </div>
                                <button
                                  type="button"
                                  onClick={() => handleDelete(key)}
                                  className="rounded p-0.5 text-red-500 hover:bg-red-50"
                                  title="Remove span"
                                >
                                  <Trash2 size={11} />
                                </button>
                              </div>
                            </div>
                            <div className="pl-5 text-[9px] text-gray-400">
                              [{s.start}–{s.end}]
                              {s.source && (
                                <span className="ml-1 rounded bg-gray-100 px-1 text-gray-500">
                                  {s.source}
                                </span>
                              )}
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="rounded border border-dashed border-gray-200 px-3 py-6 text-center text-[11px] text-gray-400">
            No spans yet. Run the pipeline or add text from the source view.
          </div>
        )}
      </div>
    </div>
  );
}
