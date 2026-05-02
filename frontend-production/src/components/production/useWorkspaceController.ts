import { useEffect, useMemo, useState } from 'react';
import { useModes } from '../../hooks/useModes';
import { useBatchDetect } from './useBatchDetect';
import { useActiveDataset, useProductionStore } from './store';
import { useConfirm } from '../shared/ConfirmDialog';
import type { ResolveStrategyId } from '../../lib/spanOverlapConflicts';

export function useWorkspaceController() {
  const reviewer = useProductionStore((s) => s.reviewer);
  const setDatasetDefaultMode = useProductionStore((s) => s.setDatasetDefaultMode);
  const setDatasetAutoResolveOverlaps = useProductionStore(
    (s) => s.setDatasetAutoResolveOverlaps,
  );
  const active = useActiveDataset();
  const { data: modesData } = useModes();
  const { run, cancel, running, progress } = useBatchDetect();
  const confirm = useConfirm();

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [runTarget, setRunTarget] = useState('');
  const [saveAsDefault, setSaveAsDefault] = useState(false);

  useEffect(() => {
    setSelectedIds(new Set());
  }, [active?.id]);

  useEffect(() => {
    if (!active) return;
    if (active.defaultDetectionMode) {
      setRunTarget(active.defaultDetectionMode);
      return;
    }
    if (modesData?.default_mode) {
      const def = modesData.modes.find((m) => m.name === modesData.default_mode);
      if (def?.available) setRunTarget(modesData.default_mode);
    }
  }, [active?.id, active?.defaultDetectionMode, modesData]);

  const modes = modesData?.modes ?? [];
  const selectedMode = useMemo(
    () => modes.find((m) => m.name === runTarget) ?? null,
    [modes, runTarget],
  );
  const targetResolvable = Boolean(runTarget) && (!selectedMode || selectedMode.available);

  const currentFile = useMemo(() => {
    if (!active) return null;
    return active.files.find((f) => f.id === active.currentFileId) ?? null;
  }, [active]);

  const toggleSelected = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAllVisible = (visibleIds: string[]) => {
    setSelectedIds((prev) => {
      if (visibleIds.length === 0) return prev;
      const allVisibleSelected = visibleIds.every((id) => prev.has(id));
      if (allVisibleSelected) {
        const next = new Set(prev);
        for (const id of visibleIds) next.delete(id);
        return next;
      }
      const next = new Set(prev);
      for (const id of visibleIds) next.add(id);
      return next;
    });
  };

  const handleRun = async () => {
    if (!active || !runTarget) return;
    let ids = Array.from(selectedIds);
    if (ids.length === 0 && currentFile) ids = [currentFile.id];
    if (ids.length === 0) return;

    const resolvedInSelection = active.files.filter((f) => ids.includes(f.id) && f.resolved);
    if (resolvedInSelection.length > 0) {
      const ok = await confirm({
        title: 'Re-run detection on resolved files?',
        message: `${resolvedInSelection.length} resolved file${
          resolvedInSelection.length === 1 ? '' : 's'
        } in the selection. Re-running will replace annotations and clear the resolved flag.`,
        confirmLabel: 'Re-run',
        danger: true,
      });
      if (!ok) return;
    }

    if (saveAsDefault && runTarget !== active.defaultDetectionMode) {
      setDatasetDefaultMode(active.id, runTarget);
    }

    await run({
      datasetId: active.id,
      fileIds: ids,
      target: runTarget,
      reviewer: reviewer || 'production-ui',
      clearResolved: true,
    });
  };

  const selectionCount = selectedIds.size;
  const runButtonLabel =
    selectionCount === 0
      ? currentFile
        ? 'Run on current file'
        : 'Run detection'
      : `Run on ${selectionCount} selected`;

  const autoResolveSetting = active?.autoResolveOverlaps;
  const autoResolveEnabled = Boolean(autoResolveSetting?.enabled);
  const autoResolveStrategy: ResolveStrategyId =
    autoResolveSetting?.strategy ?? 'label_priority';

  const setAutoResolveEnabled = (enabled: boolean) => {
    if (!active) return;
    setDatasetAutoResolveOverlaps(active.id, {
      enabled,
      strategy: autoResolveStrategy,
    });
  };

  const setAutoResolveStrategy = (strategy: ResolveStrategyId) => {
    if (!active) return;
    setDatasetAutoResolveOverlaps(active.id, {
      enabled: autoResolveEnabled,
      strategy,
    });
  };

  return {
    active,
    reviewer,
    modes,
    runTarget,
    setRunTarget,
    saveAsDefault,
    setSaveAsDefault,
    selectedMode,
    targetResolvable,
    currentFile,
    selectedIds,
    selectionCount,
    runButtonLabel,
    running,
    progress,
    toggleSelected,
    toggleSelectAllVisible,
    handleRun,
    cancel,
    autoResolveEnabled,
    autoResolveStrategy,
    setAutoResolveEnabled,
    setAutoResolveStrategy,
  };
}
