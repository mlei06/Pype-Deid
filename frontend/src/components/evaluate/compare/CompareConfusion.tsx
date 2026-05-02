import ConfusionMatrix from '../ConfusionMatrix';
import { getConfusion } from './util';
import type { EvalRunDetail } from '../../../api/types';

interface CompareConfusionProps {
  runs: EvalRunDetail[];
}

export default function CompareConfusion({ runs }: CompareConfusionProps) {
  const matrices = runs.map((run) => ({ run, confusion: getConfusion(run) }));
  const haveAny = matrices.some((m) => m.confusion && Object.keys(m.confusion).length > 0);

  if (!haveAny) {
    return (
      <p className="rounded-md border border-dashed border-gray-200 bg-white p-6 text-center text-sm text-gray-400">
        No confusion data on these runs.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-[11px] text-gray-500">
        Each gold span contributes one cell (best-overlap pred, or
        <code className="mx-0.5 rounded bg-gray-100 px-0.5">&lt;MISSED&gt;</code>); predicted spans
        with no gold overlap aggregate under the
        <code className="mx-0.5 rounded bg-gray-100 px-0.5">&lt;SPURIOUS&gt;</code> row.
      </p>
      {matrices.map(({ run, confusion }) => (
        <div key={run.id} className="flex flex-col gap-2">
          <div className="flex items-baseline gap-3 text-xs">
            <span className="font-semibold text-gray-900">{run.pipeline_name}</span>
            <span className="text-gray-500">{run.dataset_source}</span>
            <span className="text-gray-400">{run.document_count} docs</span>
            <span className="text-gray-400">{new Date(run.created_at).toLocaleDateString()}</span>
          </div>
          {confusion && Object.keys(confusion).length > 0 ? (
            <ConfusionMatrix confusion={confusion} />
          ) : (
            <p className="rounded-md border border-dashed border-gray-200 bg-white p-3 text-xs text-gray-400">
              No confusion data on this run.
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
