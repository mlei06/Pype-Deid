import { useEffect, useRef, type RefObject } from 'react';

/**
 * Keeps multiple scroll containers aligned by `scrollTop / scrollHeight` ratio.
 * A re-entry guard prevents the synthetic `scrollTop` writes we apply to
 * mirrors from re-emitting `scroll` events that would feed back as input.
 */
export function useSyncScroll(
  refs: ReadonlyArray<RefObject<HTMLElement | null>>,
  enabled: boolean,
) {
  const isSyncingRef = useRef(false);

  useEffect(() => {
    if (!enabled) return;
    const elements = refs.map((r) => r.current).filter((el): el is HTMLElement => !!el);
    if (elements.length < 2) return;

    const handlers: Array<{ el: HTMLElement; fn: () => void }> = [];

    elements.forEach((source) => {
      const fn = () => {
        if (isSyncingRef.current) return;
        const sourceScrollable = source.scrollHeight - source.clientHeight;
        if (sourceScrollable <= 0) return;
        const ratio = source.scrollTop / sourceScrollable;

        isSyncingRef.current = true;
        try {
          for (const target of elements) {
            if (target === source) continue;
            const targetScrollable = target.scrollHeight - target.clientHeight;
            if (targetScrollable <= 0) continue;
            target.scrollTop = ratio * targetScrollable;
          }
        } finally {
          // Clear after the synthetic scroll events have flushed.
          requestAnimationFrame(() => {
            isSyncingRef.current = false;
          });
        }
      };
      source.addEventListener('scroll', fn, { passive: true });
      handlers.push({ el: source, fn });
    });

    return () => {
      for (const { el, fn } of handlers) el.removeEventListener('scroll', fn);
    };
  }, [refs, enabled]);
}
