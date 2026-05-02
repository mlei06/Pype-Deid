import { apiFetch } from './client';
import type { EvalRunRequest, EvalRunSummary, EvalRunDetail } from './types';

export function runEvaluation(req: EvalRunRequest): Promise<EvalRunDetail> {
  return apiFetch('/eval/run', { method: 'POST', body: JSON.stringify(req) });
}

export function listEvalRuns(params?: {
  pipeline_name?: string;
  limit?: number;
  offset?: number;
}): Promise<EvalRunSummary[]> {
  const qs = new URLSearchParams();
  if (params?.pipeline_name) qs.set('pipeline_name', params.pipeline_name);
  if (params?.limit) qs.set('limit', String(params.limit));
  if (params?.offset) qs.set('offset', String(params.offset));
  const q = qs.toString();
  return apiFetch(`/eval/runs${q ? `?${q}` : ''}`);
}

export function getEvalRun(id: string): Promise<EvalRunDetail> {
  return apiFetch(`/eval/runs/${encodeURIComponent(id)}`);
}
