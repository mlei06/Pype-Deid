import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import LabelBadge from '@shared/components/LabelBadge';
import type { DatasetAnalytics, DatasetDetail } from '../../api/types';
import { useDatasetSplitAnalytics } from '../../hooks/useDatasets';
import { splitLabelForDisplay } from './splitLabels';

interface AnalyticsDashboardProps {
  dataset: DatasetDetail;
}

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">{label}</div>
      <div className="mt-1 text-2xl font-bold text-gray-900">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-gray-500">{sub}</div>}
    </div>
  );
}

function NumericRow({ label, stats }: { label: string; stats: { mean: number; min: number; max: number; std: number } }) {
  return (
    <tr>
      <td className="px-3 py-1.5 text-sm font-medium text-gray-700">{label}</td>
      <td className="px-3 py-1.5 text-sm text-gray-600">{stats.mean.toFixed(1)}</td>
      <td className="px-3 py-1.5 text-sm text-gray-600">{stats.min.toFixed(0)}</td>
      <td className="px-3 py-1.5 text-sm text-gray-600">{stats.max.toFixed(0)}</td>
      <td className="px-3 py-1.5 text-sm text-gray-600">{stats.std.toFixed(1)}</td>
    </tr>
  );
}

export default function AnalyticsDashboard({ dataset }: AnalyticsDashboardProps) {
  const splitOptions = Object.keys(dataset.split_document_counts ?? {});
  const [selected, setSelected] = useState<'all' | string>('all');
  const activeSplit = selected === 'all' ? null : selected;
  const { data: splitAnalytics, isLoading: splitLoading } = useDatasetSplitAnalytics(
    dataset.name,
    activeSplit,
  );

  const a: DatasetAnalytics | undefined =
    selected === 'all' ? dataset.analytics : splitAnalytics ?? undefined;

  if (!dataset.analytics) {
    return <div className="text-sm text-gray-400">No analytics available</div>;
  }

  if (selected !== 'all' && splitLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <Loader2 size={16} className="animate-spin" />
        Loading metrics for this split…
      </div>
    );
  }

  if (!a) {
    return <div className="text-sm text-gray-400">No analytics for this selection</div>;
  }

  if (a.document_count === 0 && selected === 'all') {
    return <div className="text-sm text-gray-400">This dataset has no documents.</div>;
  }

  const labelEntries = Object.entries(a.label_counts ?? {}).sort((a, b) => b[1] - a[1]);
  const spanHistEntries = Object.entries(a.span_length_histogram ?? {});
  const docBySpanEntries = Object.entries(a.documents_by_span_count ?? {});

  return (
    <div className="flex flex-col gap-5">
      {splitOptions.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-gray-500">Metrics for</span>
          <select
            value={selected}
            onChange={(e) => {
              const v = e.target.value;
              setSelected(v === 'all' ? 'all' : v);
            }}
            className="rounded-md border border-gray-200 bg-white px-2 py-1.5 text-sm text-gray-800 shadow-sm focus:border-gray-500 focus:outline-none focus:ring-1 focus:ring-gray-500"
          >
            <option value="all">All documents</option>
            {splitOptions.map((k) => (
              <option key={k} value={k}>
                {splitLabelForDisplay(k)}
              </option>
            ))}
          </select>
        </div>
      )}

      {a.document_count === 0 && selected !== 'all' && (
        <p className="text-sm text-amber-700">No documents in this split.</p>
      )}

      {/* Summary cards */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Documents" value={a.document_count} />
        <StatCard label="Total Spans" value={a.total_spans} sub={`${a.unique_label_count} unique labels`} />
        {a.spans_per_document ? (
          <StatCard
            label="Avg Spans / Doc"
            value={a.spans_per_document.mean.toFixed(1)}
            sub={`std ${a.spans_per_document.std.toFixed(1)}`}
          />
        ) : (
          <StatCard label="Avg Spans / Doc" value="—" sub="refresh to compute" />
        )}
        {a.documents_with_overlapping_spans != null ? (
          <StatCard
            label="Overlapping Docs"
            value={a.documents_with_overlapping_spans}
            sub={`${a.overlapping_span_pairs} span pairs`}
          />
        ) : (
          <StatCard label="Overlapping Docs" value="—" sub="refresh to compute" />
        )}
      </div>

      {/* Numeric distributions */}
      <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
        <div className="border-b border-gray-200 bg-gray-50 px-4 py-2">
          <h4 className="text-xs font-bold uppercase tracking-wider text-gray-500">Distributions</h4>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              <th className="px-3 py-1.5 text-left text-[10px] font-semibold uppercase text-gray-400">Metric</th>
              <th className="px-3 py-1.5 text-left text-[10px] font-semibold uppercase text-gray-400">Mean</th>
              <th className="px-3 py-1.5 text-left text-[10px] font-semibold uppercase text-gray-400">Min</th>
              <th className="px-3 py-1.5 text-left text-[10px] font-semibold uppercase text-gray-400">Max</th>
              <th className="px-3 py-1.5 text-left text-[10px] font-semibold uppercase text-gray-400">Std</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {a.character_length && <NumericRow label="Char length" stats={a.character_length} />}
            {a.token_count_estimate && <NumericRow label="Token count" stats={a.token_count_estimate} />}
            {a.spans_per_document && <NumericRow label="Spans / doc" stats={a.spans_per_document} />}
            {a.span_character_length && <NumericRow label="Span length (chars)" stats={a.span_character_length} />}
          </tbody>
        </table>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Label breakdown */}
        <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
          <div className="border-b border-gray-200 bg-gray-50 px-4 py-2">
            <h4 className="text-xs font-bold uppercase tracking-wider text-gray-500">Labels</h4>
          </div>
          <div className="max-h-64 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-white">
                <tr className="border-b border-gray-100">
                  <th className="px-3 py-1.5 text-left text-[10px] font-semibold uppercase text-gray-400">Label</th>
                  <th className="px-3 py-1.5 text-right text-[10px] font-semibold uppercase text-gray-400">Count</th>
                  <th className="px-3 py-1.5 text-right text-[10px] font-semibold uppercase text-gray-400">%</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {labelEntries.map(([label, count]) => (
                  <tr key={label}>
                    <td className="px-3 py-1.5"><LabelBadge label={label} /></td>
                    <td className="px-3 py-1.5 text-right text-gray-700">{count}</td>
                    <td className="px-3 py-1.5 text-right text-gray-500">
                      {a.total_spans ? ((count / a.total_spans) * 100).toFixed(1) : 0}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Span length histogram */}
        <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
          <div className="border-b border-gray-200 bg-gray-50 px-4 py-2">
            <h4 className="text-xs font-bold uppercase tracking-wider text-gray-500">Span Lengths</h4>
          </div>
          <div className="p-4">
            {spanHistEntries.length > 0 ? (
              <div className="flex flex-col gap-2">
                {spanHistEntries.map(([bucket, count]) => {
                  const maxCount = Math.max(...spanHistEntries.map(([, c]) => c));
                  const pct = maxCount > 0 ? (count / maxCount) * 100 : 0;
                  return (
                    <div key={bucket} className="flex items-center gap-2">
                      <span className="w-16 text-right text-xs text-gray-500">{bucket}</span>
                      <div className="flex-1 h-4 rounded bg-gray-100">
                        <div
                          className="h-4 rounded bg-blue-400"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="w-10 text-xs text-gray-600">{count}</span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-sm text-gray-400">No spans</div>
            )}
          </div>
        </div>
      </div>

      {/* Documents by span count */}
      {docBySpanEntries.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
          <div className="border-b border-gray-200 bg-gray-50 px-4 py-2">
            <h4 className="text-xs font-bold uppercase tracking-wider text-gray-500">Documents by Span Count</h4>
          </div>
          <div className="p-4">
            <div className="flex flex-wrap gap-2">
              {docBySpanEntries.map(([k, count]) => (
                <div
                  key={k}
                  className="flex flex-col items-center rounded border border-gray-200 px-2 py-1"
                >
                  <span className="text-xs font-medium text-gray-700">{count}</span>
                  <span className="text-[10px] text-gray-400">{k} spans</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
