import {
  Plus,
  X,
  ArrowRight,
  ChevronDown,
  ChevronRight,
  Loader2,
  FileText,
  Upload,
} from 'lucide-react';
import { useState, useCallback, useRef } from 'react';
import type { FieldProps } from '@rjsf/utils';
import { labelColor } from '@shared/lib/labelColors';
import { useLabelSpace } from '../../../hooks/useLabelSpace';
import { usePipeFormContextConfig } from '../../../hooks/usePipeFormContextConfig';
import type { SchemaFormContext } from '../schemaFormContext';
import { uploadDictionary, listDictionaries } from '../../../api/dictionaries';
import type { DictionaryInfo } from '../../../api/types';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import CanonicalLabelSelect from './CanonicalLabelSelect';

interface LabelSettings {
  enabled: boolean;
  remap: string | null;
  terms: string[];
  disabled_dictionaries: string[];
}

const DEFAULT_SETTINGS: LabelSettings = {
  enabled: true,
  remap: null,
  terms: [],
  disabled_dictionaries: [],
};

interface DictInfo {
  name: string;
  filename: string;
  term_count: number;
}

/**
 * Unified label configuration field for whitelist pipe.
 *
 * Each label shows:
 *  - Toggle switch (enabled / disabled)
 *  - Label badge
 *  - Optional remap text field
 *  - Expandable section: dictionaries (checked by default, can disable) + inline terms + upload
 *
 * Bound to ``labels: dict[str, WhitelistLabelSettings]``.
 */
export default function WhitelistLabelField(props: FieldProps) {
  const { formData, onChange, schema, formContext, fieldPathId } = props;
  const labels: Record<string, LabelSettings> = formData ?? {};

  const schemaAny = schema as Record<string, unknown>;
  const pipeType: string =
    (schemaAny.ui_pipe_type as string) || formContext?.pipeType || '';
  const baseLabels: string[] =
    (schemaAny.ui_base_labels as string[]) || formContext?.baseLabels || [];
  const builtinDicts: Record<string, DictInfo[]> =
    (schemaAny.ui_dictionaries_by_label as Record<string, DictInfo[]>) || {};
  const config = usePipeFormContextConfig(formContext as SchemaFormContext | undefined);
  const allowCustomLabels = schemaAny.ui_allow_custom_labels !== false;

  const { labels: allLabels, isLoading } = useLabelSpace(
    pipeType,
    config,
    baseLabels,
    labels,
    { selectedNodeId: (formContext as SchemaFormContext | undefined)?.selectedNodeId },
  );

  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [newLabel, setNewLabel] = useState('');
  const { data: allWhitelistDicts = [] } = useQuery({
    queryKey: ['dictionaries', 'whitelist'],
    queryFn: () => listDictionaries('whitelist'),
  });

  const getSettings = useCallback(
    (label: string): LabelSettings => {
      const s = labels[label];
      if (!s) return DEFAULT_SETTINGS;
      return {
        enabled: s.enabled ?? true,
        remap: s.remap ?? null,
        terms: s.terms ?? [],
        disabled_dictionaries: s.disabled_dictionaries ?? [],
      };
    },
    [labels],
  );

  const update = useCallback(
    (next: Record<string, LabelSettings>) => {
      const cleaned: Record<string, LabelSettings> = {};
      for (const [k, v] of Object.entries(next)) {
        const isCustom = !allLabels.includes(k);
        const isDiff =
          v.enabled !== DEFAULT_SETTINGS.enabled ||
          (v.remap !== null && v.remap !== '') ||
          v.terms.length > 0 ||
          v.disabled_dictionaries.length > 0;
        if (isDiff || isCustom) cleaned[k] = v;
      }
      onChange(
        Object.keys(cleaned).length > 0 ? cleaned : undefined,
        fieldPathId.path,
      );
    },
    [onChange, fieldPathId, allLabels],
  );

  const patchLabel = useCallback(
    (label: string, patch: Partial<LabelSettings>) => {
      const prev = getSettings(label);
      update({ ...labels, [label]: { ...prev, ...patch } });
    },
    [labels, getSettings, update],
  );

  const toggleEnabled = (label: string) => {
    const prev = getSettings(label);
    patchLabel(label, { enabled: !prev.enabled });
  };

  const setRemap = (label: string, value: string) => {
    patchLabel(label, { remap: value || null });
  };

  const toggleExpanded = (label: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(label)) { next.delete(label); } else { next.add(label); }
      return next;
    });
  };

  const addCustomLabel = () => {
    const trimmed = newLabel.trim().toUpperCase();
    if (!trimmed || allLabels.includes(trimmed)) return;
    patchLabel(trimmed, {
      ...DEFAULT_SETTINGS,
      // New labels start with every dictionary disabled; user opts in by checking.
      disabled_dictionaries: allWhitelistDicts.map((d) => d.name),
    });
    setExpanded((prev) => new Set(prev).add(trimmed));
    setNewLabel('');
  };

  const removeCustomLabel = (label: string) => {
    const next = { ...labels };
    delete next[label];
    update(next);
    setExpanded((prev) => {
      const s = new Set(prev);
      s.delete(label);
      return s;
    });
  };

  const title = schemaAny.title as string | undefined;
  const description = schema.description as string | undefined;

  const customLabels = Object.keys(labels).filter((k) => !allLabels.includes(k));
  const displayLabels = [...allLabels, ...customLabels.sort()];

  return (
    <div className="mb-3 space-y-2">
      {title && (
        <div className="flex items-center gap-2">
          <label className="block text-xs font-medium text-gray-600">
            {title}
          </label>
          {isLoading && (
            <Loader2 size={12} className="animate-spin text-gray-400" />
          )}
        </div>
      )}
      {description && (
        <p className="text-xs text-gray-400">{description}</p>
      )}

      {displayLabels.length > 0 && (
        <div className="space-y-1">
          {displayLabels.map((label) => {
            const s = getSettings(label);
            const isOpen = expanded.has(label);
            const isCustom = !allLabels.includes(label);
            const color = labelColor(label);
            const totalDicts = builtinDicts[label]?.length ?? 0;
            const activeDicts = totalDicts - (s.disabled_dictionaries?.length ?? 0);
            const hasRemap = !!s.remap;

            return (
              <div
                key={label}
                className={`rounded-md border transition-colors ${
                  s.enabled
                    ? 'border-gray-200 bg-white'
                    : 'border-gray-100 bg-gray-50'
                }`}
              >
                {/* Main row */}
                <div className="flex items-center gap-1.5 px-2 py-1.5">
                  {/* Toggle */}
                  <button
                    type="button"
                    onClick={() => toggleEnabled(label)}
                    className={`relative h-4 w-7 shrink-0 rounded-full transition-colors ${
                      s.enabled ? 'bg-blue-500' : 'bg-gray-300'
                    }`}
                    title={s.enabled ? 'Disable this label' : 'Enable this label'}
                  >
                    <span
                      className={`absolute top-0.5 h-3 w-3 rounded-full bg-white shadow transition-transform ${
                        s.enabled ? 'left-3.5' : 'left-0.5'
                      }`}
                    />
                  </button>

                  {/* Label badge */}
                  <span
                    className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wide ${
                      s.enabled ? '' : 'opacity-40'
                    }`}
                    style={{
                      backgroundColor: color.bg,
                      color: color.text,
                      border: `1px solid ${color.border}`,
                    }}
                  >
                    {label}
                  </span>

                  {/* Status indicators */}
                  {totalDicts > 0 && (
                    <span className="text-[10px] text-blue-500">
                      {activeDicts}/{totalDicts} dict{totalDicts > 1 ? 's' : ''}
                    </span>
                  )}
                  {s.terms.length > 0 && (
                    <span className="text-[10px] text-emerald-500">
                      {s.terms.length} term{s.terms.length > 1 ? 's' : ''}
                    </span>
                  )}
                  {hasRemap && (
                    <span className="text-[10px] text-amber-500">remapped</span>
                  )}

                  {/* Remap to canonical label */}
                  {s.enabled && (
                    <>
                      <ArrowRight size={12} className="shrink-0 text-gray-300" />
                      <CanonicalLabelSelect
                        value={s.remap ?? ''}
                        onChange={(v) => setRemap(label, v)}
                        exclude={label}
                      />
                    </>
                  )}

                  {/* Expand toggle */}
                  {s.enabled && (
                    <button
                      type="button"
                      onClick={() => toggleExpanded(label)}
                      className="shrink-0 rounded p-0.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                      title={isOpen ? 'Hide details' : 'Show dictionaries & terms'}
                    >
                      {isOpen ? (
                        <ChevronDown size={12} />
                      ) : (
                        <ChevronRight size={12} />
                      )}
                    </button>
                  )}

                  {/* Remove button for custom labels */}
                  {isCustom && (
                    <button
                      type="button"
                      onClick={() => removeCustomLabel(label)}
                      className="shrink-0 rounded p-0.5 text-gray-400 hover:bg-red-50 hover:text-red-500"
                      title="Remove custom label"
                    >
                      <X size={12} />
                    </button>
                  )}
                </div>

                {/* Expanded section: dictionaries + terms + upload */}
                {s.enabled && isOpen && (
                  <LabelDetailPanel
                    label={label}
                    settings={s}
                    builtinDicts={builtinDicts[label] ?? []}
                    onPatch={(patch) => patchLabel(label, patch)}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}

      {displayLabels.length === 0 && !isLoading && (
        <p className="text-xs text-gray-400">No labels available.</p>
      )}

      {allowCustomLabels && (
        <div className="flex items-center gap-1.5">
          <input
            className="flex-1 rounded border border-gray-300 px-2 py-1 text-xs"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            placeholder="Add custom label..."
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                addCustomLabel();
              }
            }}
          />
          <button
            type="button"
            onClick={addCustomLabel}
            className="rounded p-1 text-gray-500 hover:bg-blue-50 hover:text-blue-600"
          >
            <Plus size={14} />
          </button>
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------
// Expanded panel: dictionaries (checked by default) + upload + inline terms
// --------------------------------------------------------------------------

function LabelDetailPanel({
  label,
  settings,
  builtinDicts,
  onPatch,
}: {
  label: string;
  settings: LabelSettings;
  builtinDicts: DictInfo[];
  onPatch: (patch: Partial<LabelSettings>) => void;
}) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [newTerm, setNewTerm] = useState('');

  const { data: liveDicts = [] } = useQuery({
    queryKey: ['dictionaries', 'whitelist', label],
    queryFn: () => listDictionaries('whitelist', label),
  });

  const allDicts: DictionaryInfo[] = liveDicts.length > 0
    ? liveDicts
    : builtinDicts.map((d) => ({
        kind: 'whitelist' as const,
        label,
        name: d.name,
        filename: d.filename,
        term_count: d.term_count,
      }));

  const disabled = new Set(settings.disabled_dictionaries ?? []);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadError('');
    try {
      const stem = file.name.replace(/\.[^.]+$/, '');
      await uploadDictionary(file, 'whitelist', stem, label);
      queryClient.invalidateQueries({ queryKey: ['dictionaries'] });
    } catch (err) {
      setUploadError((err as Error).message);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const toggleDict = (name: string) => {
    const next = disabled.has(name)
      ? settings.disabled_dictionaries.filter((n) => n !== name)
      : [...(settings.disabled_dictionaries ?? []), name];
    onPatch({ disabled_dictionaries: next });
  };

  const addTerm = () => {
    const trimmed = newTerm.trim();
    if (!trimmed || settings.terms.includes(trimmed)) return;
    onPatch({ terms: [...settings.terms, trimmed] });
    setNewTerm('');
  };

  const removeTerm = (term: string) => {
    onPatch({ terms: settings.terms.filter((t) => t !== term) });
  };

  return (
    <div className="space-y-3 border-t border-gray-100 px-2 py-2">
      {/* Dictionaries section */}
      <div>
        <div className="mb-1 flex items-center justify-between">
          <div className="text-[10px] font-medium text-gray-400">
            Dictionaries
          </div>
          <label className="flex cursor-pointer items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium text-blue-600 hover:bg-blue-50">
            {uploading ? (
              <Loader2 size={10} className="animate-spin" />
            ) : (
              <Upload size={10} />
            )}
            Upload
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,.csv,.json"
              className="hidden"
              onChange={handleUpload}
            />
          </label>
        </div>

        {uploadError && (
          <div className="mb-1 rounded border border-red-200 bg-red-50 px-2 py-1 text-[10px] text-red-600">
            {uploadError}
          </div>
        )}

        {allDicts.length === 0 ? (
          <div className="rounded border border-dashed border-gray-200 px-2 py-2 text-center text-[10px] text-gray-400">
            No dictionaries for this label. Upload one above.
          </div>
        ) : (
          <div className="space-y-0.5">
            {allDicts.map((d) => {
              const isEnabled = !disabled.has(d.name);
              return (
                <button
                  key={d.name}
                  type="button"
                  onClick={() => toggleDict(d.name)}
                  className={`flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-left transition-colors ${
                    isEnabled
                      ? 'bg-blue-50 text-blue-700'
                      : 'text-gray-400 hover:bg-gray-50'
                  }`}
                >
                  <div
                    className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded border text-[8px] ${
                      isEnabled
                        ? 'border-blue-600 bg-blue-600 text-white'
                        : 'border-gray-300'
                    }`}
                  >
                    {isEnabled && '\u2713'}
                  </div>
                  <FileText size={10} className={`shrink-0 ${isEnabled ? 'text-blue-400' : 'text-gray-300'}`} />
                  <span className={`min-w-0 flex-1 truncate text-[11px] ${isEnabled ? '' : 'line-through'}`}>
                    {d.name}
                  </span>
                  <span className={`shrink-0 text-[10px] ${isEnabled ? 'text-blue-400' : 'text-gray-300'}`}>
                    {d.term_count.toLocaleString()} terms
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Inline terms section */}
      <div>
        <div className="mb-1 text-[10px] font-medium text-gray-400">
          Inline Terms
        </div>

        {settings.terms.length > 0 && (
          <div className="mb-1.5 flex flex-wrap gap-1">
            {settings.terms.map((term) => (
              <span
                key={term}
                className="inline-flex items-center gap-0.5 rounded-full bg-gray-100 px-2 py-0.5 text-[10px] text-gray-700"
              >
                {term}
                <button
                  type="button"
                  onClick={() => removeTerm(term)}
                  className="rounded-full p-0.5 hover:bg-gray-200"
                >
                  <X size={8} />
                </button>
              </span>
            ))}
          </div>
        )}

        <div className="flex items-center gap-1">
          <input
            type="text"
            className="min-w-0 flex-1 rounded border border-gray-200 bg-white px-1.5 py-0.5 text-[11px] text-gray-700 placeholder:text-gray-300 focus:border-blue-300 focus:outline-none"
            value={newTerm}
            onChange={(e) => setNewTerm(e.target.value)}
            placeholder="Add term..."
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                addTerm();
              }
            }}
          />
          <button
            type="button"
            onClick={addTerm}
            className="rounded p-0.5 text-gray-400 hover:bg-blue-50 hover:text-blue-600"
          >
            <Plus size={12} />
          </button>
        </div>
      </div>
    </div>
  );
}
