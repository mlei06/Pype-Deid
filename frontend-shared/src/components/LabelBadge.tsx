import type { HTMLAttributes } from 'react';
import { labelColor } from '../lib/labelColors';

interface LabelBadgeProps extends HTMLAttributes<HTMLSpanElement> {
  label: string;
  className?: string;
}

export default function LabelBadge({ label, className = '', ...rest }: LabelBadgeProps) {
  const c = labelColor(label);
  return (
    <span
      className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase leading-none ${className}`}
      style={{ backgroundColor: c.bg, color: c.text, border: `1px solid ${c.border}` }}
      {...rest}
    >
      {label}
    </span>
  );
}
