import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Loader2, X } from 'lucide-react';
import { redactDocument } from '../../api/process';
import type { EntitySpanResponse } from '../../api/types';
import type { OverlapGroup } from '../../lib/spanOverlapConflicts';
import LabelBadge from '../shared/LabelBadge';

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

interface ConflictResolutionPopoverProps {
  open: boolean;
  onClose: () => void;
  anchorRect: DOMRect | null;
  originalText: string;
  group: OverlapGroup | null;
  onKeep: (group: OverlapGroup, kept: EntitySpanResponse) => void;
  /** Drop every member of the group — user decided no label applies here. */
  onDropAll?: (group: OverlapGroup) => void;
}

export default function ConflictResolutionPopover({
  open,
  onClose,
  anchorRect,
  originalText,
  group,
  onKeep,
  onDropAll,
}: ConflictResolutionPopoverProps) {
  const [surrogateSnippets, setSurrogateSnippets] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);

  // Save the previously-focused element, focus the dialog on open, restore on close.
  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    // Defer to next tick so the dialog has mounted.
    const id = window.setTimeout(() => {
      const root = dialogRef.current;
      if (!root) return;
      const focusables = root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
      (focusables[0] ?? root).focus();
    }, 0);
    return () => {
      window.clearTimeout(id);
      previouslyFocused?.focus?.();
    };
  }, [open]);

  // Escape closes; Tab cycles within the dialog.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== 'Tab') return;
      const root = dialogRef.current;
      if (!root) return;
      const focusables = Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement as HTMLElement | null;
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', handler, true);
    return () => document.removeEventListener('keydown', handler, true);
  }, [open, onClose]);

  useEffect(() => {
    if (!open || !group) {
      setSurrogateSnippets({});
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    const run = async () => {
      try {
        const entries = await Promise.all(
          group.members.map(async (s) => {
            const res = await redactDocument({
              text: originalText,
              spans: [{ start: s.start, end: s.end, label: s.label }],
              output_mode: 'surrogate',
            });
            const slice = res.output_text.slice(s.start, s.end);
            return [`${s.start}-${s.end}-${s.label}`, slice] as const;
          }),
        );
        if (!cancelled) {
          setSurrogateSnippets(Object.fromEntries(entries));
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Preview failed');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [open, group, originalText]);

  if (!open || !group || !anchorRect) return null;

  const left = Math.max(8, Math.min(anchorRect.left, window.innerWidth - 420));
  const top = Math.min(anchorRect.bottom + 8, window.innerHeight - 120);
  const excerpt = group.excerpt.length > 60 ? `${group.excerpt.slice(0, 60)}…` : group.excerpt;
  const isExactRange = group.members.every(
    (m) => m.start === group.minStart && m.end === group.maxEnd,
  );

  const body = (
    <div
      ref={dialogRef}
      tabIndex={-1}
      className="fixed z-[100] w-[min(400px,calc(100vw-16px))] rounded-lg border border-amber-200 bg-white p-3 shadow-2xl outline-none"
      style={{ left, top }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="conflict-popover-title"
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <div>
          <h3 id="conflict-popover-title" className="text-sm font-semibold text-gray-900">
            Resolve span conflict
          </h3>
          <p className="mt-0.5 text-[11px] text-gray-500">
            <span className="font-mono text-gray-700">{excerpt}</span>
            <span className="text-gray-400"> at </span>
            {group.minStart}–{group.maxEnd}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
          aria-label="Close"
        >
          <X size={16} />
        </button>
      </div>
      <p className="mb-3 text-[11px] leading-snug text-gray-600">
        {isExactRange
          ? 'Multiple pipes assigned different labels to this exact range. Choose the label to use for redaction and surrogacy.'
          : 'These spans overlap. Keep one (others in the group are dropped) or drop them all.'}
      </p>

      {loading && (
        <div className="mb-2 flex items-center gap-2 text-[11px] text-gray-500">
          <Loader2 size={12} className="animate-spin" />
          Loading surrogate previews…
        </div>
      )}
      {error && (
        <div className="mb-2 rounded border border-red-100 bg-red-50 px-2 py-1 text-[11px] text-red-700">
          {error}
        </div>
      )}

      <ul className="mb-3 space-y-2">
        {group.members.map((s) => {
          const k = `${s.start}-${s.end}-${s.label}`;
          const preview = surrogateSnippets[k];
          return (
            <li
              key={k}
              className="rounded border border-gray-100 bg-gray-50/80 px-2 py-2 text-[11px]"
            >
              <div className="mb-1 flex flex-wrap items-center gap-1.5">
                <LabelBadge label={s.label} />
                <span className="font-mono text-[10px] text-gray-500">
                  [{s.start}–{s.end}]
                </span>
                <span className="text-gray-500">
                  {s.source ? (
                    <>
                      Found by: <span className="font-medium text-gray-700">{s.source}</span>
                    </>
                  ) : (
                    <span className="text-gray-400">Source unknown</span>
                  )}
                </span>
              </div>
              <div className="font-mono text-[10px] text-gray-600">
                Surrogate:{' '}
                <span className="text-gray-900">
                  {preview !== undefined ? preview : loading ? '…' : '—'}
                </span>
              </div>
              <button
                type="button"
                onClick={() => onKeep(group, s)}
                className="mt-2 w-full rounded bg-gray-900 px-2 py-1.5 text-[11px] font-medium text-white hover:bg-gray-800"
              >
                Keep {s.label}
              </button>
            </li>
          );
        })}
      </ul>

      {onDropAll && (
        <button
          type="button"
          onClick={() => onDropAll(group)}
          className="mb-2 w-full rounded border border-red-200 bg-white py-1.5 text-[11px] font-medium text-red-700 hover:bg-red-50"
          title="Remove every span in this overlap group"
        >
          Keep none — drop spans
        </button>
      )}

      <button
        type="button"
        onClick={onClose}
        className="w-full rounded border border-gray-200 py-1.5 text-[11px] text-gray-600 hover:bg-gray-50"
      >
        Cancel
      </button>
    </div>
  );

  return createPortal(body, document.body);
}
