import { useMemo, useState } from 'react';
import DeltaBadge from './DeltaBadge';
import { delta, pct } from './util';
import type { EvalPerDocumentItem, EvalRunDetail } from '../../../api/types';

interface ComparePerDocProps {
  runs: EvalRunDetail[];
}

interface DocRow {
  documentId: string;
  /** Per-run F1 (strict). null when this run didn't see this doc. */
  perRunF1: (number | null)[];
  /** Per-run FP / FN counts. */
  perRunFp: (number | null)[];
  perRunFn: (number | null)[];
  /** Smallest F1 across runs that *do* have it — drives the "worst doc" sort. */
  minF1: number;
  /** True when at least one run is missing this doc (e.g., different corpora). */
  hasGap: boolean;
}

export default function ComparePerDoc({ runs }: ComparePerDocProps) {
  const [view, setView] = useState<'shared' | 'union'>('shared');

  const { rows, missingPerDocCount } = useMemo(() => buildRows(runs, view), [runs, view]);

  if (missingPerDocCount === runs.length) {
    return (
      <p className="rounded-md border border-dashed border-gray-200 bg-white p-6 text-center text-sm text-gray-400">
        None of these runs include per-document data. Re-run them to populate this view.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end justify-between gap-3 rounded-lg border border-gray-200 bg-white p-3">
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-medium uppercase tracking-wider text-gray-500">View</span>
          <div className="flex items-center gap-1 rounded-md border border-gray-200 p-0.5">
            <button
              type="button"
              onClick={() => setView('shared')}
              className={`rounded px-2 py-1 text-xs font-medium ${
                view === 'shared'
                  ? 'bg-gray-900 text-white'
                  : 'text-gray-600 hover:bg-gray-50'
              }`}
            >
              Shared docs
            </button>
            <button
              type="button"
              onClick={() => setView('union')}
              className={`rounded px-2 py-1 text-xs font-medium ${
                view === 'union'
                  ? 'bg-gray-900 text-white'
                  : 'text-gray-600 hover:bg-gray-50'
              }`}
            >
              Union (any run)
            </button>
          </div>
        </div>
        {missingPerDocCount > 0 && (
          <p className="text-[11px] text-amber-700">
            {missingPerDocCount} of {runs.length} run(s) lack per-document data — those runs render as gaps.
          </p>
        )}
      </div>

      {rows.length === 0 ? (
        <p className="rounded-md border border-dashed border-gray-200 bg-white p-6 text-center text-sm text-gray-400">
          {view === 'shared'
            ? 'No documents are present in every selected run. Switch to "Union" to see what each run scored independently.'
            : 'No per-document rows available.'}
        </p>
      ) : (
        <div className="overflow-auto rounded-lg border border-gray-200 bg-white">
          <table className="min-w-full text-sm">
            <thead className="border-b border-gray-200 bg-gray-50">
              <tr>
                <th className="sticky left-0 z-10 bg-gray-50 px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                  Document
                </th>
                {runs.map((r, idx) => (
                  <th
                    key={r.id}
                    className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-gray-500"
                  >
                    <div className="truncate" title={`${r.pipeline_name} · ${r.dataset_source}`}>
                      {r.pipeline_name}
                    </div>
                    <div className="text-[9px] font-normal lowercase tracking-normal text-gray-400">
                      {idx === 0 ? 'baseline strict F1' : 'strict F1 · Δ'}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {rows.map((row) => (
                <tr key={row.documentId} className="hover:bg-gray-50">
                  <td className="sticky left-0 z-10 bg-white px-3 py-2">
                    <code className="rounded bg-gray-100 px-1 py-0.5 text-[11px] font-mono">
                      {row.documentId}
                    </code>
                    {row.hasGap && (
                      <span className="ml-1.5 inline-flex items-center text-[10px] text-amber-700">
                        partial
                      </span>
                    )}
                  </td>
                  {row.perRunF1.map((f1, idx) => {
                    const baselineF1 = row.perRunF1[0];
                    const fp = row.perRunFp[idx];
                    const fn = row.perRunFn[idx];
                    return (
                      <td key={runs[idx].id} className="px-3 py-2 text-xs">
                        {f1 == null ? (
                          <span className="text-gray-300">—</span>
                        ) : (
                          <div className="flex flex-col gap-0.5">
                            <div className="flex items-baseline gap-2">
                              <span className="font-medium text-gray-900">{pct(f1)}</span>
                              {idx > 0 && baselineF1 != null && (
                                <DeltaBadge delta={delta(f1, baselineF1)} compact />
                              )}
                            </div>
                            {(fp != null || fn != null) && (
                              <div className="flex items-baseline gap-2 text-[10px] text-gray-400">
                                {fp != null && (
                                  <span>
                                    FP <span className="font-mono text-rose-600">{fp}</span>
                                  </span>
                                )}
                                {fn != null && (
                                  <span>
                                    FN <span className="font-mono text-amber-600">{fn}</span>
                                  </span>
                                )}
                              </div>
                            )}
                          </div>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function buildRows(
  runs: EvalRunDetail[],
  view: 'shared' | 'union',
): { rows: DocRow[]; missingPerDocCount: number } {
  // Build {document_id -> per-run F1 / FP / FN} maps.
  const perRunMaps = runs.map((r) => {
    const items = (r.metrics?.document_level as EvalPerDocumentItem[] | undefined) ?? [];
    const m = new Map<string, EvalPerDocumentItem>();
    for (const item of items) m.set(item.document_id, item);
    return m;
  });
  const missingPerDocCount = perRunMaps.filter((m) => m.size === 0).length;

  let docIds: string[];
  if (view === 'shared') {
    if (missingPerDocCount === runs.length) docIds = [];
    else {
      // Intersection of doc ids across runs that have per-doc data.
      const withData = perRunMaps.filter((m) => m.size > 0);
      const first = withData[0];
      docIds = [...first.keys()].filter((id) => withData.every((m) => m.has(id)));
    }
  } else {
    const all = new Set<string>();
    for (const m of perRunMaps) for (const id of m.keys()) all.add(id);
    docIds = [...all];
  }

  const rows: DocRow[] = docIds.map((id) => {
    const perRunF1: (number | null)[] = [];
    const perRunFp: (number | null)[] = [];
    const perRunFn: (number | null)[] = [];
    let minF1 = 1;
    let hasGap = false;
    for (const m of perRunMaps) {
      const item = m.get(id);
      if (!item) {
        perRunF1.push(null);
        perRunFp.push(null);
        perRunFn.push(null);
        hasGap = true;
        continue;
      }
      const f1 = item.metrics.strict?.f1 ?? 0;
      perRunF1.push(f1);
      perRunFp.push(item.false_positive_count);
      perRunFn.push(item.false_negative_count);
      if (f1 < minF1) minF1 = f1;
    }
    return { documentId: id, perRunF1, perRunFp, perRunFn, minF1, hasGap };
  });

  // Worst-first.
  rows.sort((a, b) => a.minF1 - b.minF1);
  // Cap to keep the page snappy.
  return { rows: rows.slice(0, 200), missingPerDocCount };
}
