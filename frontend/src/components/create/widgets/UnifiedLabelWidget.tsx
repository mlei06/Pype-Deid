import { Plus, X, ChevronDown, ChevronRight, ArrowRight, Loader2 } from 'lucide-react';
import { useState } from 'react';
import type { FieldProps } from '@rjsf/utils';
import { labelColor } from '@shared/lib/labelColors';
import { useLabelSpace } from '../../../hooks/useLabelSpace';
import { usePipeFormContextConfig } from '../../../hooks/usePipeFormContextConfig';
import type { SchemaFormContext } from '../schemaFormContext';

/**
 * Unified per-label configuration for detector pipes.
 *
 * Renders each label **once** with:
 * - Toggle on/off (writes to `label_mapping[label] = null` to disable)
 * - Expandable section showing the regex pattern (custom override or built-in)
 * - Optional label remapping field
 *
 * This widget is bound to the `patterns` field. It reads and writes
 * `label_mapping` through `formContext.onConfigChange`.
 */
export default function UnifiedLabelField(props: FieldProps) {
  const { formData, onChange, schema, formContext, fieldPathId } = props;
  const patterns: Record<string, string> = formData ?? {};

  const schemaAny = schema as Record<string, unknown>;
  const pipeType: string =
    (schemaAny.ui_pipe_type as string) || formContext?.pipeType || '';
  const baseLabels: string[] =
    (schemaAny.ui_base_labels as string[]) || formContext?.baseLabels || [];
  const config = usePipeFormContextConfig(formContext as SchemaFormContext | undefined);
  const onConfigChange: ((c: Record<string, unknown>) => void) | undefined =
    (formContext as Record<string, unknown> | undefined)?.onConfigChange as
      | ((c: Record<string, unknown>) => void)
      | undefined;

  const labelMapping: Record<string, string | null> =
    (config.label_mapping as Record<string, string | null>) ?? {};

  const { labels: allLabels, isLoading } = useLabelSpace(
    pipeType,
    config,
    baseLabels,
    patterns,
    { selectedNodeId: (formContext as SchemaFormContext | undefined)?.selectedNodeId },
  );

  const [newLabel, setNewLabel] = useState('');
  const [expandedLabels, setExpandedLabels] = useState<Set<string>>(new Set());

  // --- helpers ---

  const isEnabled = (label: string) => labelMapping[label] !== null;

  const remapValue = (label: string): string => {
    const v = labelMapping[label];
    if (v === undefined || v === null) return '';
    return v;
  };

  const updatePatterns = (next: Record<string, string>) => {
    const cleaned: Record<string, string> = {};
    for (const [k, v] of Object.entries(next)) {
      if (v !== '') cleaned[k] = v;
    }
    onChange(Object.keys(cleaned).length > 0 ? cleaned : undefined, fieldPathId.path);
  };

  const updateLabelMapping = (next: Record<string, string | null>) => {
    if (!onConfigChange) return;
    const cleaned: Record<string, string | null> = {};
    for (const [k, v] of Object.entries(next)) {
      if (v === null || (typeof v === 'string' && v !== '')) {
        cleaned[k] = v;
      }
    }
    onConfigChange({
      ...config,
      label_mapping: Object.keys(cleaned).length > 0 ? cleaned : undefined,
    });
  };

  const toggleEnabled = (label: string) => {
    const next = { ...labelMapping };
    if (labelMapping[label] === null) {
      delete next[label];
    } else {
      next[label] = null;
    }
    updateLabelMapping(next);
  };

  const setRemap = (label: string, value: string) => {
    const next = { ...labelMapping };
    if (value === '') {
      delete next[label];
    } else {
      next[label] = value;
    }
    updateLabelMapping(next);
  };

  const setPattern = (label: string, value: string) => {
    const next = { ...patterns };
    if (value === '') {
      delete next[label];
    } else {
      next[label] = value;
    }
    updatePatterns(next);
  };

  const toggleExpand = (label: string) => {
    setExpandedLabels((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  };

  const addCustomLabel = () => {
    const trimmed = newLabel.trim().toUpperCase();
    if (!trimmed) return;
    setExpandedLabels((prev) => new Set(prev).add(trimmed));
    setNewLabel('');
  };

  const removeCustomLabel = (label: string) => {
    const nextPatterns = { ...patterns };
    delete nextPatterns[label];
    updatePatterns(nextPatterns);

    const nextMapping = { ...labelMapping };
    delete nextMapping[label];
    updateLabelMapping(nextMapping);

    setExpandedLabels((prev) => {
      const s = new Set(prev);
      s.delete(label);
      return s;
    });
  };

  // Build display list
  const customLabels = [
    ...Object.keys(patterns).filter((k) => !allLabels.includes(k)),
    ...Array.from(expandedLabels).filter(
      (k) => !allLabels.includes(k) && !(k in patterns),
    ),
  ];
  const uniqueCustom = [...new Set(customLabels)].sort();
  const displayLabels = [...allLabels, ...uniqueCustom];

  const description = schema.description as string | undefined;

  return (
    <div className="mb-3 space-y-2">
      <div className="flex items-center gap-2">
        <label className="block text-xs font-medium text-gray-600">
          Labels
        </label>
        {isLoading && (
          <Loader2 size={12} className="animate-spin text-gray-400" />
        )}
      </div>
      {description && (
        <p className="text-xs text-gray-400">{description}</p>
      )}

      {displayLabels.length > 0 && (
        <div className="space-y-1">
          {displayLabels.map((label) => {
            const enabled = isEnabled(label);
            const hasCustomPattern = label in patterns && patterns[label] !== '';
            const isOpen = expandedLabels.has(label);
            const isCustom = !allLabels.includes(label);
            const color = labelColor(label);
            const remap = remapValue(label);

            return (
              <div
                key={label}
                className={`rounded-md border transition-colors ${
                  !enabled
                    ? 'border-gray-100 bg-gray-50/60'
                    : isOpen
                      ? 'border-blue-200 bg-blue-50/20'
                      : 'border-gray-200 bg-white'
                }`}
              >
                {/* Main row */}
                <div className="flex items-center gap-2 px-2 py-1.5">
                  {/* On/off toggle */}
                  <button
                    type="button"
                    onClick={() => toggleEnabled(label)}
                    className={`relative h-4 w-7 shrink-0 rounded-full transition-colors ${
                      enabled ? 'bg-blue-500' : 'bg-gray-300'
                    }`}
                    title={enabled ? 'Disable this label' : 'Enable this label'}
                  >
                    <span
                      className={`absolute top-0.5 h-3 w-3 rounded-full bg-white shadow transition-transform ${
                        enabled ? 'left-3.5' : 'left-0.5'
                      }`}
                    />
                  </button>

                  {/* Label badge */}
                  <span
                    className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wide ${
                      enabled ? '' : 'opacity-40'
                    }`}
                    style={{
                      backgroundColor: color.bg,
                      color: color.text,
                      border: `1px solid ${color.border}`,
                    }}
                  >
                    {label}
                  </span>

                  {/* Status chips */}
                  {enabled && hasCustomPattern && (
                    <span className="text-[10px] text-blue-500">custom</span>
                  )}
                  {enabled && !hasCustomPattern && !isCustom && (
                    <span className="text-[10px] text-gray-300">built-in</span>
                  )}

                  <div className="flex-1" />

                  {/* Remove custom label */}
                  {isCustom && (
                    <button
                      type="button"
                      onClick={() => removeCustomLabel(label)}
                      className="rounded p-0.5 text-gray-400 hover:bg-red-50 hover:text-red-500"
                      title="Remove custom label"
                    >
                      <X size={12} />
                    </button>
                  )}

                  {/* Expand/collapse */}
                  {enabled && (
                    <button
                      type="button"
                      onClick={() => toggleExpand(label)}
                      className="rounded p-0.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                      title={isOpen ? 'Collapse' : 'Configure'}
                    >
                      {isOpen ? (
                        <ChevronDown size={14} />
                      ) : (
                        <ChevronRight size={14} />
                      )}
                    </button>
                  )}
                </div>

                {/* Expanded config */}
                {enabled && isOpen && (
                  <div className="space-y-2 border-t border-gray-100 px-2 py-2">
                    {/* Regex pattern */}
                    <div>
                      <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wider text-gray-400">
                        Regex pattern
                      </label>
                      <input
                        type="text"
                        className="w-full rounded border border-gray-200 bg-white px-1.5 py-1 font-mono text-xs text-gray-700 placeholder:text-gray-300 focus:border-blue-300 focus:outline-none"
                        value={patterns[label] ?? ''}
                        onChange={(e) => setPattern(label, e.target.value)}
                        placeholder={isCustom ? 'regex pattern…' : 'override built-in pattern…'}
                      />
                    </div>

                    {/* Label mapping */}
                    <div>
                      <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wider text-gray-400">
                        Map to label
                      </label>
                      <div className="flex items-center gap-1.5">
                        <ArrowRight size={12} className="shrink-0 text-gray-300" />
                        <input
                          type="text"
                          className="min-w-0 flex-1 rounded border border-gray-200 bg-gray-50 px-1.5 py-1 text-xs text-gray-700 placeholder:text-gray-300 focus:border-blue-300 focus:bg-white focus:outline-none"
                          value={remap}
                          onChange={(e) => setRemap(label, e.target.value)}
                          placeholder="keep as-is"
                        />
                      </div>
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

      {/* Add custom label */}
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
    </div>
  );
}
