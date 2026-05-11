import { Plus, X, ArrowRight, ChevronDown, ChevronRight, Loader2 } from 'lucide-react';
import { useState, useCallback } from 'react';
import type { FieldProps } from '@rjsf/utils';
import { labelColor } from '@shared/lib/labelColors';
import { useLabelSpace } from '../../../hooks/useLabelSpace';
import { usePipeFormContextConfig } from '../../../hooks/usePipeFormContextConfig';
import type { SchemaFormContext } from '../schemaFormContext';
import CanonicalLabelSelect from './CanonicalLabelSelect';

interface LabelSettings {
  enabled: boolean;
  remap: string | null;
  custom_pattern: string | null;
}

const DEFAULT_SETTINGS: LabelSettings = {
  enabled: true,
  remap: null,
  custom_pattern: null,
};

/**
 * Unified label configuration field for regex_ner.
 *
 * Each label from the detector's label space is shown once with:
 *  - Toggle switch (enabled / disabled)
 *  - Label badge
 *  - Optional remap text field
 *  - Expandable section: built-in regex pattern (read-only) + custom override
 *
 * Bound to ``labels: dict[str, RegexLabelSettings]``.  Reads
 * ``ui_base_labels``, ``ui_pipe_type``, and ``ui_builtin_patterns`` from
 * schema annotations injected by the API.
 */
export default function UnifiedLabelField(props: FieldProps) {
  const { formData, onChange, schema, formContext, fieldPathId } = props;
  const labels: Record<string, LabelSettings> = formData ?? {};

  const schemaAny = schema as Record<string, unknown>;
  const pipeType: string =
    (schemaAny.ui_pipe_type as string) || formContext?.pipeType || '';
  const baseLabels: string[] =
    (schemaAny.ui_base_labels as string[]) || formContext?.baseLabels || [];
  const builtinPatterns: Record<string, string> =
    (schemaAny.ui_builtin_patterns as Record<string, string>) || {};
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

  const getSettings = useCallback(
    (label: string): LabelSettings => labels[label] ?? DEFAULT_SETTINGS,
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
          (v.custom_pattern !== null && v.custom_pattern !== '');
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

  const setCustomPattern = (label: string, value: string) => {
    patchLabel(label, { custom_pattern: value || null });
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
    patchLabel(trimmed, { enabled: true, remap: null, custom_pattern: null });
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
            const hasBuiltin = label in builtinPatterns;
            const hasCustomPattern = !!s.custom_pattern;
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
                  {hasCustomPattern && (
                    <span className="text-[10px] text-blue-500">custom regex</span>
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

                  {/* Expand toggle for regex section */}
                  {s.enabled && (hasBuiltin || hasCustomPattern || isCustom) && (
                    <button
                      type="button"
                      onClick={() => toggleExpanded(label)}
                      className="shrink-0 rounded p-0.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                      title={isOpen ? 'Hide patterns' : 'Show patterns'}
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

                {/* Expanded regex section */}
                {s.enabled && isOpen && (
                  <div className="space-y-1.5 border-t border-gray-100 px-2 py-2">
                    {/* Built-in pattern (read-only) */}
                    {hasBuiltin && (
                      <div>
                        <div className="mb-0.5 text-[10px] font-medium text-gray-400">
                          Built-in pattern
                        </div>
                        <div className="max-h-20 overflow-auto rounded border border-gray-100 bg-gray-50 px-1.5 py-1 font-mono text-[10px] leading-relaxed text-gray-500">
                          {builtinPatterns[label]}
                        </div>
                      </div>
                    )}

                    {/* Custom pattern */}
                    <div>
                      <div className="mb-0.5 text-[10px] font-medium text-gray-400">
                        Custom pattern {hasBuiltin ? '(overrides built-in)' : ''}
                      </div>
                      <input
                        type="text"
                        className="w-full rounded border border-gray-200 bg-white px-1.5 py-1 font-mono text-xs text-gray-700 placeholder:text-gray-300 focus:border-blue-300 focus:outline-none"
                        value={s.custom_pattern ?? ''}
                        onChange={(e) => setCustomPattern(label, e.target.value)}
                        placeholder={
                          hasBuiltin
                            ? 'leave empty to use built-in…'
                            : 'regex pattern…'
                        }
                      />
                    </div>
                  </div>
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
            placeholder="Add custom label…"
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
