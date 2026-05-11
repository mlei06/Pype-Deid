/**
 * Minimal types shared across the Playground and Production frontends.
 *
 * These mirror the per-app `api/types.ts` definitions for the fields that
 * shared utilities (entitySpanKey, traceConflicts, …) actually depend on.
 * Each consumer app keeps its own richer `api/types.ts` for app-specific
 * fields (e.g. surrogate_spans on the production response).
 */

export interface EntitySpanResponse {
  start: number;
  end: number;
  label: string;
  text: string;
  confidence: number | null;
  source: string | null;
}

export interface TraceFrame {
  path: string;
  stage: string;
  pipe_type: string;
  branch_index: number | null;
  extra: Record<string, unknown>;
  document?: {
    document: { id: string; text: string; metadata: Record<string, unknown> };
    spans: {
      start: number;
      end: number;
      label: string;
      confidence: number | null;
      source: string | null;
    }[];
  };
  elapsed_ms?: number;
}
