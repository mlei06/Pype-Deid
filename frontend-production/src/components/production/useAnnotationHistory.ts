import { useCallback, useEffect, useRef, useState } from 'react';
import type { EntitySpanResponse } from '../../api/types';
import { useProductionStore } from './store';

const MAX_HISTORY = 50;

interface AnnotationHistory {
  /** Apply an annotation update and push the previous value onto the undo stack. */
  commit: (next: EntitySpanResponse[]) => void;
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  /** Wall-clock millis of the last commit/undo/redo on this file (null if none yet). */
  lastChangeAt: number | null;
}

/**
 * Per-file undo/redo over annotation arrays. History is kept in refs (not in
 * the persisted store) so it doesn't bloat IndexedDB or survive reloads —
 * undo is for the current editing session.
 *
 * Reads current annotations directly from the zustand store on each call so
 * back-to-back commits within the same render correctly capture every step.
 */
export function useAnnotationHistory(
  datasetId: string,
  fileId: string,
): AnnotationHistory {
  const updateFile = useProductionStore((s) => s.updateFile);
  const undoRef = useRef<EntitySpanResponse[][]>([]);
  const redoRef = useRef<EntitySpanResponse[][]>([]);
  const [, force] = useState(0);
  const [lastChangeAt, setLastChangeAt] = useState<number | null>(null);

  useEffect(() => {
    undoRef.current = [];
    redoRef.current = [];
    setLastChangeAt(null);
    force((n) => n + 1);
  }, [datasetId, fileId]);

  const readSpans = useCallback((): EntitySpanResponse[] => {
    const ds = useProductionStore.getState().datasets[datasetId];
    return ds?.files.find((f) => f.id === fileId)?.annotations ?? [];
  }, [datasetId, fileId]);

  const commit = useCallback(
    (next: EntitySpanResponse[]) => {
      undoRef.current.push(readSpans());
      if (undoRef.current.length > MAX_HISTORY) undoRef.current.shift();
      redoRef.current = [];
      updateFile(datasetId, fileId, { annotations: next });
      setLastChangeAt(Date.now());
      force((n) => n + 1);
    },
    [datasetId, fileId, updateFile, readSpans],
  );

  const undo = useCallback(() => {
    const prev = undoRef.current.pop();
    if (prev === undefined) return;
    redoRef.current.push(readSpans());
    updateFile(datasetId, fileId, { annotations: prev });
    setLastChangeAt(Date.now());
    force((n) => n + 1);
  }, [datasetId, fileId, updateFile, readSpans]);

  const redo = useCallback(() => {
    const nxt = redoRef.current.pop();
    if (nxt === undefined) return;
    undoRef.current.push(readSpans());
    updateFile(datasetId, fileId, { annotations: nxt });
    setLastChangeAt(Date.now());
    force((n) => n + 1);
  }, [datasetId, fileId, updateFile, readSpans]);

  return {
    commit,
    undo,
    redo,
    canUndo: undoRef.current.length > 0,
    canRedo: redoRef.current.length > 0,
    lastChangeAt,
  };
}
