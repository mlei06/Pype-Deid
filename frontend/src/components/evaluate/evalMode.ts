export type EvalMode = 'new' | 'results' | 'compare';

export const EVAL_MODES: EvalMode[] = ['new', 'results', 'compare'];

export function parseEvalMode(value: string | null | undefined): EvalMode {
  return EVAL_MODES.includes(value as EvalMode) ? (value as EvalMode) : 'new';
}

/** Parse the comma-separated `?runs=` URL param into a unique, ordered list. */
export function parseRunIds(value: string | null | undefined): string[] {
  if (!value) return [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of value.split(',')) {
    const id = raw.trim();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    out.push(id);
  }
  return out;
}

export function serializeRunIds(ids: readonly string[]): string | null {
  return ids.length === 0 ? null : ids.join(',');
}
