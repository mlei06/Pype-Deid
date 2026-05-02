import { useMemo, useState } from 'react';
import { ArrowUpDown, Search } from 'lucide-react';
import { clsx } from 'clsx';
import LabelBadge from '../../shared/LabelBadge';
import DeltaBadge from './DeltaBadge';
import { delta, getLabelMetric, getPerLabel, MATCHING_MODES, modeLabel, pct } from './util';
import type { MatchingMode } from './util';
import type { EvalRunDetail } from '../../../api/types';

interface ComparePerLabelProps {
  runs: EvalRunDetail[];
}

type Metric = 'f1' | 'precision' | 'recall';
type SortBy = 'label' | 'baseline' | 'maxAbsDelta';

const PER_LABEL_MODES: MatchingMode[] = MATCHING_MODES.filter(
  (m) => m !== 'exact_boundary',
);

export default function ComparePerLabel({ runs }: ComparePerLabelProps) {
  const [mode, setMode] = useState<MatchingMode>('strict');
  const [metric, setMetric] = useState<Metric>('f1');
  const [sortBy, setSortBy] = useState<SortBy>('maxAbsDelta');
  const [showOnly, setShowOnly] = useState<'all' | 'changed' | 'regressed'>('all');
  const [filterText, setFilterText] = useState('');

  const baseline = runs[0];
  const labels = useMemo(() => collectLabels(runs), [runs]);

  const rows = useMemo(() => {
    const baseMap = getPerLabel(baseline);
    const out = labels.map((label) => {
      const baseM = getLabelMetric(baseMap[label], mode);
      const baseValue = baseM ? baseM[metric] : null;
      const cells = runs.map((run) => {
        if (run.id === baseline.id) {
          return { value: baseValue, delta: null as number | null, support: baseM?.tp != null ? (baseMap[label]?.support ?? 0) : null };
        }
        const lm = getLabelMetric(getPerLabel(run)[label], mode);
        const value = lm ? lm[metric] : null;
        return {
          value,
          delta: delta(value, baseValue),
          support: getPerLabel(run)[label]?.support ?? null,
        };
      });
      const deltas = cells.map((c) => c.delta).filter((d): d is number => d != null);
      const maxAbsDelta = deltas.length > 0 ? Math.max(...deltas.map((d) => Math.abs(d))) : 0;
      const minDelta = deltas.length > 0 ? Math.min(...deltas) : 0;
      return { label, cells, baselineSupport: baseMap[label]?.support ?? 0, maxAbsDelta, minDelta };
    });

    let filtered = out;
    if (filterText.trim()) {
      const needle = filterText.trim().toLowerCase();
      filtered = filtered.filter((r) => r.label.toLowerCase().includes(needle));
    }
    if (showOnly === 'changed') {
      filtered = filtered.filter((r) => r.maxAbsDelta >= 0.005);
    } else if (showOnly === 'regressed') {
      filtered = filtered.filter((r) => r.minDelta <= -0.005);
    }

    if (sortBy === 'label') {
      filtered.sort((a, b) => a.label.localeCompare(b.label));
    } else if (sortBy === 'baseline') {
      filtered.sort((a, b) => (b.cells[0].value ?? -1) - (a.cells[0].value ?? -1));
    } else {
      filtered.sort((a, b) => b.maxAbsDelta - a.maxAbsDelta);
    }
    return filtered;
  }, [labels, runs, baseline, mode, metric, sortBy, showOnly, filterText]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-gray-200 bg-white p-3">
        <Selector
          label="Match mode"
          value={mode}
          options={PER_LABEL_MODES.map((m) => ({ id: m, label: modeLabel(m) }))}
          onChange={(v) => setMode(v as MatchingMode)}
        />
        <Selector
          label="Metric"
          value={metric}
          options={[
            { id: 'f1', label: 'F1' },
            { id: 'precision', label: 'Precision' },
            { id: 'recall', label: 'Recall' },
          ]}
          onChange={(v) => setMetric(v as Metric)}
        />
        <Selector
          label="Sort by"
          value={sortBy}
          options={[
            { id: 'maxAbsDelta', label: 'Largest move' },
            { id: 'baseline', label: 'Baseline value' },
            { id: 'label', label: 'Label name' },
          ]}
          onChange={(v) => setSortBy(v as SortBy)}
        />
        <Selector
          label="Show"
          value={showOnly}
          options={[
            { id: 'all', label: 'All labels' },
            { id: 'changed', label: 'Changed only' },
            { id: 'regressed', label: 'Regressions only' },
          ]}
          onChange={(v) => setShowOnly(v as typeof showOnly)}
        />
        <div className="relative">
          <Search
            size={12}
            className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-gray-400"
          />
          <input
            type="text"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            placeholder="Filter labels…"
            className="rounded-md border border-gray-300 bg-white py-1.5 pl-7 pr-2 text-xs shadow-sm focus:border-gray-500 focus:ring-1 focus:ring-gray-500 focus:outline-none"
          />
        </div>
      </div>

      {rows.length === 0 ? (
        <p className="rounded-md border border-dashed border-gray-200 bg-white p-6 text-center text-sm text-gray-400">
          No labels match this filter.
        </p>
      ) : (
        <div className="overflow-auto rounded-lg border border-gray-200 bg-white">
          <table className="min-w-full text-sm">
            <thead className="border-b border-gray-200 bg-gray-50">
              <tr>
                <th className="sticky left-0 z-10 bg-gray-50 px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                  <button
                    type="button"
                    onClick={() => setSortBy('label')}
                    className="inline-flex items-center gap-1 hover:text-gray-700"
                  >
                    Label
                    <ArrowUpDown size={10} />
                  </button>
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
                      {idx === 0 ? 'baseline' : `vs ${runs[0].pipeline_name}`}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {rows.map((r) => (
                <tr key={r.label} className="hover:bg-gray-50">
                  <td className="sticky left-0 z-10 bg-white px-3 py-2">
                    <div className="flex items-center gap-2">
                      <LabelBadge label={r.label} />
                      <span className="text-[10px] text-gray-400">
                        n={r.baselineSupport}
                      </span>
                    </div>
                  </td>
                  {r.cells.map((cell, idx) => (
                    <td
                      key={runs[idx].id}
                      className={clsx(
                        'px-3 py-2 text-xs',
                        idx === 0 ? 'bg-gray-50/40' : '',
                      )}
                    >
                      <div className="flex items-baseline gap-2">
                        <span className="font-medium text-gray-900">{pct(cell.value)}</span>
                        <DeltaBadge delta={cell.delta} compact />
                      </div>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Selector({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { id: string; label: string }[];
  onChange: (next: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] font-medium uppercase tracking-wider text-gray-500">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-gray-300 bg-white px-2 py-1.5 text-xs shadow-sm focus:border-gray-500 focus:ring-1 focus:ring-gray-500 focus:outline-none"
      >
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function collectLabels(runs: EvalRunDetail[]): string[] {
  const set = new Set<string>();
  for (const run of runs) {
    for (const k of Object.keys(getPerLabel(run))) set.add(k);
  }
  return [...set].sort((a, b) => a.localeCompare(b));
}
