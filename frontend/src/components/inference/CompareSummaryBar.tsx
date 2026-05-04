import { summarizePair } from '../../lib/spanCompare';
import type { ProcessResponse } from '../../api/types';

interface NamedResult {
  name: string;
  result: ProcessResponse;
}

interface CompareSummaryBarProps {
  results: NamedResult[];
}

/** Mini-row of pairwise comparison stats. Shown once ≥2 pipelines have run. */
export default function CompareSummaryBar({ results }: CompareSummaryBarProps) {
  if (results.length < 2) return null;

  // For 2 pipelines, one row. For 3, three pairs (1↔2, 1↔3, 2↔3).
  const pairs: Array<{ a: NamedResult; b: NamedResult }> = [];
  for (let i = 0; i < results.length; i++) {
    for (let j = i + 1; j < results.length; j++) {
      pairs.push({ a: results[i]!, b: results[j]! });
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2 border-y border-gray-100 bg-gray-50/60 px-3 py-1.5 text-[11px]">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
        Compare
      </span>
      {pairs.map(({ a, b }) => {
        const s = summarizePair(a.result.spans, b.result.spans);
        return (
          <div
            key={`${a.name}__${b.name}`}
            className="flex items-center gap-1.5 rounded-md border border-gray-200 bg-white px-2 py-0.5"
          >
            <span className="max-w-[140px] truncate font-mono text-[10px] text-gray-700" title={a.name}>
              {a.name}
            </span>
            <span className="text-gray-400">↔</span>
            <span className="max-w-[140px] truncate font-mono text-[10px] text-gray-700" title={b.name}>
              {b.name}
            </span>
            <span className="rounded bg-emerald-100 px-1 text-[10px] font-medium text-emerald-800" title="Spans both pipelines flagged identically">
              ={s.agreed}
            </span>
            <span className="rounded bg-sky-100 px-1 text-[10px] font-medium text-sky-800" title={`Only in ${a.name}`}>
              ←{s.onlyA}
            </span>
            <span className="rounded bg-violet-100 px-1 text-[10px] font-medium text-violet-800" title={`Only in ${b.name}`}>
              →{s.onlyB}
            </span>
            {s.relabeled > 0 && (
              <span className="rounded bg-amber-100 px-1 text-[10px] font-medium text-amber-800" title="Same range, different label">
                Δ{s.relabeled}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
