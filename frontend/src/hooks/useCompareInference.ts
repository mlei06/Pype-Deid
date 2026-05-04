import { useCallback, useRef, useState } from 'react';
import { processText } from '../api/process';
import type { ProcessResponse } from '../api/types';

export type CompareEntryStatus = 'idle' | 'pending' | 'success' | 'error';

export interface CompareEntry {
  status: CompareEntryStatus;
  result?: ProcessResponse;
  error?: string;
  elapsedMs?: number;
}

export interface CompareResults {
  results: Record<string, CompareEntry>;
  runAll: (pipelines: string[], text: string) => void;
  reset: () => void;
  isAnyPending: boolean;
}

/**
 * Fires `processText` for N pipelines in parallel and tracks per-pipeline state.
 * A request-id ref guards against late callbacks from a stale run overwriting
 * results from a newer run (e.g. user clicks Run, then Run again before the
 * first batch settles).
 */
export function useCompareInference(): CompareResults {
  const [results, setResults] = useState<Record<string, CompareEntry>>({});
  const requestIdRef = useRef(0);

  const runAll = useCallback((pipelines: string[], text: string) => {
    if (!text.trim() || pipelines.length === 0) return;
    const reqId = ++requestIdRef.current;

    const initial: Record<string, CompareEntry> = {};
    for (const p of pipelines) initial[p] = { status: 'pending' };
    setResults(initial);

    pipelines.forEach((name) => {
      const t0 = performance.now();
      processText(name, { text }, true).then(
        (result) => {
          if (requestIdRef.current !== reqId) return;
          setResults((prev) => ({
            ...prev,
            [name]: {
              status: 'success',
              result,
              elapsedMs: performance.now() - t0,
            },
          }));
        },
        (err: unknown) => {
          if (requestIdRef.current !== reqId) return;
          const msg = err instanceof Error ? err.message : 'Run failed';
          setResults((prev) => ({
            ...prev,
            [name]: { status: 'error', error: msg },
          }));
        },
      );
    });
  }, []);

  const reset = useCallback(() => {
    requestIdRef.current++;
    setResults({});
  }, []);

  const isAnyPending = Object.values(results).some((r) => r.status === 'pending');

  return { results, runAll, reset, isAnyPending };
}
