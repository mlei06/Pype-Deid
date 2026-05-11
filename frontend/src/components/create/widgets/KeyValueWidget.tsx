import { Plus, X, Loader2 } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { FieldProps } from '@rjsf/utils';
import { fetchPrefixLabelSpace } from '../../../api/pipelines';
import { labelColor } from '@shared/lib/labelColors';
import type { SchemaFormContext } from '../schemaFormContext';

/**
 * Key-value map editor for dict[str, str | None] fields.
 * Registered as an rjsf custom **field** (not widget) because
 * `ui:widget` is ignored on `type: "object"` schemas.
 */
export default function KeyValueField(props: FieldProps) {
  const { formData, onChange, schema, name, fieldPathId, formContext: rawContext } = props;
  const data: Record<string, string | null> = formData ?? {};
  const entries: [string, string | null][] = Object.entries(data);
  const [newKey, setNewKey] = useState('');
  const [newVal, setNewVal] = useState('');

  const formContext = rawContext as SchemaFormContext | undefined;
  const isLabelMapperMapping =
    formContext?.pipeType === 'label_mapper' && name === 'mapping';
  const pipeIndex = formContext?.selectedPipeOrderIndex;
  const fullCfg = formContext?.fullPipelineConfig;
  const prefixFingerprint = useMemo(
    () => (fullCfg ? JSON.stringify(fullCfg.pipes) : ''),
    [fullCfg],
  );

  const prefixQuery = useQuery({
    queryKey: ['prefix-label-space', pipeIndex, prefixFingerprint],
    queryFn: () => fetchPrefixLabelSpace(fullCfg!, pipeIndex!),
    enabled: isLabelMapperMapping && fullCfg != null && pipeIndex != null,
    staleTime: 15_000,
  });

  /**
   * When the mapping is still empty, pre-fill the left column (and identity targets) from the
   * symbolic upstream label set. `seededForEmptyKeyRef` avoids duplicate onChange in Strict Mode;
   * it is cleared whenever the user has any keys so a later “clear all” can trigger a fresh fill.
   */
  const seededForEmptyKeyRef = useRef<string | null>(null);
  useEffect(() => {
    if (Object.keys(data).length > 0) {
      seededForEmptyKeyRef.current = null;
      return;
    }
    if (!isLabelMapperMapping) return;
    if (!prefixQuery.isSuccess) return;
    if (prefixQuery.data?.error) return;
    const labels = prefixQuery.data?.labels;
    if (!labels?.length) return;
    const seedKey = [
      formContext?.selectedNodeId ?? '',
      pipeIndex ?? -1,
      prefixFingerprint,
      labels.join('\0'),
    ].join('|');
    if (seededForEmptyKeyRef.current === seedKey) return;
    const next = Object.fromEntries(labels.map((l) => [l, l])) as Record<string, string | null>;
    if (
      Object.keys(data).length === Object.keys(next).length &&
      Object.keys(next).every((k) => (data as Record<string, string | null>)[k] === next[k])
    ) {
      return;
    }
    seededForEmptyKeyRef.current = seedKey;
    onChange(
      Object.keys(next).length > 0 ? next : undefined,
      fieldPathId.path,
    );
  }, [
    isLabelMapperMapping,
    data,
    prefixQuery.isSuccess,
    prefixQuery.data,
    formContext?.selectedNodeId,
    pipeIndex,
    prefixFingerprint,
    fieldPathId.path,
    onChange,
  ]);

  const allowNullValues =
    schema.additionalProperties &&
    typeof schema.additionalProperties === 'object' &&
    'anyOf' in (schema.additionalProperties as Record<string, unknown>);

  const update = (updated: Record<string, string | null>) => {
    onChange(Object.keys(updated).length > 0 ? updated : undefined, fieldPathId.path);
  };

  const addIdentityForMissingUpstream = () => {
    const src = prefixQuery.data?.labels;
    if (!src?.length) return;
    const next = { ...data };
    for (const lb of src) {
      if (next[lb] === undefined) {
        next[lb] = lb;
      }
    }
    update(next);
  };

  const addEntry = () => {
    const k = newKey.trim();
    if (!k) return;
    update({ ...data, [k]: newVal || null });
    setNewKey('');
    setNewVal('');
  };

  const removeEntry = (key: string) => {
    const copy = { ...data };
    delete copy[key];
    update(copy);
  };

  const updateKey = (oldKey: string, newKeyName: string) => {
    const copy: Record<string, string | null> = {};
    for (const [k, v] of entries) {
      copy[k === oldKey ? newKeyName : k] = v;
    }
    update(copy);
  };

  const updateValue = (key: string, val: string) => {
    update({ ...data, [key]: val || (allowNullValues ? null : '') });
  };

  const title = (schema as Record<string, unknown>).title as string | undefined;
  const help = (schema as Record<string, unknown>).ui_help as string | undefined;
  const description = schema.description as string | undefined;

  return (
    <div className="mb-3 space-y-2">
      {(title || name) && (
        <label className="mb-1 block text-xs font-medium text-gray-600">
          {title || name}
        </label>
      )}
      {description && (
        <p className="text-xs text-gray-400">{description}</p>
      )}

      {isLabelMapperMapping && (
        <div className="mb-2 rounded border border-slate-200 bg-slate-50/80 px-2 py-2">
          <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-slate-500">
            Upstream label space (symbolic)
          </div>
          {prefixQuery.isLoading && (
            <div className="flex items-center gap-1.5 text-xs text-slate-500">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Computing…
            </div>
          )}
          {prefixQuery.data?.error && (
            <p className="text-xs text-amber-700">{prefixQuery.data.error}</p>
          )}
          {!prefixQuery.isLoading && !prefixQuery.data?.error && (prefixQuery.data?.labels?.length ?? 0) === 0 && (
            <p className="text-xs text-slate-500">No upstream pipes — map labels after detectors run.</p>
          )}
          {!prefixQuery.isLoading && (prefixQuery.data?.labels?.length ?? 0) > 0 && (
            <>
              <p className="mb-1.5 text-[11px] text-slate-600">
                Empty mappings get one row per upstream label (identity) when this list loads. Use the
                button below to add any new labels without wiping existing rows.
              </p>
              <div className="mb-2 flex flex-wrap gap-1">
                {prefixQuery.data!.labels.map((lb) => {
                  const c = labelColor(lb);
                  return (
                    <span
                      key={lb}
                      className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium"
                      style={{ backgroundColor: c.bg, color: c.text }}
                    >
                      {lb}
                    </span>
                  );
                })}
              </div>
              <button
                type="button"
                onClick={addIdentityForMissingUpstream}
                className="rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 hover:bg-slate-100"
              >
                Add identity mappings for missing sources
              </button>
            </>
          )}
        </div>
      )}

      {entries.length > 0 && (
        <div className="space-y-1.5">
          {entries.map(([k, v], i) => (
            <div key={i} className="flex items-center gap-1.5">
              <input
                className="w-1/3 rounded border border-gray-300 px-2 py-1 text-sm"
                value={k}
                onChange={(e) => updateKey(k, e.target.value)}
                placeholder="Label"
              />
              <span className="text-xs text-gray-400">&rarr;</span>
              <input
                className="flex-1 rounded border border-gray-300 px-2 py-1 text-sm"
                value={v ?? ''}
                onChange={(e) => updateValue(k, e.target.value)}
                placeholder={allowNullValues ? '(null = drop)' : 'Value'}
              />
              <button
                type="button"
                onClick={() => removeEntry(k)}
                className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-500"
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center gap-1.5">
        <input
          className="w-1/3 rounded border border-gray-300 px-2 py-1 text-sm"
          value={newKey}
          onChange={(e) => setNewKey(e.target.value)}
          placeholder="New key"
          onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addEntry())}
        />
        <span className="text-xs text-gray-400">&rarr;</span>
        <input
          className="flex-1 rounded border border-gray-300 px-2 py-1 text-sm"
          value={newVal}
          onChange={(e) => setNewVal(e.target.value)}
          placeholder="New value"
          onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addEntry())}
        />
        <button
          type="button"
          onClick={addEntry}
          className="rounded p-1 text-gray-500 hover:bg-blue-50 hover:text-blue-600"
        >
          <Plus size={14} />
        </button>
      </div>

      {help && (
        <p className="text-xs text-gray-400">{help}</p>
      )}
    </div>
  );
}
