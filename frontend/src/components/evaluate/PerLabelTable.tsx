import { useState, useMemo } from 'react';
import { ArrowUpDown } from 'lucide-react';
import LabelBadge from '@shared/components/LabelBadge';
import type { LabelMetricsDetail } from '../../api/types';

interface PerLabelTableProps {
  perLabel: Record<string, LabelMetricsDetail>;
}

type SortKey = 'label' | 'f1' | 'precision' | 'recall' | 'support';

function TH({ k, label, onSort }: { k: SortKey; label: string; onSort: (k: SortKey) => void }) {
  return (
    <th
      className="cursor-pointer px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-gray-500 hover:text-gray-700"
      onClick={() => onSort(k)}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        <ArrowUpDown size={10} />
      </span>
    </th>
  );
}

export default function PerLabelTable({ perLabel }: PerLabelTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>('support');
  const [sortAsc, setSortAsc] = useState(false);

  const rows = useMemo(() => {
    const entries = Object.entries(perLabel).map(([label, m]) => ({
      label,
      f1: m.strict.f1,
      precision: m.strict.precision,
      recall: m.strict.recall,
      support: m.support,
    }));

    entries.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (typeof av === 'string' && typeof bv === 'string')
        return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
      return sortAsc ? (av as number) - (bv as number) : (bv as number) - (av as number);
    });

    return entries;
  }, [perLabel, sortKey, sortAsc]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else {
      setSortKey(key);
      setSortAsc(false);
    }
  };

  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
      <table className="w-full text-sm">
        <thead className="border-b border-gray-200 bg-gray-50">
          <tr>
            <TH k="label" label="Label" onSort={toggleSort} />
            <TH k="precision" label="Precision" onSort={toggleSort} />
            <TH k="recall" label="Recall" onSort={toggleSort} />
            <TH k="f1" label="F1" onSort={toggleSort} />
            <TH k="support" label="Support" onSort={toggleSort} />
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {rows.map((r) => (
            <tr key={r.label} className="hover:bg-gray-50">
              <td className="px-3 py-2">
                <LabelBadge label={r.label} />
              </td>
              <td className="px-3 py-2 text-gray-600">{(r.precision * 100).toFixed(1)}%</td>
              <td className={`px-3 py-2 ${r.recall < 0.5 ? 'font-semibold text-red-600' : 'text-gray-600'}`}>
                {(r.recall * 100).toFixed(1)}%
              </td>
              <td className="px-3 py-2 font-medium text-gray-900">{(r.f1 * 100).toFixed(1)}%</td>
              <td className="px-3 py-2 text-gray-400">{r.support}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
