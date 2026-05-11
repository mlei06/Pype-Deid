import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, RefreshCw, X } from 'lucide-react';
import { clsx } from 'clsx';
import { redactDocument } from '../../api/production';
import RedactedView from '@shared/components/RedactedView';
import SpanHighlighter from '../shared/SpanHighlighter';
import {
  getCachedOutput,
  hashAnnotations,
  hashSourceText,
  putCachedOutput,
  type CachedOutput,
  type PreviewMode,
} from '../../lib/outputCache';
import { dedupeSpansKeepPrimary } from '../../lib/spanOverlapConflicts';
import type { EntitySpanResponse } from '../../api/types';

interface PreviewColumnProps {
  datasetId: string;
  fileId: string;
  originalText: string;
  annotations: EntitySpanResponse[];
  reviewer: string;
  /** Seed string. Free text in the input; hashed to an int at the API boundary. */
  seed: string;
  onSeedChange: (seed: string) => void;
  onClose: () => void;
}

const DEBOUNCE_MS = 300;

/** Stable string→int mapping so a free-text seed becomes a number for the API. */
function seedStringToInt(seed: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h & 0x7fffffff;
}

function rollSeed(): string {
  return Math.floor(Math.random() * 1_000_000_000).toString(36);
}

export default function PreviewColumn({
  datasetId,
  fileId,
  originalText,
  annotations,
  reviewer,
  seed,
  onSeedChange,
  onClose,
}: PreviewColumnProps) {
  const [mode, setMode] = useState<PreviewMode>('redacted');
  const [cached, setCached] = useState<CachedOutput | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fetchSeqRef = useRef(0);

  const textHash = useMemo(() => hashSourceText(originalText), [originalText]);
  const annotationsHash = useMemo(() => hashAnnotations(annotations), [annotations]);

  const fetchPreview = useCallback(async () => {
    const mySeq = ++fetchSeqRef.current;

    // Empty annotations: redacted = original text; surrogate = original text.
    if (annotations.length === 0) {
      const value: CachedOutput = {
        text: originalText,
        spans: [],
        generatedAt: new Date().toISOString(),
      };
      putCachedOutput({
        datasetId,
        fileId,
        textHash,
        annotationsHash,
        mode,
        seed,
        value,
      });
      setCached(value);
      setError(null);
      setLoading(false);
      return;
    }

    const hit = getCachedOutput({ textHash, annotationsHash, mode, seed });
    if (hit) {
      setCached(hit);
      setError(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const res = await redactDocument(
        {
          text: originalText,
          spans: annotations.map((s) => ({
            start: s.start,
            end: s.end,
            label: s.label,
          })),
          output_mode: mode === 'redacted' ? 'redacted' : 'surrogate',
          include_surrogate_spans: mode === 'surrogate',
          surrogate_consistency: true,
          surrogate_seed: mode === 'surrogate' ? seedStringToInt(seed) : null,
        },
        reviewer || 'production-ui',
      );
      if (fetchSeqRef.current !== mySeq) return;

      const value: CachedOutput =
        mode === 'redacted'
          ? {
              text: res.output_text,
              spans: [],
              generatedAt: new Date().toISOString(),
            }
          : {
              text: res.surrogate_text ?? res.output_text,
              spans: (res.surrogate_spans ?? []).map((s) => ({ ...s })),
              generatedAt: new Date().toISOString(),
            };
      putCachedOutput({
        datasetId,
        fileId,
        textHash,
        annotationsHash,
        mode,
        seed,
        value,
      });
      setCached(value);
    } catch (err) {
      if (fetchSeqRef.current !== mySeq) return;
      setError(err instanceof Error ? err.message : 'preview failed');
      setCached(null);
    } finally {
      if (fetchSeqRef.current === mySeq) setLoading(false);
    }
  }, [
    datasetId,
    fileId,
    originalText,
    annotations,
    annotationsHash,
    textHash,
    mode,
    seed,
    reviewer,
  ]);

  useEffect(() => {
    const handle = setTimeout(() => {
      void fetchPreview();
    }, DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [fetchPreview]);

  const surrogateDisplaySpans = useMemo(() => {
    if (!cached || mode !== 'surrogate') return [];
    return dedupeSpansKeepPrimary(cached.spans);
  }, [cached, mode]);

  const showRoll = mode === 'surrogate';

  return (
    <aside className="flex h-full w-full min-w-0 flex-col border-l border-gray-200 bg-white">
      <header className="flex flex-wrap items-center gap-1.5 border-b border-gray-200 px-2 py-1.5">
        <div className="flex rounded border border-gray-200 bg-gray-50 p-0.5 text-[10px]">
          {(['redacted', 'surrogate'] as PreviewMode[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={clsx(
                'rounded px-2 py-0.5 font-medium capitalize',
                mode === m ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500',
              )}
            >
              {m}
            </button>
          ))}
        </div>
        {showRoll && (
          <div className="flex items-center gap-1">
            <label className="text-[10px] text-gray-500" htmlFor="preview-seed">
              seed
            </label>
            <input
              id="preview-seed"
              value={seed}
              onChange={(e) => onSeedChange(e.target.value)}
              className="w-20 rounded border border-gray-200 bg-white px-1 py-0.5 font-mono text-[10px] text-gray-800"
              title="Free-text seed; same seed + same annotations → same surrogate values"
            />
            <button
              type="button"
              onClick={() => onSeedChange(rollSeed())}
              className="rounded p-0.5 text-gray-500 hover:bg-gray-100"
              title="Roll a new seed"
            >
              <RefreshCw size={11} />
            </button>
          </div>
        )}
        <span className="ml-auto inline-flex items-center gap-1 text-[10px] text-gray-400">
          {loading && <Loader2 size={11} className="animate-spin" />}
          {!loading && cached && 'cached'}
        </span>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-0.5 text-gray-500 hover:bg-gray-100"
          title="Hide preview"
        >
          <X size={12} />
        </button>
      </header>

      <div className={clsx('min-h-0 flex-1 overflow-auto p-3 text-sm', loading && 'opacity-60')}>
        {error ? (
          <div className="space-y-2">
            <p className="rounded border border-red-200 bg-red-50 px-2 py-1 text-xs text-red-700">
              {error}
            </p>
            <button
              type="button"
              onClick={() => void fetchPreview()}
              className="rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-700 hover:bg-gray-50"
            >
              Retry
            </button>
          </div>
        ) : !cached ? (
          <p className="text-xs text-gray-400">Generating preview…</p>
        ) : mode === 'redacted' ? (
          <RedactedView text={cached.text} />
        ) : surrogateDisplaySpans.length > 0 ? (
          <SpanHighlighter text={cached.text} spans={surrogateDisplaySpans} />
        ) : (
          <RedactedView text={cached.text} />
        )}
      </div>
    </aside>
  );
}
