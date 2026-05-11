import { useEffect, useMemo, useRef, useState } from 'react';
import { clsx } from 'clsx';
import { CANONICAL_LABELS } from '@shared/lib/canonicalLabels';

interface LabelComboboxProps {
  value: string;
  /** Called when the user accepts a value (Enter, suggestion click, or blur if commitOnBlur). */
  onCommit: (next: string) => void;
  /** Called when user dismisses without committing (Escape). */
  onCancel?: () => void;
  /** Extra suggestions (e.g. labels already present on the document) shown above the canonical list. */
  extraSuggestions?: string[];
  placeholder?: string;
  className?: string;
  inputClassName?: string;
  autoFocus?: boolean;
  /** When true, blur away from the field commits the typed value (matches inline-edit ergonomics). */
  commitOnBlur?: boolean;
  size?: 'sm' | 'md';
  ariaLabel?: string;
}

/**
 * Free-text-or-pick label input with autocomplete over `CANONICAL_LABELS` plus
 * any extra suggestions (e.g. labels already present on the current document).
 *
 * Keyboard:
 *  - ↑ / ↓ — move highlighted suggestion
 *  - Enter — commit highlighted suggestion or, if no menu open, the typed value
 *  - Escape — cancel and revert the input
 */
export default function LabelCombobox({
  value,
  onCommit,
  onCancel,
  extraSuggestions = [],
  placeholder = 'Type label',
  className,
  inputClassName,
  autoFocus = false,
  commitOnBlur = false,
  size = 'md',
  ariaLabel,
}: LabelComboboxProps) {
  const [draft, setDraft] = useState(value);
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);
  const blurredCommitting = useRef(false);

  useEffect(() => setDraft(value), [value]);

  const suggestions = useMemo(() => {
    const seen = new Set<string>();
    const all: string[] = [];
    for (const l of [...extraSuggestions, ...CANONICAL_LABELS]) {
      const t = l.trim();
      if (!t || seen.has(t)) continue;
      seen.add(t);
      all.push(t);
    }
    const q = draft.trim().toUpperCase();
    if (!q) return all.slice(0, 12);
    const matches = all.filter((l) => l.toUpperCase().includes(q));
    matches.sort((a, b) => {
      const ar = a.toUpperCase().startsWith(q) ? 0 : 1;
      const br = b.toUpperCase().startsWith(q) ? 0 : 1;
      return ar - br || a.localeCompare(b);
    });
    return matches.slice(0, 12);
  }, [draft, extraSuggestions]);

  useEffect(() => {
    if (activeIdx >= suggestions.length) setActiveIdx(0);
  }, [suggestions.length, activeIdx]);

  const commit = (raw: string) => {
    const next = raw.trim();
    if (!next) {
      onCancel?.();
      setOpen(false);
      return;
    }
    onCommit(next);
    setOpen(false);
  };

  const sizeCls =
    size === 'sm' ? 'px-1 py-0.5 text-[10px]' : 'px-2 py-1 text-xs';

  return (
    <div className={clsx('relative', className)}>
      <input
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        aria-label={ariaLabel}
        autoFocus={autoFocus}
        value={draft}
        placeholder={placeholder}
        className={clsx(
          'w-full rounded border border-gray-200 bg-white text-gray-800 outline-none focus:border-gray-400',
          sizeCls,
          inputClassName,
        )}
        onChange={(e) => {
          setDraft(e.target.value);
          setOpen(true);
          setActiveIdx(0);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          // Allow mousedown on a suggestion to fire first.
          window.setTimeout(() => {
            setOpen(false);
            if (blurredCommitting.current) {
              blurredCommitting.current = false;
              return;
            }
            if (commitOnBlur) {
              const next = draft.trim();
              if (next && next !== value) {
                onCommit(next);
              } else if (!next) {
                onCancel?.();
              }
            }
          }, 0);
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            const pick =
              open && suggestions[activeIdx] ? suggestions[activeIdx] : draft;
            commit(pick);
          } else if (e.key === 'Escape') {
            e.preventDefault();
            setDraft(value);
            setOpen(false);
            onCancel?.();
          } else if (e.key === 'ArrowDown') {
            if (suggestions.length === 0) return;
            e.preventDefault();
            setOpen(true);
            setActiveIdx((i) => (i + 1) % suggestions.length);
          } else if (e.key === 'ArrowUp') {
            if (suggestions.length === 0) return;
            e.preventDefault();
            setOpen(true);
            setActiveIdx(
              (i) => (i - 1 + suggestions.length) % suggestions.length,
            );
          }
        }}
      />
      {open && suggestions.length > 0 && (
        <ul
          role="listbox"
          className="absolute left-0 right-0 top-full z-30 mt-0.5 max-h-48 min-w-full overflow-auto rounded border border-gray-200 bg-white py-0.5 shadow-lg"
        >
          {suggestions.map((s, i) => (
            <li key={s}>
              <button
                type="button"
                role="option"
                aria-selected={i === activeIdx}
                onMouseDown={(e) => {
                  e.preventDefault();
                  blurredCommitting.current = true;
                  commit(s);
                }}
                onMouseEnter={() => setActiveIdx(i)}
                className={clsx(
                  'block w-full px-2 py-1 text-left text-[11px]',
                  i === activeIdx
                    ? 'bg-gray-100 text-gray-900'
                    : 'text-gray-700 hover:bg-gray-50',
                )}
              >
                {s}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
