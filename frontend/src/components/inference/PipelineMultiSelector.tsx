import { useState, useRef, useEffect } from 'react';
import { Plus, X, ChevronDown } from 'lucide-react';
import { usePipelines } from '../../hooks/usePipelines';

interface PipelineMultiSelectorProps {
  selected: string[];
  onChange: (names: string[]) => void;
  max?: number;
}

export default function PipelineMultiSelector({
  selected,
  onChange,
  max = 3,
}: PipelineMultiSelectorProps) {
  const { data: pipelines = [], isLoading } = usePipelines();
  const [open, setOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (popoverRef.current?.contains(e.target as Node)) return;
      setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  const atMax = selected.length >= max;
  const available = pipelines.filter((p) => !selected.includes(p.name));

  const remove = (name: string) => onChange(selected.filter((n) => n !== name));
  const add = (name: string) => {
    if (selected.includes(name) || atMax) return;
    onChange([...selected, name]);
    setOpen(false);
  };
  const replaceAt = (idx: number, name: string) => {
    if (selected[idx] === name) return;
    if (selected.includes(name)) return;
    const next = [...selected];
    next[idx] = name;
    onChange(next);
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {selected.length === 0 && (
        <div className="flex items-center gap-1 rounded-md border border-gray-200 bg-gray-50 px-1.5 py-1">
          <span className="text-[10px] font-medium text-gray-500">Pipeline</span>
          <select
            value=""
            disabled={isLoading}
            onChange={(e) => {
              if (e.target.value) add(e.target.value);
            }}
            className="rounded border border-gray-300 bg-white px-2 py-1 text-sm text-gray-900"
          >
            <option value="">{isLoading ? 'Loading…' : 'Choose pipeline'}</option>
            {pipelines.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {selected.map((name, idx) => (
        <div
          key={`${name}-${idx}`}
          className="flex items-center gap-1 rounded-md border border-gray-200 bg-gray-50 px-1.5 py-1"
        >
          <span className="text-[10px] font-medium text-gray-500">
            {selected.length > 1 ? `Pipeline ${idx + 1}` : 'Pipeline'}
          </span>
          <select
            value={name}
            onChange={(e) => replaceAt(idx, e.target.value)}
            className="rounded border border-gray-300 bg-white px-2 py-1 text-sm text-gray-900"
          >
            <option value={name}>{name}</option>
            {pipelines
              .filter((p) => p.name !== name && !selected.includes(p.name))
              .map((p) => (
                <option key={p.name} value={p.name}>
                  {p.name}
                </option>
              ))}
          </select>
          {selected.length > 1 && (
            <button
              type="button"
              onClick={() => remove(name)}
              title="Remove this pipeline"
              className="rounded p-0.5 text-gray-400 hover:bg-gray-200 hover:text-gray-700"
            >
              <X size={12} />
            </button>
          )}
        </div>
      ))}

      {selected.length > 0 && !atMax && (
        <div className="relative" ref={popoverRef}>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            disabled={available.length === 0}
            className="flex items-center gap-1 rounded-md border border-dashed border-gray-300 bg-white px-2 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-40"
            title={
              available.length === 0
                ? 'All pipelines added'
                : `Add another pipeline (up to ${max})`
            }
          >
            <Plus size={12} />
            Add pipeline
            <ChevronDown size={12} />
          </button>
          {open && available.length > 0 && (
            <div
              role="menu"
              className="absolute left-0 top-full z-30 mt-1 max-h-72 min-w-[200px] overflow-y-auto rounded-md border border-gray-200 bg-white py-1 shadow-lg"
            >
              {available.map((p) => (
                <button
                  key={p.name}
                  type="button"
                  role="menuitem"
                  onClick={() => add(p.name)}
                  className="block w-full px-3 py-1.5 text-left text-sm text-gray-800 hover:bg-gray-50"
                >
                  {p.name}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      {atMax && (
        <span className="text-[10px] text-gray-400">{max} max</span>
      )}
    </div>
  );
}
