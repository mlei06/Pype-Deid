import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Play,
  Loader2,
  Plus,
  Database,
  Shuffle,
  PanelTop,
  ChevronDown,
  ChevronRight,
  Link2,
  Link2Off,
} from 'lucide-react';
import PipelineMultiSelector from './PipelineMultiSelector';
import PipelineColumn from './PipelineColumn';
import TraceColumn from './TraceColumn';
import CompareSummaryBar from './CompareSummaryBar';
import TextInput from './TextInput';
import ColorKeyPopover from '@shared/components/ColorKeyPopover';
import { useCompareInference } from '../../hooks/useCompareInference';
import { useSyncScroll } from '../../hooks/useSyncScroll';
import { useDatasets } from '../../hooks/useDatasets';
import { previewDataset, getDocument } from '../../api/datasets';

/** Read-only multi-pipeline comparison view. */
export default function InferenceView() {
  const [pipelines, setPipelines] = useState<string[]>([]);
  const [text, setText] = useState('');
  const [inputExpanded, setInputExpanded] = useState(true);
  const [hoveredRange, setHoveredRange] = useState<{ start: number; end: number } | null>(
    null,
  );
  const [collapsedTraces, setCollapsedTraces] = useState<Set<string>>(new Set());
  const [syncScroll, setSyncScroll] = useState(true);
  const [sampleDataset, setSampleDataset] = useState('');
  const [isSampling, setIsSampling] = useState(false);

  const { results, runAll, reset, isAnyPending } = useCompareInference();

  // One scroll-container ref per pipeline, kept in a ref-map so the array we
  // pass to useSyncScroll has a stable identity for the lifetime of each
  // pipeline. Recreating refs on every render would defeat the hook.
  const scrollRefMap = useRef(new Map<string, React.RefObject<HTMLDivElement | null>>());
  const scrollRefs = useMemo(() => {
    const map = scrollRefMap.current;
    for (const name of pipelines) {
      if (!map.has(name)) map.set(name, { current: null });
    }
    // Drop refs for pipelines that are no longer selected.
    for (const key of [...map.keys()]) {
      if (!pipelines.includes(key)) map.delete(key);
    }
    return pipelines.map((p) => map.get(p)!);
  }, [pipelines]);

  useSyncScroll(scrollRefs, syncScroll && pipelines.length > 1);

  const { data: datasets = [] } = useDatasets();

  const handleRun = () => {
    if (pipelines.length === 0 || !text.trim()) return;
    runAll(pipelines, text);
    setInputExpanded(false);
  };

  const handleClear = () => {
    setText('');
    reset();
    setInputExpanded(true);
  };

  const removePipeline = (name: string) => {
    setPipelines((prev) => prev.filter((p) => p !== name));
  };

  const toggleTraceCollapsed = (name: string) => {
    setCollapsedTraces((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const handleSampleFromDataset = async () => {
    const ds = datasets.find((d) => d.name === sampleDataset);
    if (!ds || ds.document_count === 0) return;
    setIsSampling(true);
    try {
      const offset = Math.floor(Math.random() * ds.document_count);
      const preview = await previewDataset(sampleDataset, { limit: 1, offset });
      if (preview.items.length === 0) return;
      const doc = await getDocument(sampleDataset, preview.items[0].document_id);
      setText(doc.text);
    } finally {
      setIsSampling(false);
    }
  };

  // Reset hovered range whenever the run changes — stale highlights from the
  // previous result would point at offsets that may no longer exist.
  useEffect(() => {
    setHoveredRange(null);
  }, [results]);

  const successResults = useMemo(
    () =>
      pipelines
        .map((name) => {
          const entry = results[name];
          if (entry?.status === 'success' && entry.result) {
            return { name, result: entry.result };
          }
          return null;
        })
        .filter((r): r is { name: string; result: NonNullable<typeof r>['result'] } => r != null),
    [pipelines, results],
  );

  const runDisabled = pipelines.length === 0 || !text.trim() || isAnyPending;
  const hasAnyResult = Object.keys(results).length > 0;

  // Tailwind needs literal class names, not interpolated indices.
  const docGridClass =
    pipelines.length >= 3
      ? 'grid-cols-3'
      : pipelines.length === 2
        ? 'grid-cols-2'
        : 'grid-cols-1';

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex shrink-0 flex-wrap items-end gap-2 border-b border-gray-200 bg-white px-3 py-2 shadow-sm">
        <PipelineMultiSelector selected={pipelines} onChange={setPipelines} max={3} />

        <button
          type="button"
          onClick={handleRun}
          disabled={runDisabled}
          className="flex shrink-0 items-center gap-1.5 rounded-md bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-40"
        >
          {isAnyPending ? (
            <Loader2 size={15} className="animate-spin" />
          ) : (
            <Play size={15} />
          )}
          Run
          {pipelines.length > 1 && (
            <span className="ml-1 rounded bg-white/15 px-1 text-[10px] font-semibold">
              ×{pipelines.length}
            </span>
          )}
        </button>

        <button
          type="button"
          onClick={() => setInputExpanded((e) => !e)}
          className="flex items-center gap-1 rounded-md border border-gray-200 bg-gray-50 px-2 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-100"
          title="Show or hide input text"
        >
          <PanelTop size={14} />
          Input
          {inputExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>

        <button
          type="button"
          onClick={handleClear}
          className="flex items-center gap-1 rounded-md border border-gray-200 bg-gray-50 px-2 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-100"
          title="Clear text and results"
        >
          <Plus size={14} />
          New
        </button>

        <div className="ml-auto flex items-center gap-2">
          <ColorKeyPopover />
          {pipelines.length > 1 && (
            <button
              type="button"
              onClick={() => setSyncScroll((v) => !v)}
              className={`flex items-center gap-1 rounded-md border px-2 py-1.5 text-xs font-medium ${
                syncScroll
                  ? 'border-gray-300 bg-gray-100 text-gray-800'
                  : 'border-gray-200 bg-white text-gray-500 hover:bg-gray-50'
              }`}
              title={syncScroll ? 'Sync scroll: on' : 'Sync scroll: off'}
            >
              {syncScroll ? <Link2 size={12} /> : <Link2Off size={12} />}
              Sync scroll
            </button>
          )}
        </div>
      </header>

      {inputExpanded && (
        <div className="shrink-0 border-b border-gray-100 bg-gray-50/50 px-3 py-2">
          <div className="mx-auto max-w-5xl">
            <div className="mb-1 text-xs font-medium text-gray-600">Input text</div>
            <TextInput value={text} onChange={setText} />
            {datasets.length > 0 && (
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <Database size={12} className="shrink-0 text-gray-400" />
                <span className="text-xs text-gray-400">Sample from dataset:</span>
                <select
                  className="rounded border border-gray-200 bg-white px-1.5 py-0.5 text-xs text-gray-700"
                  value={sampleDataset}
                  onChange={(e) => setSampleDataset(e.target.value)}
                >
                  <option value="">Choose dataset…</option>
                  {datasets.map((d) => (
                    <option key={d.name} value={d.name}>
                      {d.name} ({d.document_count} docs)
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={handleSampleFromDataset}
                  disabled={!sampleDataset || isSampling}
                  className="flex items-center gap-1 rounded border border-gray-200 bg-white px-2 py-0.5 text-xs text-gray-700 hover:bg-gray-50 disabled:opacity-40"
                >
                  {isSampling ? (
                    <Loader2 size={11} className="animate-spin" />
                  ) : (
                    <Shuffle size={11} />
                  )}
                  Sample
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {hasAnyResult && successResults.length >= 2 && (
        <CompareSummaryBar results={successResults} />
      )}

      {!hasAnyResult ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center text-sm text-gray-500">
          <p className="font-medium text-gray-700">No run yet</p>
          <p className="max-w-md text-xs text-gray-400">
            Pick 1–3 pipelines, paste text (or sample from a dataset), then Run. Each
            pipeline gets its own annotated-document and trace panel for side-by-side
            comparison.
          </p>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-hidden bg-gray-50 p-2">
          <div className={`grid min-h-0 flex-1 gap-2 ${docGridClass}`}>
            {pipelines.map((name) => (
              <PipelineColumn
                key={name}
                ref={scrollRefMap.current.get(name)}
                pipelineName={name}
                entry={results[name]}
                onRemove={pipelines.length > 1 ? () => removePipeline(name) : undefined}
                pulseRange={hoveredRange}
                onHoverRange={setHoveredRange}
              />
            ))}
          </div>
          <div className={`grid min-h-0 max-h-[45%] gap-2 ${docGridClass}`}>
            {pipelines.map((name) => (
              <TraceColumn
                key={name}
                pipelineName={name}
                entry={results[name]}
                collapsed={collapsedTraces.has(name)}
                onToggleCollapsed={() => toggleTraceCollapsed(name)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
