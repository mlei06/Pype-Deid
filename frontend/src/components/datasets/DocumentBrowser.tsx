import { useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, FileText } from 'lucide-react';
import { useDatasetPreview, useDocument } from '../../hooks/useDatasets';
import LabelBadge from '@shared/components/LabelBadge';
import SpanHighlighter from '../shared/SpanHighlighter';
import type { DocumentPreview } from '../../api/types';
import { splitLabelForDisplay, UNSPLIT_BUCKET } from './splitLabels';

interface DocumentBrowserProps {
  datasetName: string;
  splitDocumentCounts: Record<string, number>;
}

const PAGE_SIZE = 20;

/**
 * @param selected null = all splits; else include only these bucket keys
 */
function computeFilterSplits(
  selected: string[] | null,
  allKeys: string[],
): string[] | null {
  if (selected == null) return null;
  if (allKeys.length > 0 && selected.length === allKeys.length) return null;
  return selected;
}

export default function DocumentBrowser({ datasetName, splitDocumentCounts }: DocumentBrowserProps) {
  const [offset, setOffset] = useState(0);
  const [selectedDocIdOverride, setSelectedDocIdOverride] = useState<string | null>(null);
  const splitKeys = useMemo(
    () => Object.keys(splitDocumentCounts),
    [splitDocumentCounts],
  );
  /** null = all */
  const [selectedSplits, setSelectedSplits] = useState<string[] | null>(null);
  const filterSplits = useMemo(
    () => computeFilterSplits(selectedSplits, splitKeys),
    [selectedSplits, splitKeys],
  );

  const { data: page, isLoading } = useDatasetPreview(
    datasetName,
    offset,
    PAGE_SIZE,
    filterSplits,
  );
  const previews = page?.items;
  const totalFiltered = page?.total ?? 0;
  const selectedDocId =
    previews && previews.some((p) => p.document_id === selectedDocIdOverride)
      ? selectedDocIdOverride
      : (previews?.[0]?.document_id ?? null);
  const { data: docDetail, isLoading: detailLoading } = useDocument(datasetName, selectedDocId);

  const toggleKey = (key: string) => {
    setOffset(0);
    setSelectedSplits((prev) => {
      if (splitKeys.length === 0) return null;
      if (prev == null) {
        const next = splitKeys.filter((k) => k !== key);
        return next.length === 0 ? splitKeys : next;
      }
      if (prev.includes(key)) {
        const next = prev.filter((k) => k !== key);
        return next.length === 0 ? null : next;
      }
      const next = [...prev, key];
      if (next.length === splitKeys.length) return null;
      return next;
    });
  };

  if (isLoading) {
    return <div className="text-sm text-gray-400">Loading documents...</div>;
  }

  if (!previews?.length && offset === 0 && !filterSplits) {
    return <div className="text-sm text-gray-400">No documents in dataset</div>;
  }

  const isKeyOn = (key: string) =>
    selectedSplits == null ? true : selectedSplits.includes(key);

  return (
    <div className="flex flex-col gap-4">
      {splitKeys.length > 0 && (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <span className="text-xs font-medium text-gray-500">Include document splits</span>
          <div className="flex flex-wrap items-center gap-2">
            {splitKeys.map((k) => (
              <label
                key={k}
                className="inline-flex cursor-pointer items-center gap-1.5 rounded border border-gray-200 bg-white px-2 py-1 text-xs"
              >
                <input
                  type="checkbox"
                  className="rounded border-gray-300"
                  checked={isKeyOn(k)}
                  onChange={() => toggleKey(k)}
                />
                {splitLabelForDisplay(k)}
              </label>
            ))}
            {selectedSplits != null && (
              <button
                type="button"
                className="text-xs text-blue-600 hover:underline"
                onClick={() => {
                  setOffset(0);
                  setSelectedSplits(null);
                }}
              >
                All splits
              </button>
            )}
          </div>
        </div>
      )}

      {!previews?.length && offset === 0 ? (
        <p className="text-sm text-amber-800">No documents match the split filter.</p>
      ) : (
        <div className="grid gap-3 lg:grid-cols-[minmax(18rem,24rem)_1fr]">
          <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
            <div className="flex items-center justify-between border-b border-gray-200 bg-gray-50 px-3 py-2">
              <p className="text-xs font-medium text-gray-600">Documents</p>
              <span className="text-[11px] text-gray-500">
                {totalFiltered > 0
                  ? `${offset + 1}–${offset + (previews?.length ?? 0)} of ${totalFiltered}`
                  : `${offset + 1}–${offset + (previews?.length ?? 0)}`}
              </span>
            </div>
            <div className="max-h-[34rem] space-y-1 overflow-auto p-2">
              {previews?.map((d: DocumentPreview) => {
                const selected = d.document_id === selectedDocId;
                return (
                  <button
                    key={d.document_id}
                    type="button"
                    onClick={() => setSelectedDocIdOverride(d.document_id)}
                    className={`w-full rounded-md border px-2 py-2 text-left transition-colors ${
                      selected
                        ? 'border-blue-200 bg-blue-50'
                        : 'border-gray-200 bg-white hover:bg-gray-50'
                    }`}
                  >
                    <div className="mb-1 flex items-start justify-between gap-2">
                      <code className="truncate text-[11px] text-gray-700">{d.document_id}</code>
                      <span className="text-[10px] text-gray-500">{d.span_count} spans</span>
                    </div>
                    {splitKeys.length > 0 && (
                      <p className="mb-1 text-[10px] text-gray-500">
                        Split:{' '}
                        {d.split != null && d.split !== ''
                          ? splitLabelForDisplay(d.split)
                          : splitLabelForDisplay(UNSPLIT_BUCKET)}
                      </p>
                    )}
                    <p className="max-h-9 overflow-hidden text-[11px] text-gray-500">{d.text_preview}</p>
                  </button>
                );
              })}
            </div>
            <div className="flex items-center justify-between border-t border-gray-200 bg-gray-50 px-3 py-2">
              <button
                onClick={() => {
                  setOffset(Math.max(0, offset - PAGE_SIZE));
                  setSelectedDocIdOverride(null);
                }}
                disabled={offset === 0}
                className="flex items-center gap-1 text-xs text-gray-600 hover:text-gray-900 disabled:opacity-30"
              >
                <ChevronLeft size={14} /> Previous
              </button>
              <button
                onClick={() => {
                  setOffset(offset + PAGE_SIZE);
                  setSelectedDocIdOverride(null);
                }}
                disabled={!previews || offset + previews.length >= totalFiltered}
                className="flex items-center gap-1 text-xs text-gray-600 hover:text-gray-900 disabled:opacity-30"
              >
                Next <ChevronRight size={14} />
              </button>
            </div>
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-3">
            {detailLoading && <p className="text-sm text-gray-400">Loading selected document…</p>}
            {!detailLoading && docDetail && (
              <div className="flex flex-col gap-3">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-100 pb-2">
                  <div className="min-w-0">
                    <p className="text-[11px] uppercase tracking-wide text-gray-400">Document</p>
                    <code className="block truncate text-xs text-gray-700">{docDetail.document_id}</code>
                  </div>
                  <div className="flex flex-wrap items-center gap-1">
                    {[...new Set(docDetail.spans.map((s) => s.label))]
                      .sort((a, b) => a.localeCompare(b))
                      .map((label) => (
                        <LabelBadge key={label} label={label} />
                      ))}
                  </div>
                </div>
                <div className="max-h-[34rem] overflow-auto rounded border border-gray-100 bg-gray-50 p-2">
                  <SpanHighlighter
                    text={docDetail.text}
                    spans={docDetail.spans.map((s) => ({
                      start: s.start,
                      end: s.end,
                      label: s.label,
                      text: docDetail.text.slice(s.start, s.end),
                      confidence: s.confidence ?? null,
                      source: s.source ?? null,
                    }))}
                  />
                </div>
                {Object.keys(docDetail.metadata).length > 0 && (
                  <details>
                    <summary className="cursor-pointer text-xs text-gray-500 hover:text-gray-700">
                      Metadata
                    </summary>
                    <pre className="mt-1 overflow-x-auto rounded bg-gray-50 p-2 text-xs text-gray-600">
                      {JSON.stringify(docDetail.metadata, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            )}
            {!detailLoading && !docDetail && (
              <div className="flex h-56 items-center justify-center text-sm text-gray-400">
                <FileText size={16} className="mr-1.5" />
                Select a document to inspect annotations
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
