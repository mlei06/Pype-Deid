import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { clsx } from 'clsx';
import { BarChart3, Grid3x3, FileText, Shield } from 'lucide-react';
import MetricsCards from './MetricsCards';
import PerLabelTable from './PerLabelTable';
import ConfusionMatrix from './ConfusionMatrix';
import RedactionDashboard from './RedactionDashboard';
import EvalPerDocumentPanel from './EvalPerDocumentPanel';
import ResultsRibbon from './ResultsRibbon';
import type {
  EvalPerDocumentItem,
  EvalRunDetail,
  LabelMetricsDetail,
  MacroMetrics,
  MatchMetrics,
  RedactionMetrics,
} from '../../api/types';

interface EvalDashboardProps {
  run: EvalRunDetail;
}

type DashboardTab = 'overview' | 'confusion' | 'perdoc' | 'redaction';

function parseTab(value: string | null, allowed: DashboardTab[]): DashboardTab {
  return allowed.includes(value as DashboardTab) ? (value as DashboardTab) : allowed[0];
}

export default function EvalDashboard({ run }: EvalDashboardProps) {
  const metrics = run.metrics ?? {};
  const overall =
    metrics.overall && typeof metrics.overall === 'object'
      ? (metrics.overall as Record<string, MatchMetrics>)
      : {};
  const perLabel =
    metrics.per_label && typeof metrics.per_label === 'object'
      ? (metrics.per_label as Record<string, LabelMetricsDetail>)
      : ({} as Record<string, LabelMetricsDetail>);
  const riskWeightedRecall =
    (typeof metrics.risk_weighted_recall === 'number'
      ? metrics.risk_weighted_recall
      : run.risk_weighted_recall) ?? 0;
  const labelConfusion =
    metrics.label_confusion && typeof metrics.label_confusion === 'object'
      ? (metrics.label_confusion as Record<string, Record<string, number>>)
      : undefined;
  const macro =
    metrics.macro && typeof metrics.macro === 'object'
      ? (metrics.macro as MacroMetrics)
      : undefined;

  const hasOverallMetrics = Object.keys(overall).length > 0;
  const hasConfusion = !!labelConfusion && Object.keys(labelConfusion).length > 0;
  const perDocItems = Array.isArray(metrics.document_level)
    ? (metrics.document_level as EvalPerDocumentItem[])
    : undefined;
  const hasPerDoc = !!perDocItems && perDocItems.length > 0;
  const hasRedaction = !!metrics.has_redaction && !!metrics.redaction;
  const redaction = metrics.redaction as RedactionMetrics | undefined;

  const availableTabs = useMemo<DashboardTab[]>(() => {
    const tabs: DashboardTab[] = ['overview'];
    if (hasConfusion) tabs.push('confusion');
    if (hasPerDoc) tabs.push('perdoc');
    if (hasRedaction) tabs.push('redaction');
    return tabs;
  }, [hasConfusion, hasPerDoc, hasRedaction]);

  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = parseTab(searchParams.get('tab'), availableTabs);
  const setActiveTab = (next: DashboardTab) => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        params.set('tab', next);
        return params;
      },
      { replace: true },
    );
  };

  return (
    <div className="flex flex-col gap-4">
      <ResultsRibbon run={run} />

      <div className="flex w-fit overflow-hidden rounded-lg border border-gray-200 bg-white">
        <DashboardTabButton
          id="overview"
          activeTab={activeTab}
          onSelect={setActiveTab}
          label="Overview"
          icon={<BarChart3 size={14} />}
        />
        {hasConfusion && (
          <DashboardTabButton
            id="confusion"
            activeTab={activeTab}
            onSelect={setActiveTab}
            label="Confusion"
            icon={<Grid3x3 size={14} />}
          />
        )}
        {hasPerDoc && (
          <DashboardTabButton
            id="perdoc"
            activeTab={activeTab}
            onSelect={setActiveTab}
            label="Per-document"
            icon={<FileText size={14} />}
          />
        )}
        {hasRedaction && (
          <DashboardTabButton
            id="redaction"
            activeTab={activeTab}
            onSelect={setActiveTab}
            label="Redaction"
            icon={<Shield size={14} />}
          />
        )}
      </div>

      {activeTab === 'overview' && (
        <div className="flex flex-col gap-4">
          {!hasOverallMetrics && (
            <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              No overall metrics in this run file (older or incomplete format). Summary scores may
              still appear in the list view.
            </div>
          )}
          <MetricsCards
            metrics={overall}
            riskWeightedRecall={riskWeightedRecall}
            macro={macro}
          />
          <PerLabelTable perLabel={perLabel} />
        </div>
      )}

      {activeTab === 'confusion' && labelConfusion && (
        <ConfusionMatrix confusion={labelConfusion} />
      )}

      {activeTab === 'perdoc' && perDocItems && (
        <EvalPerDocumentPanel
          items={perDocItems}
          truncated={!!metrics.document_level_truncated}
          total={metrics.document_level_total ?? perDocItems.length}
          includesSpans={!!metrics.document_level_includes_spans}
        />
      )}

      {activeTab === 'redaction' && redaction && <RedactionDashboard redaction={redaction} />}
    </div>
  );
}

function DashboardTabButton({
  id,
  activeTab,
  onSelect,
  label,
  icon,
}: {
  id: DashboardTab;
  activeTab: DashboardTab;
  onSelect: (tab: DashboardTab) => void;
  label: string;
  icon: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(id)}
      className={clsx(
        'flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-colors',
        activeTab === id ? 'bg-gray-900 text-white' : 'text-gray-600 hover:bg-gray-50',
      )}
    >
      {icon}
      {label}
    </button>
  );
}
