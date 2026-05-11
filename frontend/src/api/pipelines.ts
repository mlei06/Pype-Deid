import { apiFetch } from './client';
import type {
  CreatePipelineRequest,
  PipelineConfig,
  PipelineDetail,
  PipeTypeInfo,
  ValidatePipelineResponse,
} from './types';

export interface PrefixLabelSpaceResponse {
  labels: string[];
  error: string | null;
}

export function listPipelines(): Promise<PipelineDetail[]> {
  return apiFetch('/pipelines');
}

export function getPipeline(name: string): Promise<PipelineDetail> {
  return apiFetch(`/pipelines/${encodeURIComponent(name)}`);
}

export function createPipeline(req: CreatePipelineRequest): Promise<PipelineDetail> {
  return apiFetch('/pipelines', { method: 'POST', body: JSON.stringify(req) });
}

export function updatePipeline(name: string, config: PipelineConfig): Promise<PipelineDetail> {
  return apiFetch(`/pipelines/${encodeURIComponent(name)}`, {
    method: 'PUT',
    body: JSON.stringify({ config }),
  });
}

export function deletePipeline(name: string): Promise<void> {
  return apiFetch(`/pipelines/${encodeURIComponent(name)}`, { method: 'DELETE' });
}

export function renamePipeline(
  name: string,
  newName: string,
): Promise<PipelineDetail> {
  return apiFetch(`/pipelines/${encodeURIComponent(name)}/rename`, {
    method: 'POST',
    body: JSON.stringify({ new_name: newName }),
  });
}

export function validatePipeline(
  name: string,
  config?: PipelineConfig,
): Promise<ValidatePipelineResponse> {
  return apiFetch(`/pipelines/${encodeURIComponent(name)}/validate`, {
    method: 'POST',
    body: JSON.stringify(config ? { config } : {}),
  });
}

export function listPipeTypes(): Promise<PipeTypeInfo[]> {
  return apiFetch('/pipelines/pipe-types');
}

export interface ComputePipeLabelsResponse {
  labels: string[];
}

export function computePipeLabels(
  name: string,
  config?: Record<string, unknown>,
): Promise<ComputePipeLabelsResponse> {
  return apiFetch(`/pipelines/pipe-types/${encodeURIComponent(name)}/labels`, {
    method: 'POST',
    body: JSON.stringify({ config: config ?? null }),
  });
}

/** Per-model label keys + default ``entity_map`` for any detector with ``label_source: 'bundle'``.
 * Key shape (raw NER tag vs. Presidio entity) is signaled by ``PipeTypeInfo.bundle_key_semantics``.
 */
export interface ModelInfo {
  trained_max_length?: number | null;
  max_position_embeddings?: number | null;
  segmentation?: string | null;
  base_model?: string | null;
  train_documents?: number | null;
  trained_at?: string | null;
  [key: string]: unknown;
}

export interface LabelSpaceBundle {
  labels_by_model: Record<string, string[]>;
  default_entity_map: Record<string, string>;
  /** Per-model raw→canonical label maps from each model's manifest. Preferred over the legacy global ``default_entity_map`` when present for the selected model. */
  entity_maps_by_model?: Record<string, Record<string, string>>;
  default_model: string;
  /** Optional per-model display metadata (e.g. trained max length). Empty for pipes that don't expose it. */
  model_info?: Record<string, ModelInfo>;
}

export function fetchLabelSpaceBundle(pipeType: string): Promise<LabelSpaceBundle> {
  return apiFetch(`/pipelines/pipe-types/${encodeURIComponent(pipeType)}/label-space-bundle`);
}

export interface PipeReadiness {
  installed: boolean;
  ok: boolean;
  missing: string[];
  ready_details: Record<string, unknown> | null;
  install_hint: string | null;
}

export function fetchPipeReadiness(
  pipeType: string,
  config?: Record<string, unknown>,
): Promise<PipeReadiness> {
  return apiFetch(`/pipelines/pipe-types/${encodeURIComponent(pipeType)}/readiness`, {
    method: 'POST',
    body: JSON.stringify({ config: config ?? null }),
  });
}

/** Symbolic labels entering the pipe at *stepIndex* (``label_mapper`` UI). */
export function fetchPrefixLabelSpace(
  config: PipelineConfig,
  stepIndex: number,
): Promise<PrefixLabelSpaceResponse> {
  return apiFetch('/pipelines/prefix-label-space', {
    method: 'POST',
    body: JSON.stringify({ config, step_index: stepIndex }),
  });
}
