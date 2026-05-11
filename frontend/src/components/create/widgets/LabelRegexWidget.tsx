import { Plus, X, Regex, Loader2 } from 'lucide-react';
import { useState } from 'react';
import type { FieldProps } from '@rjsf/utils';
import { labelColor } from '@shared/lib/labelColors';
import { useLabelSpace } from '../../../hooks/useLabelSpace';
import { usePipeFormContextConfig } from '../../../hooks/usePipeFormContextConfig';
import type { SchemaFormContext } from '../schemaFormContext';

/**
 * Label-space-aware editor for ``patterns: dict[str, str]``.
 *
 * Displays every known label for the detector.  Each row shows a label badge
 * and an optional regex input — empty means "use built-in pattern", filled
 * means "override with this custom pattern".
 *
 * Reads ``pipeType``, ``baseLabels``, and ``config`` from the schema annotations
 * injected by the API (``ui_base_labels``, ``ui_pipe_type``), falling back to
 * rjsf ``formContext``.
 */
export default function LabelRegexField(props: FieldProps) {
  const { formData, onChange, schema, formContext, fieldPathId } = props;
  const patterns: Record<string, string> = formData ?? {};

  const schemaAny = schema as Record<string, unknown>;
  const pipeType: string =
    (schemaAny.ui_pipe_type as string) || formContext?.pipeType || '';
  const baseLabels: string[] =
    (schemaAny.ui_base_labels as string[]) || formContext?.baseLabels || [];
  const config = usePipeFormContextConfig(formContext as SchemaFormContext | undefined);

  const { labels: allLabels, isLoading } = useLabelSpace(
    pipeType,
    config,
    baseLabels,
    patterns,
    { selectedNodeId: (formContext as SchemaFormContext | undefined)?.selectedNodeId },
  );

  const [newLabel, setNewLabel] = useState('');
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(Object.keys(patterns)));

  const update = (next: Record<string, string>) => {
    const cleaned: Record<string, string> = {};
    for (const [k, v] of Object.entries(next)) {
      if (v !== '') cleaned[k] = v;
    }
    onChange(Object.keys(cleaned).length > 0 ? cleaned : undefined, fieldPathId.path);
  };

  const setPattern = (label: string, value: string) => {
    const next = { ...patterns };
    if (value === '') {
      delete next[label];
    } else {
      next[label] = value;
    }
    update(next);
  };

  const toggleExpand = (label: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(label)) {
        next.delete(label);
        if (patterns[label]) {
          const copy = { ...patterns };
          delete copy[label];
          update(copy);
        }
      } else {
        next.add(label);
      }
      return next;
    });
  };

  const addCustomLabel = () => {
    const trimmed = newLabel.trim().toUpperCase();
    if (!trimmed) return;
    setExpanded((prev) => new Set(prev).add(trimmed));
    setNewLabel('');
  };

  const removeCustomLabel = (label: string) => {
    const next = { ...patterns };
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
  const allowCustomLabels = schemaAny.ui_allow_custom_labels === true;

  const customLabels = [
    ...Object.keys(patterns).filter((k) => !allLabels.includes(k)),
    ...Array.from(expanded).filter((k) => !allLabels.includes(k) && !(k in patterns)),
  ];
  const uniqueCustom = [...new Set(customLabels)].sort();
  const displayLabels = [...allLabels, ...uniqueCustom];

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
            const hasPattern = label in patterns && patterns[label] !== '';
            const isOpen = expanded.has(label) || hasPattern;
            const isCustom = !allLabels.includes(label);
            const color = labelColor(label);

            return (
              <div
                key={label}
                className={`rounded-md border transition-colors ${
                  hasPattern
                    ? 'border-blue-200 bg-blue-50/30'
                    : 'border-gray-200 bg-white'
                }`}
              >
                <div className="flex items-center gap-2 px-2 py-1.5">
                  <button
                    type="button"
                    onClick={() => toggleExpand(label)}
                    className={`flex h-4 w-4 shrink-0 items-center justify-center rounded transition-colors ${
                      isOpen
                        ? 'bg-blue-500 text-white'
                        : 'bg-gray-200 text-gray-400 hover:bg-gray-300'
                    }`}
                    title={isOpen ? 'Remove custom pattern' : 'Add custom pattern'}
                  >
                    <Regex size={10} />
                  </button>

                  <span
                    className="inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wide"
                    style={{
                      backgroundColor: color.bg,
                      color: color.text,
                      border: `1px solid ${color.border}`,
                    }}
                  >
                    {label}
                  </span>

                  {hasPattern && (
                    <span className="text-[10px] text-blue-500">custom</span>
                  )}
                  {!isOpen && !hasPattern && (
                    <span className="text-[10px] text-gray-300">built-in</span>
                  )}

                  {isCustom && (
                    <button
                      type="button"
                      onClick={() => removeCustomLabel(label)}
                      className="ml-auto rounded p-0.5 text-gray-400 hover:bg-red-50 hover:text-red-500"
                      title="Remove custom label"
                    >
                      <X size={12} />
                    </button>
                  )}
                </div>

                {isOpen && (
                  <div className="px-2 pb-1.5">
                    <input
                      type="text"
                      className="w-full rounded border border-gray-200 bg-white px-1.5 py-1 font-mono text-xs text-gray-700 placeholder:text-gray-300 focus:border-blue-300 focus:outline-none"
                      value={patterns[label] ?? ''}
                      onChange={(e) => setPattern(label, e.target.value)}
                      placeholder="regex pattern (overrides built-in)…"
                    />
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
            placeholder="Add pattern for new label…"
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
