import { useState, useEffect, useRef } from 'react';
import { ChevronDown } from 'lucide-react';
import { labelFamilyLegend, labelFamilySwatch } from '../lib/labelColors';

export default function ColorKeyPopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const items = labelFamilyLegend();

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current?.contains(e.target as Node)) return;
      setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 rounded border border-gray-200 bg-white px-1.5 py-0.5 text-[10px] font-medium text-gray-600 hover:bg-gray-50"
        aria-expanded={open}
        title="Show label color key"
      >
        Color key
        <ChevronDown
          size={11}
          className={open ? 'rotate-180 transition-transform' : 'transition-transform'}
        />
      </button>
      {open && (
        <div className="absolute left-0 top-full z-40 mt-1 w-[320px] max-w-[80vw] rounded-md border border-gray-200 bg-white p-2 shadow-lg">
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px]">
            {items.map(({ family, title }) => {
              const sw = labelFamilySwatch(family);
              return (
                <span
                  key={family}
                  className="inline-flex items-center gap-1 text-gray-700"
                  title={title}
                >
                  <span
                    className="h-2.5 w-2.5 shrink-0 rounded-sm"
                    style={{ backgroundColor: sw.bg, border: `1px solid ${sw.border}` }}
                  />
                  <span className="max-w-[160px] truncate">{title}</span>
                </span>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
