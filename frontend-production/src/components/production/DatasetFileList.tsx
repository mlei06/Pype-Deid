import { useMemo, useRef, useState } from 'react';
import {
  Upload,
  FileText,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Circle,
  Trash2,
  ClipboardPaste,
  Flag,
} from 'lucide-react';
import { clsx } from 'clsx';
import { useVirtualizer } from '@tanstack/react-virtual';
import {
  useProductionStore,
  makeId,
  type Dataset,
  type DatasetFile,
  type DetectionStatus,
} from './store';
import PasteModal from './PasteModal';
import { useConfirm } from '../shared/ConfirmDialog';

/** Row height (px) used for virtualization. Matches the rendered `<li>` height. */
const ROW_HEIGHT_PX = 36;
/** Switch to virtualization once the visible list exceeds this. */
const VIRTUALIZE_THRESHOLD = 200;

interface DatasetFileListProps {
  dataset: Dataset;
  selectedIds: Set<string>;
  onToggleSelected: (id: string) => void;
  /** Toggle selection for the currently visible rows only (respects filter chips). */
  onToggleSelectAllVisible: (visibleFileIds: string[]) => void;
  disabled?: boolean;
}

async function parseFile(file: File): Promise<DatasetFile[]> {
  const text = await file.text();
  const createdAt = new Date().toISOString();
  if (file.name.endsWith('.jsonl')) {
    const out: DatasetFile[] = [];
    for (const line of text.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        const obj = JSON.parse(trimmed);
        const docText: unknown =
          typeof obj.text === 'string'
            ? obj.text
            : typeof obj.document?.text === 'string'
              ? obj.document.text
              : null;
        if (typeof docText !== 'string' || !docText) continue;
        const sourceLabel =
          (typeof obj.source_label === 'string' && obj.source_label) ||
          (typeof obj.id === 'string' && obj.id) ||
          (typeof obj.document?.id === 'string' && obj.document.id) ||
          `${file.name}#${out.length + 1}`;
        out.push({
          id: makeId(sourceLabel),
          sourceLabel,
          originalText: docText,
          annotations: [],
          detectionStatus: 'pending',
          resolved: false,
          createdAt,
        });
      } catch {
        /* skip malformed lines */
      }
    }
    return out;
  }
  return [
    {
      id: makeId(file.name),
      sourceLabel: file.name,
      originalText: text,
      annotations: [],
      detectionStatus: 'pending',
      resolved: false,
      createdAt,
    },
  ];
}

const STATUS_ICONS: Record<DetectionStatus, typeof Circle> = {
  pending: Circle,
  processing: Loader2,
  ready: FileText,
  error: AlertTriangle,
};

const STATUS_COLORS: Record<DetectionStatus, string> = {
  pending: 'text-gray-400',
  processing: 'text-blue-500 animate-spin',
  ready: 'text-gray-700',
  error: 'text-red-600',
};

export default function DatasetFileList({
  dataset,
  selectedIds,
  onToggleSelected,
  onToggleSelectAllVisible,
  disabled,
}: DatasetFileListProps) {
  const addFiles = useProductionStore((s) => s.addFiles);
  const removeFile = useProductionStore((s) => s.removeFile);
  const clearFiles = useProductionStore((s) => s.clearFiles);
  const setCurrentFile = useProductionStore((s) => s.setCurrentFile);
  const setFileResolved = useProductionStore((s) => s.setFileResolved);
  const setFileFlagged = useProductionStore((s) => s.setFileFlagged);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [filter, setFilter] = useState<'all' | 'todo' | 'resolved' | 'error'>('all');
  const [showPaste, setShowPaste] = useState(false);
  const confirm = useConfirm();

  const counts = useMemo(() => {
    let resolved = 0;
    let errored = 0;
    for (const f of dataset.files) {
      if (f.resolved) resolved += 1;
      else if (f.detectionStatus === 'error') errored += 1;
    }
    return { total: dataset.files.length, resolved, errored };
  }, [dataset.files]);

  const visible = useMemo(() => {
    switch (filter) {
      case 'todo':
        // Anything still on the user's plate: not yet resolved and not in
        // an error state. Covers both pre-detection (pending / processing)
        // and detected-but-not-yet-reviewed (ready) files.
        return dataset.files.filter(
          (f) => !f.resolved && f.detectionStatus !== 'error',
        );
      case 'resolved':
        return dataset.files.filter((f) => f.resolved);
      case 'error':
        return dataset.files.filter((f) => f.detectionStatus === 'error');
      case 'all':
      default:
        return dataset.files;
    }
  }, [dataset.files, filter]);

  const allVisibleSelected =
    visible.length > 0 && visible.every((f) => selectedIds.has(f.id));

  const handleFiles = async (files: FileList | null) => {
    if (!files) return;
    const parsed: DatasetFile[] = [];
    for (const f of Array.from(files)) {
      parsed.push(...(await parseFile(f)));
    }
    if (parsed.length) addFiles(dataset.id, parsed);
  };

  const handlePasteSubmit = (title: string, text: string) => {
    if (!text.trim()) return;
    const label =
      title.trim() ||
      `Pasted ${new Date().toLocaleString(undefined, {
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })}`;
    const file: DatasetFile = {
      id: makeId(label),
      sourceLabel: label,
      originalText: text,
      annotations: [],
      detectionStatus: 'pending',
      resolved: false,
      createdAt: new Date().toISOString(),
    };
    addFiles(dataset.id, [file]);
    setShowPaste(false);
  };

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-gray-200 bg-white">
      <div className="flex items-center justify-between border-b border-gray-200 px-3 py-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">
          Files
        </span>
        <span className="text-[11px] text-gray-400">
          {counts.resolved}/{counts.total} resolved
          {counts.errored > 0 && ` · ${counts.errored} err`}
        </span>
      </div>

      <div className="flex gap-1 border-b border-gray-200 p-2">
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
          className="flex flex-1 items-center justify-center gap-1 rounded bg-gray-900 px-2 py-1.5 text-xs font-medium text-white hover:bg-gray-800 disabled:opacity-40"
        >
          <Upload size={12} />
          Upload
        </button>
        <button
          type="button"
          onClick={() => setShowPaste(true)}
          disabled={disabled}
          className="flex items-center gap-1 rounded border border-gray-200 bg-white px-2 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-40"
        >
          <ClipboardPaste size={12} />
          Paste
        </button>
        {dataset.files.length > 0 && (
          <button
            type="button"
            onClick={async () => {
              const ok = await confirm({
                title: `Remove all files from "${dataset.name}"?`,
                message: `${dataset.files.length} file${
                  dataset.files.length === 1 ? '' : 's'
                } and all their annotations will be deleted.`,
                confirmLabel: 'Remove all',
                danger: true,
              });
              if (ok) clearFiles(dataset.id);
            }}
            className="rounded border border-gray-200 px-2 py-1.5 text-xs text-gray-500 hover:bg-gray-50"
            title="Clear all files in this dataset"
          >
            <Trash2 size={12} />
          </button>
        )}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".txt,.jsonl,text/plain,application/jsonl"
          className="hidden"
          onChange={(e) => {
            void handleFiles(e.target.files);
            e.target.value = '';
          }}
        />
      </div>

      <div className="flex items-center gap-1 border-b border-gray-100 px-2 py-1.5 text-[11px] text-gray-500">
        <label className="flex cursor-pointer items-center gap-1">
          <input
            type="checkbox"
            checked={allVisibleSelected}
            disabled={visible.length === 0 || disabled}
            onChange={() => onToggleSelectAllVisible(visible.map((f) => f.id))}
          />
          <span>Select all</span>
        </label>
        <span className="ml-auto text-[10px] text-gray-400">
          {selectedIds.size} selected
        </span>
      </div>

      <div className="flex gap-1 border-b border-gray-100 px-2 py-1 text-[10px]">
        {(
          [
            { id: 'all', label: 'All' },
            { id: 'todo', label: 'To do' },
            { id: 'resolved', label: 'Resolved' },
            { id: 'error', label: 'Error' },
          ] as const
        ).map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => setFilter(f.id)}
            className={clsx(
              'rounded px-1.5 py-0.5',
              filter === f.id ? 'bg-gray-900 text-white' : 'text-gray-500 hover:bg-gray-100',
            )}
            title={
              f.id === 'todo'
                ? 'Files still needing detection or review (anything not resolved)'
                : undefined
            }
          >
            {f.label}
          </button>
        ))}
      </div>

      <FileListBody
        visible={visible}
        selectedIds={selectedIds}
        onToggleSelected={onToggleSelected}
        currentFileId={dataset.currentFileId}
        onSelectCurrent={(id) => setCurrentFile(dataset.id, id)}
        onToggleResolved={(f) => setFileResolved(dataset.id, f.id, !f.resolved)}
        onToggleFlagged={(f) => setFileFlagged(dataset.id, f.id, !f.flagged)}
        onRemove={async (f) => {
          const ok = await confirm({
            title: `Remove "${f.sourceLabel}"?`,
            message: 'This file and its annotations will be deleted from the dataset.',
            confirmLabel: 'Remove',
            danger: true,
          });
          if (ok) removeFile(dataset.id, f.id);
        }}
        emptyMessage={
          dataset.files.length === 0
            ? 'No files yet. Paste or upload .txt / .jsonl to start.'
            : 'No files match this filter.'
        }
      />

      {showPaste && (
        <PasteModal
          onClose={() => setShowPaste(false)}
          onSubmit={handlePasteSubmit}
        />
      )}
    </aside>
  );
}

interface FileRowProps {
  file: DatasetFile;
  isCurrent: boolean;
  isSelected: boolean;
  onToggleSelected: (id: string) => void;
  onSelectCurrent: (id: string) => void;
  onToggleResolved: (f: DatasetFile) => void;
  onToggleFlagged: (f: DatasetFile) => void;
  onRemove: (f: DatasetFile) => void;
}

function FileRow({
  file: f,
  isCurrent,
  isSelected,
  onToggleSelected,
  onSelectCurrent,
  onToggleResolved,
  onToggleFlagged,
  onRemove,
}: FileRowProps) {
  const Icon = STATUS_ICONS[f.detectionStatus];
  const spanCount = f.detectionStatus === 'ready' ? f.annotations.length : null;
  return (
    <div
      role="button"
      tabIndex={0}
      aria-current={isCurrent ? 'true' : undefined}
      onClick={() => onSelectCurrent(f.id)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelectCurrent(f.id);
        }
      }}
      className={clsx(
        'flex h-9 cursor-pointer select-none items-center gap-1.5 border-l-2 border-b border-gray-100 px-2 text-xs transition-colors focus:outline-none focus-visible:bg-gray-100',
        isCurrent
          ? 'border-l-gray-900 bg-gray-50 text-gray-900'
          : 'border-l-transparent text-gray-700 hover:bg-gray-50',
      )}
    >
      <input
        type="checkbox"
        checked={isSelected}
        onClick={(e) => e.stopPropagation()}
        onChange={() => onToggleSelected(f.id)}
        className="shrink-0 cursor-pointer"
        aria-label={`Select ${f.sourceLabel}`}
      />
      <Icon
        size={13}
        className={clsx('shrink-0', STATUS_COLORS[f.detectionStatus])}
      />
      <span className="min-w-0 flex-1 truncate font-medium">{f.sourceLabel}</span>
      <span className="shrink-0 text-[10px] text-gray-400">
        {spanCount != null
          ? spanCount
          : f.detectionStatus === 'processing'
            ? '...'
            : f.detectionStatus === 'error'
              ? 'err'
              : ''}
      </span>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onToggleFlagged(f);
        }}
        className={clsx(
          'rounded p-0.5',
          f.flagged
            ? 'text-amber-600 hover:bg-amber-50'
            : 'text-gray-300 hover:bg-gray-100 hover:text-amber-500',
        )}
        title={f.flagged ? 'Unflag' : 'Flag'}
      >
        <Flag size={11} />
      </button>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onToggleResolved(f);
        }}
        className={clsx(
          'rounded p-0.5',
          f.resolved
            ? 'text-green-600 hover:bg-green-50'
            : 'text-gray-300 hover:bg-gray-100 hover:text-green-500',
        )}
        title={f.resolved ? 'Mark unresolved' : 'Mark resolved'}
      >
        <CheckCircle2 size={11} />
      </button>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onRemove(f);
        }}
        className="rounded p-0.5 text-gray-300 hover:bg-red-50 hover:text-red-500"
        title="Remove file"
      >
        <Trash2 size={11} />
      </button>
    </div>
  );
}

interface FileListBodyProps {
  visible: DatasetFile[];
  selectedIds: Set<string>;
  onToggleSelected: (id: string) => void;
  currentFileId: string | null;
  onSelectCurrent: (id: string) => void;
  onToggleResolved: (f: DatasetFile) => void;
  onToggleFlagged: (f: DatasetFile) => void;
  onRemove: (f: DatasetFile) => void;
  emptyMessage: string;
}

function FileListBody({
  visible,
  selectedIds,
  onToggleSelected,
  currentFileId,
  onSelectCurrent,
  onToggleResolved,
  onToggleFlagged,
  onRemove,
  emptyMessage,
}: FileListBodyProps) {
  const parentRef = useRef<HTMLDivElement | null>(null);
  const shouldVirtualize = visible.length > VIRTUALIZE_THRESHOLD;

  const virtualizer = useVirtualizer({
    count: shouldVirtualize ? visible.length : 0,
    estimateSize: () => ROW_HEIGHT_PX,
    overscan: 12,
    getScrollElement: () => parentRef.current,
  });

  if (visible.length === 0) {
    return (
      <div className="flex-1 overflow-auto">
        <p className="px-3 py-6 text-center text-xs text-gray-400">{emptyMessage}</p>
      </div>
    );
  }

  if (!shouldVirtualize) {
    return (
      <div className="flex-1 overflow-auto" ref={parentRef}>
        <ul className="m-0 list-none p-0">
          {visible.map((f) => (
            <li key={f.id}>
              <FileRow
                file={f}
                isCurrent={f.id === currentFileId}
                isSelected={selectedIds.has(f.id)}
                onToggleSelected={onToggleSelected}
                onSelectCurrent={onSelectCurrent}
                onToggleResolved={onToggleResolved}
                onToggleFlagged={onToggleFlagged}
                onRemove={onRemove}
              />
            </li>
          ))}
        </ul>
      </div>
    );
  }

  const items = virtualizer.getVirtualItems();
  const totalSize = virtualizer.getTotalSize();
  return (
    <div
      className="flex-1 overflow-auto"
      ref={parentRef}
      role="list"
      aria-rowcount={visible.length}
    >
      <div
        style={{
          height: totalSize,
          width: '100%',
          position: 'relative',
        }}
      >
        {items.map((item) => {
          const f = visible[item.index];
          return (
            <div
              key={f.id}
              role="listitem"
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${item.start}px)`,
              }}
            >
              <FileRow
                file={f}
                isCurrent={f.id === currentFileId}
                isSelected={selectedIds.has(f.id)}
                onToggleSelected={onToggleSelected}
                onSelectCurrent={onSelectCurrent}
                onToggleResolved={onToggleResolved}
                onToggleFlagged={onToggleFlagged}
                onRemove={onRemove}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
