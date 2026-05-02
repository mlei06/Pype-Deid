import { useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Keyboard,
  Loader2,
  PanelLeftClose,
  PanelLeftOpen,
  Play,
  Settings2,
  Square,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import DatasetFileList from './DatasetFileList';
import DocumentReviewer from './DocumentReviewer';
import { useFileListKeybinds } from './useFileListKeybinds';
import { useWorkspaceController } from './useWorkspaceController';

const SHORTCUTS: { keys: string; description: string }[] = [
  { keys: '↑ / ↓', description: 'Previous / next file in the list' },
  { keys: 'J / K', description: 'Next / previous unresolved file' },
  { keys: 'N', description: 'Next file whose detection failed' },
  { keys: 'R', description: 'Toggle resolved on the current file' },
  { keys: 'Enter / Space', description: 'Accept selected ghost span in review pane' },
  { keys: '⌫ / Delete', description: 'Remove the hovered or selected span' },
  { keys: '⌘/Ctrl+Z', description: 'Undo last span edit (Shift to redo)' },
  { keys: '[ / ]', description: 'Jump to previous / next overlap conflict' },
  { keys: '?', description: 'Show this cheat sheet' },
];

export default function WorkspaceView() {
  const {
    active,
    reviewer,
    modes,
    runTarget,
    setRunTarget,
    saveAsDefault,
    setSaveAsDefault,
    selectedMode,
    targetResolvable,
    currentFile,
    selectedIds,
    selectionCount,
    runButtonLabel,
    running,
    progress,
    toggleSelected,
    toggleSelectAllVisible,
    handleRun,
    cancel,
  } = useWorkspaceController();
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [showFiles, setShowFiles] = useState(true);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useFileListKeybinds({
    dataset: active,
    visible: active?.files ?? [],
    rootRef,
    enabled: !running,
    onOpenCheatSheet: () => setShowShortcuts(true),
  });

  useEffect(() => {
    setShowFiles(true);
  }, [active?.id]);

  if (!active) {
    return (
      <div className="flex h-full items-center justify-center bg-gray-50 p-8 text-sm text-gray-500">
        Pick a dataset from Library to start reviewing files.
      </div>
    );
  }

  return (
    <div ref={rootRef} className="flex h-full flex-col bg-gray-50" tabIndex={-1}>
      <header className="flex flex-wrap items-end gap-3 border-b border-gray-200 bg-white px-4 py-2">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500">Run with</label>
          <div className="flex items-center gap-2">
            <select
              value={runTarget}
              onChange={(e) => setRunTarget(e.target.value)}
              className="rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-800 shadow-sm"
            >
              <option value="">Select mode…</option>
              {modes.map((m) => (
                <option key={m.name} value={m.name} disabled={!m.available}>
                  {m.name}
                  {!m.available ? ' (unavailable)' : ''}
                </option>
              ))}
            </select>
            {selectedMode && selectedMode.available && (
              <span
                className="inline-flex items-center gap-1 text-[11px] text-gray-500"
                title={selectedMode.description}
              >
                <CheckCircle2 size={11} className="text-green-600" />
                <code className="text-gray-700">{selectedMode.pipeline}</code>
              </span>
            )}
            {selectedMode && !selectedMode.available && (
              <span className="inline-flex items-center gap-1 text-[11px] text-amber-700">
                <AlertCircle size={11} />
                missing: {selectedMode.missing.join(', ')}
              </span>
            )}
          </div>
          <label className="flex items-center gap-1 text-[10px] text-gray-500">
            <input
              type="checkbox"
              checked={saveAsDefault}
              onChange={(e) => setSaveAsDefault(e.target.checked)}
            />
            Set as dataset default
          </label>
        </div>

        <div className="ml-auto flex items-center gap-2">
          {active && (
            <Link
              to={`/datasets/${active.id}/export`}
              className="inline-flex items-center gap-1 rounded border border-gray-200 bg-white px-2 py-1.5 text-xs text-gray-600 hover:bg-gray-50"
            >
              <Settings2 size={12} />
              Export
            </Link>
          )}
          <button
            type="button"
            onClick={() => setShowFiles((v) => !v)}
            className="inline-flex items-center gap-1 rounded border border-gray-200 bg-white px-2 py-1.5 text-xs text-gray-600 hover:bg-gray-50"
            title={showFiles ? 'Hide file list' : 'Show file list'}
          >
            {showFiles ? <PanelLeftClose size={12} /> : <PanelLeftOpen size={12} />}
            Files
          </button>
          <button
            type="button"
            onClick={() => setShowShortcuts(true)}
            className="inline-flex items-center gap-1 rounded border border-gray-200 bg-white px-2 py-1.5 text-xs text-gray-600 hover:bg-gray-50"
          >
            <Keyboard size={12} />
            Shortcuts
          </button>
          {running && (
            <span className="text-[11px] text-blue-600">
              detecting {progress.done}/{progress.total}…
            </span>
          )}
          <button
            type="button"
            onClick={() => void handleRun()}
            disabled={!targetResolvable || running || (selectionCount === 0 && !currentFile)}
            className="flex items-center gap-1 rounded bg-gray-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-gray-800 disabled:opacity-40"
            title={
              !runTarget
                ? 'Pick a mode first'
                : selectedMode && !selectedMode.available
                  ? `Mode unavailable — missing: ${selectedMode.missing.join(', ')}`
                  : runButtonLabel
            }
          >
            {running ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
            {runButtonLabel}
          </button>
          {running && (
            <button
              type="button"
              onClick={cancel}
              className="inline-flex items-center gap-1 rounded border border-gray-200 bg-white px-2 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
            >
              <Square size={10} />
              Cancel
            </button>
          )}
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {showFiles && (
          <DatasetFileList
            dataset={active}
            selectedIds={selectedIds}
            onToggleSelected={toggleSelected}
            onToggleSelectAllVisible={toggleSelectAllVisible}
            disabled={running}
          />
        )}
        <div className="flex min-h-0 flex-1 flex-col">
          {currentFile ? (
            currentFile.detectionStatus === 'pending' ? (
              <EmptyPane message="Select this file in the list and click Run detection." />
            ) : currentFile.detectionStatus === 'processing' ? (
              <EmptyPane message="Detecting spans…" spinning />
            ) : currentFile.detectionStatus === 'error' ? (
              <EmptyPane
                message={`Detection failed: ${currentFile.error ?? 'unknown error'}`}
                tone="error"
              />
            ) : (
              <DocumentReviewer
                datasetId={active.id}
                dataset={active}
                file={currentFile}
                reviewer={reviewer}
              />
            )
          ) : (
            <EmptyPane message="No file selected. Add files or pick one from the list." />
          )}
        </div>
      </div>
      {showShortcuts && <ShortcutCheatSheet onClose={() => setShowShortcuts(false)} />}
    </div>
  );
}

function ShortcutCheatSheet({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-lg border border-gray-200 bg-white p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-800">Keyboard shortcuts</h2>
          <button type="button" onClick={onClose} className="text-xs text-gray-500 hover:text-gray-700">
            Close
          </button>
        </div>
        <table className="w-full text-sm">
          <tbody>
            {SHORTCUTS.map((s) => (
              <tr key={s.keys}>
                <td className="py-1 pr-4 font-mono text-xs text-gray-700">{s.keys}</td>
                <td className="py-1 text-gray-600">{s.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function EmptyPane({
  message,
  tone,
  spinning,
}: {
  message: string;
  tone?: 'error';
  spinning?: boolean;
}) {
  return (
    <div className="flex flex-1 items-center justify-center p-8">
      <div
        className={`flex items-center gap-2 rounded-md px-4 py-3 text-sm ${
          tone === 'error' ? 'border border-red-200 bg-red-50 text-red-700' : 'text-gray-500'
        }`}
      >
        {spinning && <Loader2 size={14} className="animate-spin" />}
        {message}
      </div>
    </div>
  );
}
