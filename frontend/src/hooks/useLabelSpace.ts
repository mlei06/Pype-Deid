import { useQuery } from '@tanstack/react-query';
import { useCallback, useMemo } from 'react';
import { usePipelineEditorStore } from '../stores/pipelineEditorStore';
import { computePipeLabels, fetchLabelSpaceBundle } from '../api/pipelines';
import { usePipeTypes } from './usePipeTypes';
import { usePipeEditorNodeId } from '../components/create/PipeEditorNodeContext';
import type { LabelSpaceBundle } from '../api/pipelines';
import type { PipeTypeInfo } from '../api/types';

/**
 * Fetches the dynamic label space for a detector pipe.
 *
 * Strategy is driven by ``PipeTypeInfo.label_source`` from the catalog:
 *   - ``bundle`` — one GET per session; switching ``model`` / editing ``entity_map``
 *     recomputes client-side from the cached bundle.
 *   - ``compute`` — POST ``/pipe-types/{name}/labels`` with the current config.
 *   - ``none``   — return ``baseLabels`` as-is.
 *
 * Bundle key shape (raw NER tag vs. Presidio entity name) is read from
 * ``PipeTypeInfo.bundle_key_semantics``; both follow the same merge rule:
 * ``effective_map[key] ?? key``.
 */
export type UseLabelSpaceOptions = {
  /** Selected node id — enables store-backed reads so model/entity_map updates trigger refetch. */
  selectedNodeId?: string;
};

function selectPipeTypeInfo(pipeTypes: PipeTypeInfo[] | undefined, name: string): PipeTypeInfo | undefined {
  return pipeTypes?.find((p) => p.name === name);
}

function bundleLabels(bundle: LabelSpaceBundle, model: string, entityMap: Record<string, string>): string[] {
  const keys = bundle.labels_by_model[model] ?? [];
  const perModelDefault = bundle.entity_maps_by_model?.[model];
  const baseDefault = perModelDefault ?? bundle.default_entity_map;
  const effective = { ...baseDefault, ...entityMap };
  const set = new Set<string>();
  for (const k of keys) set.add(effective[k] ?? k);
  return [...set].sort();
}

export function useLabelSpace(
  pipeType: string,
  config: Record<string, unknown>,
  baseLabels: string[],
  _currentMapping: Record<string, unknown> | undefined,
  options?: UseLabelSpaceOptions,
) {
  const ctxNodeId = usePipeEditorNodeId();
  const selectedNodeId = options?.selectedNodeId ?? ctxNodeId;

  const { data: pipeTypes } = usePipeTypes();
  const info = selectPipeTypeInfo(pipeTypes, pipeType);
  const labelSource = info?.label_source ?? 'compute';
  const useBundle = labelSource === 'bundle' || labelSource === 'both';

  type StoreState = ReturnType<typeof usePipelineEditorStore.getState>;

  const selectModel = useCallback(
    (s: StoreState) => {
      if (!selectedNodeId) return undefined;
      const m = s.pipes.find((n) => n.id === selectedNodeId)?.data.config?.model;
      return typeof m === 'string' ? m : undefined;
    },
    [selectedNodeId],
  );

  const selectEntityMap = useCallback(
    (s: StoreState) => {
      if (!selectedNodeId) return undefined;
      const em = s.pipes.find((n) => n.id === selectedNodeId)?.data.config?.entity_map;
      return em && typeof em === 'object' && !Array.isArray(em)
        ? (em as Record<string, string>)
        : undefined;
    },
    [selectedNodeId],
  );

  const modelLive = usePipelineEditorStore(selectModel);
  const entityMapLive = usePipelineEditorStore(selectEntityMap);

  const configFingerprint = JSON.stringify(config);

  const configWithoutMapping = useMemo(() => {
    const { label_mapping: _, ...rest } = config;
    return rest;
  }, [configFingerprint, config]);

  /** Store-backed slice so POST /labels refetches even if RJSF hands widgets a stale ``config`` object. */
  const storeOverrideFingerprint = useMemo(() => {
    if (!selectedNodeId) return '';
    return [
      modelLive ?? '',
      entityMapLive ? JSON.stringify(entityMapLive) : '',
    ].join('|');
  }, [selectedNodeId, modelLive, entityMapLive]);

  const bundleQuery = useQuery({
    queryKey: ['label-space-bundle', pipeType],
    queryFn: () => fetchLabelSpaceBundle(pipeType),
    staleTime: 5 * 60_000,
    enabled: !!pipeType && useBundle,
  });

  const postLabels = useQuery({
    queryKey: ['pipe-labels', pipeType, configFingerprint, storeOverrideFingerprint],
    queryFn: () => computePipeLabels(pipeType, configWithoutMapping),
    staleTime: 30_000,
    enabled: !!pipeType && (labelSource === 'compute' || labelSource === 'both'),
  });

  const labels = useMemo(() => {
    if (useBundle && bundleQuery.data) {
      const bundle = bundleQuery.data;
      const modelName =
        modelLive ||
        (typeof config.model === 'string' && config.model) ||
        bundle.default_model;
      const userMap =
        entityMapLive ?? (config.entity_map as Record<string, string> | undefined) ?? {};
      return bundleLabels(bundle, modelName, userMap);
    }

    if (useBundle && bundleQuery.isLoading) {
      return [...baseLabels].sort();
    }

    // POST /labels returns the full base label space for the current pipe config (e.g. presidio
    // model). Do not union with catalog ``ui_base_labels`` — those defaults are a fixed snapshot
    // and would hide model switches.
    if (postLabels.data?.labels != null && postLabels.data.labels.length > 0) {
      return [...postLabels.data.labels].sort();
    }

    return [...baseLabels].sort();
  }, [
    baseLabels,
    useBundle,
    bundleQuery.data,
    bundleQuery.isLoading,
    postLabels.data,
    config.model,
    config.entity_map,
    modelLive,
    entityMapLive,
  ]);

  const isLoading = useBundle ? bundleQuery.isLoading : postLabels.isLoading;

  return { labels, isLoading };
}
