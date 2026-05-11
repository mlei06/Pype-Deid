import { useState } from 'react';
import { ShieldCheck, ShieldAlert, ArrowUpDown } from 'lucide-react';
import { clsx } from 'clsx';
import LabelBadge from '@shared/components/LabelBadge';
import type { RedactionMetrics } from '../../api/types';

interface RedactionDashboardProps {
  redaction: RedactionMetrics;
}

function pct(value: number): string {
  return (value * 100).toFixed(1) + '%';
}

export default function RedactionDashboard({ redaction }: RedactionDashboardProps) {
  const [showLeaked, setShowLeaked] = useState(false);

  const isClean = redaction.leaked_phi_count === 0;

  return (
    <div className="flex flex-col gap-4">
      {/* Summary cards */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {/* Redaction Recall */}
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-gray-400">
            Redaction Recall
          </div>
          <div className={clsx(
            'text-2xl font-bold',
            redaction.redaction_recall >= 1.0 ? 'text-green-600' :
            redaction.redaction_recall >= 0.9 ? 'text-yellow-600' : 'text-red-600',
          )}>
            {pct(redaction.redaction_recall)}
          </div>
          <div className="mt-1 text-[10px] text-gray-400">
            {redaction.gold_phi_count - redaction.leaked_phi_count} / {redaction.gold_phi_count} PHI items redacted
          </div>
        </div>

        {/* Leakage Rate */}
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-gray-400">
            Leakage Rate
          </div>
          <div className={clsx(
            'text-2xl font-bold',
            redaction.leakage_rate === 0 ? 'text-green-600' :
            redaction.leakage_rate <= 0.1 ? 'text-yellow-600' : 'text-red-600',
          )}>
            {pct(redaction.leakage_rate)}
          </div>
          <div className="mt-1 text-[10px] text-gray-400">
            {redaction.leaked_phi_count} PHI item{redaction.leaked_phi_count !== 1 ? 's' : ''} leaked
          </div>
        </div>

        {/* Gold PHI Count */}
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-gray-400">
            Gold PHI Items
          </div>
          <div className="text-2xl font-bold text-gray-900">
            {redaction.gold_phi_count}
          </div>
          <div className="mt-1 text-[10px] text-gray-400">
            gold span occurrences
          </div>
        </div>

        {/* Text Size Change */}
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-gray-400">
            Text Size Change
          </div>
          <div className="text-lg font-semibold text-gray-700">
            {redaction.original_length.toLocaleString()} &rarr; {redaction.redacted_length.toLocaleString()}
          </div>
          <div className="mt-1 text-[10px] text-gray-400">
            {redaction.over_redaction_chars > 0
              ? `~${redaction.over_redaction_chars} non-PHI chars removed`
              : 'no over-redaction detected'}
          </div>
        </div>
      </div>

      {/* Status banner */}
      {isClean ? (
        <div className="flex items-center gap-2 rounded-md bg-green-50 border border-green-200 px-3 py-2 text-sm text-green-700">
          <ShieldCheck size={16} />
          No PHI leakage detected — all gold-standard PHI was successfully redacted from the output.
        </div>
      ) : (
        <div className="flex items-center gap-2 rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
          <ShieldAlert size={16} />
          {redaction.leaked_phi_count} PHI item{redaction.leaked_phi_count !== 1 ? 's' : ''} still
          appear verbatim in the redacted output.
        </div>
      )}

      {/* Per-label leakage table */}
      {redaction.per_label.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
          <table className="w-full text-sm">
            <thead className="border-b border-gray-200 bg-gray-50">
              <tr>
                <th className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                  Label
                </th>
                <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                  Gold
                </th>
                <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                  Leaked
                </th>
                <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                  Leakage Rate
                </th>
                <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                  Redacted
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {redaction.per_label.map((ll) => (
                <tr key={ll.label} className="hover:bg-gray-50">
                  <td className="px-3 py-2">
                    <LabelBadge label={ll.label} />
                  </td>
                  <td className="px-3 py-2 text-right text-gray-600">{ll.gold_count}</td>
                  <td className={clsx(
                    'px-3 py-2 text-right',
                    ll.leaked_count > 0 ? 'font-semibold text-red-600' : 'text-gray-400',
                  )}>
                    {ll.leaked_count}
                  </td>
                  <td className={clsx(
                    'px-3 py-2 text-right',
                    ll.leakage_rate > 0 ? 'font-semibold text-red-600' : 'text-green-600',
                  )}>
                    {pct(ll.leakage_rate)}
                  </td>
                  <td className="px-3 py-2 text-right text-green-600">
                    {pct(1 - ll.leakage_rate)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Leaked spans detail (expandable) */}
      {redaction.leaked_spans.length > 0 && (
        <div>
          <button
            onClick={() => setShowLeaked(!showLeaked)}
            className="flex items-center gap-1 text-xs font-medium text-gray-600 hover:text-gray-900"
          >
            <ArrowUpDown size={12} />
            {showLeaked ? 'Hide' : 'Show'} leaked PHI details ({redaction.leaked_spans.length})
          </button>

          {showLeaked && (
            <div className="mt-2 overflow-hidden rounded-lg border border-red-200 bg-white">
              <table className="w-full text-sm">
                <thead className="border-b border-red-100 bg-red-50">
                  <tr>
                    <th className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-red-500">
                      Label
                    </th>
                    <th className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-red-500">
                      Leaked Text
                    </th>
                    <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-red-500">
                      Occurrences
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-red-50">
                  {redaction.leaked_spans.map((ls, i) => (
                    <tr key={i} className="hover:bg-red-50/50">
                      <td className="px-3 py-2">
                        <LabelBadge label={ls.label} />
                      </td>
                      <td className="px-3 py-2 font-mono text-red-700">
                        {ls.original_text}
                      </td>
                      <td className="px-3 py-2 text-right text-gray-500">
                        {ls.found_at.length}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
