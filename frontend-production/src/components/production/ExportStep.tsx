import { useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Download,
  Loader2,
  Package,
  Play,
  RefreshCw,
  Square,
  UploadCloud,
} from 'lucide-react';
import JSZip from 'jszip';
import { ApiError } from '../../api/client';
import { uploadDataset } from '../../api/datasets';
import { getHealth } from '../../api/health';
import { downloadBlob } from '../../lib/download';
import {
  hashAnnotations,
  invalidateCacheForDataset,
} from '../../lib/outputCache';
import { dedupeSpansKeepPrimary } from '../../lib/spanOverlapConflicts';
import RedactedView from '@shared/components/RedactedView';
import SpanHighlighter from '../shared/SpanHighlighter';
import {
  useProductionStore,
  type Dataset,
  type DatasetFile,
  type ExportOutputType,
} from './store';
import {
  useBatchGenerate,
  type FileBatchResult,
} from './useBatchGenerate';

interface ExportStepProps {
  dataset: Dataset;
  reviewer: string;
}

interface JsonlLine {
  schema_version: 1;
  output_type: ExportOutputType;
  id: string;
  source_label: string;
  text: string;
  spans: Array<{
    start: number;
    end: number;
    label: string;
    confidence?: number | null;
    source?: string | null;
  }>;
  resolved: boolean;
  metadata?: Record<string, unknown>;
}

const OUTPUT_TYPES: { value: ExportOutputType; label: string; helper: string }[] = [
  { value: 'annotated', label: 'annotated', helper: 'Original text with spans. No API call.' },
  {
    value: 'redacted',
    label: 'redacted',
    helper: 'Replace each span with [LABEL]. Hits /process/redact.',
  },
  {
    value: 'surrogate_annotated',
    label: 'surrogate',
    helper: 'Realistic fake values, aligned spans. Hits /process/redact.',
  },
];

function safeStem(name: string): string {
  return name.replace(/[\\/]/g, '_').replace(/\s+/g, '_').slice(0, 120) || 'dataset';
}

function buildLine(
  file: DatasetFile,
  result: FileBatchResult,
  outputType: ExportOutputType,
  dataset: Dataset,
  reviewer: string,
  exportedAt: string,
): JsonlLine {
  const text = result.text ?? '';
  const spans = (result.spans ?? []).map((s) => ({
    start: s.start,
    end: s.end,
    label: s.label,
    confidence: s.confidence ?? null,
    source: s.source ?? null,
  }));
  const annotationsAtGenerate = result.annotationsAtGenerate ?? file.annotations;
  return {
    schema_version: 1,
    output_type: outputType,
    id: file.id,
    source_label: file.sourceLabel,
    text,
    spans,
    resolved: file.resolved,
    metadata: {
      dataset_name: dataset.name,
      exported_at: exportedAt,
      reviewer: reviewer || null,
      note: file.note ?? null,
      last_detection_target: file.lastDetectionTarget ?? null,
      original_text: outputType === 'annotated' ? null : file.originalText,
      original_spans:
        outputType === 'annotated'
          ? null
          : annotationsAtGenerate.map((s) => ({
              start: s.start,
              end: s.end,
              label: s.label,
            })),
    },
  };
}

function buildJsonl(lines: JsonlLine[]): string {
  return lines.map((l) => JSON.stringify(l)).join('\n') + '\n';
}

function isResultStale(file: DatasetFile, result: FileBatchResult | undefined): boolean {
  if (!result || result.status !== 'ok') return false;
  if (!result.annotationsAtGenerate) return false;
  return (
    hashAnnotations(file.annotations) !==
    hashAnnotations(result.annotationsAtGenerate)
  );
}

export default function ExportStep({ dataset, reviewer }: ExportStepProps) {
  const lastScope = useProductionStore((s) => s.lastExportScope);
  const setLastScope = useProductionStore((s) => s.setLastExportScope);
  const setDatasetExportType = useProductionStore((s) => s.setDatasetExportType);

  const [scope, setScope] = useState<'all' | 'resolved'>(lastScope);
  const [outputType, setOutputType] = useState<ExportOutputType>(
    dataset.exportOutputType,
  );
  const [seed, setSeed] = useState<string>(dataset.defaultSurrogateSeed ?? '0');
  const [asZip, setAsZip] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloadSummary, setDownloadSummary] = useState<string | null>(null);
  const [reviewIndex, setReviewIndex] = useState(0);

  const [registerOpen, setRegisterOpen] = useState(false);
  const [regName, setRegName] = useState('');
  const [regDescription, setRegDescription] = useState('');
  const [isRegistering, setIsRegistering] = useState(false);
  const [regError, setRegError] = useState<string | null>(null);

  const [apiKeyScope, setApiKeyScope] = useState<'admin' | 'inference' | null | undefined>(
    undefined,
  );
  const [healthLoaded, setHealthLoaded] = useState(false);

  const { run, cancel, running, progress, results, reset } = useBatchGenerate();

  const chosen = useMemo(
    () =>
      scope === 'resolved'
        ? dataset.files.filter((f) => f.resolved)
        : dataset.files,
    [scope, dataset.files],
  );

  const successFiles = useMemo(
    () => chosen.filter((f) => results[f.id]?.status === 'ok'),
    [chosen, results],
  );
  const errorFiles = useMemo(
    () => chosen.filter((f) => results[f.id]?.status === 'error'),
    [chosen, results],
  );
  const generatedCount = successFiles.length;
  const everGenerated = Object.keys(results).length > 0;

  const staleFiles = useMemo(
    () =>
      chosen.filter((f) => {
        const r = results[f.id];
        if (!r || r.status !== 'ok') return false;
        if (!r.annotationsAtGenerate) return false;
        return (
          hashAnnotations(f.annotations) !==
          hashAnnotations(r.annotationsAtGenerate)
        );
      }),
    [chosen, results],
  );

  // Reset reviewIndex when scope or generation results change shape.
  useEffect(() => {
    setReviewIndex(0);
  }, [scope, dataset.id]);
  useEffect(() => {
    if (successFiles.length === 0) return;
    setReviewIndex((i) => Math.min(i, successFiles.length - 1));
  }, [successFiles.length]);

  // Reset downstream state when the active dataset changes.
  useEffect(() => {
    reset();
    setDownloadError(null);
    setDownloadSummary(null);
  }, [dataset.id, reset]);

  // Load API key scope for the Register button.
  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((h) => {
        if (cancelled) return;
        setApiKeyScope(h.api_key_scope ?? null);
        setHealthLoaded(true);
      })
      .catch(() => {
        if (cancelled) return;
        setApiKeyScope(null);
        setHealthLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const setScopeAndRemember = (s: 'all' | 'resolved') => {
    setScope(s);
    setLastScope(s);
  };

  const setOutputTypeAndRemember = (t: ExportOutputType) => {
    setOutputType(t);
    setDatasetExportType(dataset.id, t);
    // Generated outputs of a different type are no longer applicable.
    reset();
  };

  const startGenerate = () => {
    setDownloadError(null);
    setDownloadSummary(null);
    void run({
      dataset,
      files: chosen,
      outputType,
      seedOverride: seed,
      reviewer,
    });
  };

  const regenerateStale = () => {
    if (staleFiles.length === 0) return;
    void run({
      dataset,
      files: staleFiles,
      outputType,
      seedOverride: seed,
      reviewer,
    });
  };

  const retryFailed = () => {
    if (errorFiles.length === 0) return;
    void run({
      dataset,
      files: errorFiles,
      outputType,
      seedOverride: seed,
      reviewer,
    });
  };

  const dropCacheAndRegenerate = () => {
    invalidateCacheForDataset(dataset.id);
    reset();
    void run({
      dataset,
      files: chosen,
      outputType,
      seedOverride: seed,
      reviewer,
    });
  };

  const buildExportLines = (): { lines: JsonlLine[]; exportedAt: string } => {
    const exportedAt = new Date().toISOString();
    const lines: JsonlLine[] = [];
    for (const f of chosen) {
      const r = results[f.id];
      if (!r || r.status !== 'ok') continue;
      lines.push(buildLine(f, r, outputType, dataset, reviewer, exportedAt));
    }
    return { lines, exportedAt };
  };

  const handleDownload = () => {
    if (generatedCount === 0) {
      setDownloadError('No generated outputs to download. Generate first.');
      return;
    }
    setDownloadError(null);
    const { lines, exportedAt } = buildExportLines();
    const jsonl = buildJsonl(lines);
    const stamp = exportedAt.slice(0, 10);
    const stem = safeStem(dataset.name);
    if (asZip) {
      const zip = new JSZip();
      zip.file('corpus.jsonl', jsonl);
      zip.file(
        'manifest.json',
        JSON.stringify(
          {
            schema_version: 1,
            dataset_name: dataset.name,
            dataset_id: dataset.id,
            output_type: outputType,
            scope,
            line_count: lines.length,
            reviewer: reviewer || null,
            exported_at: exportedAt,
            surrogate_seed: outputType === 'surrogate_annotated' ? seed : null,
          },
          null,
          2,
        ),
      );
      void zip.generateAsync({ type: 'blob' }).then((blob) => {
        downloadBlob(`${stem}_${stamp}.zip`, blob, 'application/zip');
      });
    } else {
      downloadBlob(
        `${stem}_${stamp}.jsonl`,
        new Blob([jsonl], { type: 'application/jsonl' }),
        'application/jsonl',
      );
    }
    setDownloadSummary(`${lines.length} line(s) · ${outputType} · ${scope}`);
  };

  const canRegisterOnServer =
    healthLoaded && apiKeyScope === 'admin' && generatedCount > 0;
  const registerTitle = (() => {
    if (!healthLoaded) return 'Checking API key scope…';
    if (apiKeyScope === 'inference') {
      return 'Register requires an admin API key (configured key is inference-only).';
    }
    if (apiKeyScope !== 'admin') {
      return 'Set VITE_API_KEY to an admin API key.';
    }
    if (generatedCount === 0) return 'Generate output before registering.';
    return 'Register this export on the Datasets API.';
  })();

  const openRegister = () => {
    if (!canRegisterOnServer) return;
    setRegError(null);
    setRegName(
      safeStem(dataset.name)
        .toLowerCase()
        .replace(/[^a-z0-9._-]+/g, '-')
        .replace(/^-+|-+$/g, '') || 'dataset',
    );
    setRegDescription(`Production export: ${dataset.name} (${outputType})`);
    setRegisterOpen(true);
  };

  const handleRegister = async () => {
    if (!regName.trim()) {
      setRegError('Dataset name is required.');
      return;
    }
    setRegError(null);
    setIsRegistering(true);
    try {
      const { lines } = buildExportLines();
      const jsonl = buildJsonl(lines);
      const blob = new Blob([jsonl], { type: 'application/x-ndjson' });
      const res = await uploadDataset({
        name: regName.trim(),
        file: blob,
        filename: `${safeStem(dataset.name)}.jsonl`,
        description: regDescription.trim() || undefined,
        lineFormat: 'production_v1',
      });
      setRegisterOpen(false);
      setDownloadSummary(
        `Registered on server: ${res.name} · ${res.document_count} document(s)`,
      );
    } catch (err) {
      if (err instanceof ApiError) {
        const d = err.detail;
        setRegError(typeof d === 'string' ? d : JSON.stringify(d));
      } else {
        setRegError(err instanceof Error ? err.message : 'register failed');
      }
    } finally {
      setIsRegistering(false);
    }
  };

  const currentFile = successFiles[reviewIndex] ?? null;
  const currentResult = currentFile ? results[currentFile.id] : null;

  const surrogateDisplaySpans = useMemo(() => {
    if (!currentResult || outputType !== 'surrogate_annotated') return [];
    return dedupeSpansKeepPrimary(currentResult.spans ?? []);
  }, [currentResult, outputType]);

  return (
    <div className="flex h-full flex-col">
      {/* Configure */}
      <section className="border-b border-gray-200 bg-white p-4">
        <div className="flex flex-wrap items-end gap-4">
          <fieldset>
            <legend className="text-[11px] font-medium text-gray-500">Scope</legend>
            <div className="mt-1 flex gap-2 text-[11px] text-gray-700">
              <label className="flex items-center gap-1">
                <input
                  type="radio"
                  name="export-scope"
                  checked={scope === 'all'}
                  onChange={() => setScopeAndRemember('all')}
                />
                All ({dataset.files.length})
              </label>
              <label className="flex items-center gap-1">
                <input
                  type="radio"
                  name="export-scope"
                  checked={scope === 'resolved'}
                  onChange={() => setScopeAndRemember('resolved')}
                />
                Resolved only ({dataset.files.filter((f) => f.resolved).length})
              </label>
            </div>
          </fieldset>

          <fieldset>
            <legend className="text-[11px] font-medium text-gray-500">Output</legend>
            <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-gray-700">
              {OUTPUT_TYPES.map((t) => (
                <label key={t.value} className="flex items-center gap-1" title={t.helper}>
                  <input
                    type="radio"
                    name="export-output-type"
                    checked={outputType === t.value}
                    onChange={() => setOutputTypeAndRemember(t.value)}
                  />
                  {t.label}
                </label>
              ))}
            </div>
          </fieldset>

          {outputType === 'surrogate_annotated' && (
            <div className="flex flex-col">
              <label className="text-[11px] font-medium text-gray-500" htmlFor="export-seed">
                Seed
              </label>
              <div className="mt-1 flex items-center gap-1">
                <input
                  id="export-seed"
                  value={seed}
                  onChange={(e) => setSeed(e.target.value)}
                  className="w-28 rounded border border-gray-300 bg-white px-2 py-1 font-mono text-[11px] text-gray-800"
                />
                <button
                  type="button"
                  onClick={() => setSeed(Math.floor(Math.random() * 1_000_000_000).toString(36))}
                  className="rounded p-1 text-gray-500 hover:bg-gray-100"
                  title="Roll a new seed"
                >
                  <RefreshCw size={12} />
                </button>
              </div>
            </div>
          )}

          <div className="ml-auto flex items-center gap-2">
            {running && (
              <span className="text-[11px] text-blue-600">
                generating {progress.done}/{progress.total}…
              </span>
            )}
            <button
              type="button"
              onClick={startGenerate}
              disabled={chosen.length === 0 || running}
              className="flex items-center gap-1 rounded bg-gray-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-gray-800 disabled:opacity-40"
              title={
                chosen.length === 0
                  ? 'No files in this scope'
                  : `Generate ${outputType} output for ${chosen.length} file(s)`
              }
            >
              {running ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
              Generate Output
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
        </div>
      </section>

      {/* Status banners (stale, errors) */}
      {everGenerated && (staleFiles.length > 0 || errorFiles.length > 0) && (
        <section className="border-b border-gray-200 bg-amber-50 px-4 py-2 text-[11px] text-amber-900">
          <div className="flex flex-wrap items-center gap-3">
            {staleFiles.length > 0 && (
              <span className="inline-flex items-center gap-1">
                <AlertCircle size={12} />
                {staleFiles.length} file(s) edited since generation
                <button
                  type="button"
                  onClick={regenerateStale}
                  disabled={running}
                  className="ml-1 inline-flex items-center gap-1 rounded border border-amber-300 bg-white px-1.5 py-0.5 text-[10px] font-medium text-amber-900 hover:bg-amber-100 disabled:opacity-50"
                >
                  <RefreshCw size={10} />
                  Regenerate
                </button>
              </span>
            )}
            {errorFiles.length > 0 && (
              <span className="inline-flex items-center gap-1 text-red-700">
                <AlertCircle size={12} />
                {errorFiles.length} file(s) failed
                <button
                  type="button"
                  onClick={retryFailed}
                  disabled={running}
                  className="ml-1 inline-flex items-center gap-1 rounded border border-red-300 bg-white px-1.5 py-0.5 text-[10px] font-medium text-red-700 hover:bg-red-100 disabled:opacity-50"
                >
                  <RefreshCw size={10} />
                  Retry failed
                </button>
              </span>
            )}
            <button
              type="button"
              onClick={dropCacheAndRegenerate}
              disabled={running}
              className="ml-auto text-[10px] text-amber-700 underline hover:text-amber-900 disabled:opacity-50"
              title="Drop the client cache and regenerate every file from scratch"
            >
              Force regenerate all
            </button>
          </div>
        </section>
      )}

      {/* Pager */}
      <section className="min-h-0 flex-1 overflow-auto p-4">
        {!everGenerated ? (
          <EmptyPanel
            message={
              chosen.length === 0
                ? 'No files in scope. Adjust scope or import files first.'
                : 'Press Generate Output to produce previews and downloadable artifacts.'
            }
          />
        ) : currentFile && currentResult?.status === 'ok' ? (
          <div className="flex h-full min-h-[280px] flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2 text-[11px]">
              <button
                type="button"
                onClick={() => setReviewIndex((i) => Math.max(0, i - 1))}
                disabled={reviewIndex === 0}
                className="inline-flex items-center gap-1 rounded border border-gray-200 bg-white px-2 py-1 text-gray-700 hover:bg-gray-50 disabled:opacity-40"
              >
                <ChevronLeft size={12} />
                Prev
              </button>
              <button
                type="button"
                onClick={() =>
                  setReviewIndex((i) => Math.min(successFiles.length - 1, i + 1))
                }
                disabled={reviewIndex >= successFiles.length - 1}
                className="inline-flex items-center gap-1 rounded border border-gray-200 bg-white px-2 py-1 text-gray-700 hover:bg-gray-50 disabled:opacity-40"
              >
                Next
                <ChevronRight size={12} />
              </button>
              <span className="text-gray-600">
                {reviewIndex + 1}/{successFiles.length}
              </span>
              <code className="rounded bg-gray-100 px-1.5 py-0.5 text-[11px]">
                {outputType}
              </code>
              <span className="text-gray-700">{currentFile.sourceLabel}</span>
              {isResultStale(currentFile, currentResult) && (
                <span className="rounded bg-amber-100 px-1.5 py-0.5 text-amber-800">stale</span>
              )}
            </div>
            <div className="min-h-0 flex-1 overflow-auto rounded border border-gray-200 bg-gray-50 p-3 text-sm">
              {outputType === 'redacted' ? (
                <RedactedView text={currentResult.text ?? ''} />
              ) : surrogateDisplaySpans.length > 0 ? (
                <SpanHighlighter
                  text={currentResult.text ?? ''}
                  spans={surrogateDisplaySpans}
                />
              ) : outputType === 'annotated' ? (
                <SpanHighlighter
                  text={currentResult.text ?? ''}
                  spans={currentResult.spans ?? []}
                />
              ) : (
                <RedactedView text={currentResult.text ?? ''} />
              )}
            </div>
          </div>
        ) : (
          <EmptyPanel
            message={
              successFiles.length === 0
                ? 'No successful outputs to preview yet.'
                : 'Pick a successful file to preview.'
            }
          />
        )}
      </section>

      {/* Action footer */}
      <section className="flex flex-wrap items-center gap-3 border-t border-gray-200 bg-white px-4 py-3">
        <label className="flex items-center gap-1 text-[11px] text-gray-600">
          <input
            type="checkbox"
            checked={asZip}
            onChange={(e) => setAsZip(e.target.checked)}
          />
          Wrap in .zip with manifest
        </label>
        {downloadSummary && (
          <span className="text-[11px] text-gray-500">{downloadSummary}</span>
        )}
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            title={registerTitle}
            onClick={openRegister}
            disabled={!canRegisterOnServer}
            className="flex items-center gap-1 rounded border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-800 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <UploadCloud size={12} />
            Register as dataset
          </button>
          <button
            type="button"
            onClick={handleDownload}
            disabled={generatedCount === 0}
            className="flex items-center gap-1 rounded bg-gray-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-gray-800 disabled:opacity-40"
          >
            {asZip ? <Package size={12} /> : <Download size={12} />}
            {asZip ? 'Download .zip' : 'Download .jsonl'}
          </button>
        </div>
        {downloadError && (
          <div className="basis-full rounded border border-red-200 bg-red-50 px-2 py-1 text-xs text-red-700">
            {downloadError}
          </div>
        )}
      </section>

      {registerOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="register-dataset-title"
        >
          <div className="w-full max-w-md rounded-lg border border-gray-200 bg-white p-4 shadow-lg">
            <h2 id="register-dataset-title" className="text-sm font-semibold text-gray-900">
              Register as dataset
            </h2>
            <p className="mt-1 text-[11px] text-gray-500">
              Creates a new dataset on the API from this export (line_format=production_v1).
              Requires an admin API key.
            </p>
            <div className="mt-3 space-y-2">
              <label className="block text-[11px] font-medium text-gray-600" htmlFor="reg-name">
                Dataset name
              </label>
              <input
                id="reg-name"
                type="text"
                value={regName}
                onChange={(e) => setRegName(e.target.value)}
                className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
                autoFocus
              />
              <label className="block text-[11px] font-medium text-gray-600" htmlFor="reg-desc">
                Description
              </label>
              <input
                id="reg-desc"
                type="text"
                value={regDescription}
                onChange={(e) => setRegDescription(e.target.value)}
                className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
              />
            </div>
            {regError && (
              <div className="mt-2 rounded border border-red-200 bg-red-50 px-2 py-1 text-xs text-red-800">
                {regError}
              </div>
            )}
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setRegisterOpen(false)}
                disabled={isRegistering}
                className="rounded border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void handleRegister()}
                disabled={isRegistering}
                className="inline-flex items-center gap-1 rounded bg-gray-900 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
              >
                {isRegistering ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <UploadCloud size={12} />
                )}
                Register
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function EmptyPanel({ message }: { message: string }) {
  return (
    <div className="flex h-full min-h-[260px] items-center justify-center rounded border border-dashed border-gray-300 bg-gray-50 text-sm text-gray-500">
      {message}
    </div>
  );
}
