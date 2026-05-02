import { ArrowDown, ArrowUp, Minus } from 'lucide-react';

interface DeltaBadgeProps {
  /** ``current - baseline``. Pass ``null`` to render nothing. */
  delta: number | null;
  /** Render compact (10 px) or default (11 px) sizing. */
  compact?: boolean;
}

export default function DeltaBadge({ delta, compact }: DeltaBadgeProps) {
  if (delta == null) return null;
  const size = compact ? 10 : 11;
  const cls = compact ? 'text-[10px]' : 'text-[11px]';
  if (Math.abs(delta) < 0.001) {
    return (
      <span className={`inline-flex items-center gap-0.5 ${cls} text-gray-400`}>
        <Minus size={size} />
        flat
      </span>
    );
  }
  if (delta > 0) {
    return (
      <span className={`inline-flex items-center gap-0.5 ${cls} font-semibold text-green-600`}>
        <ArrowUp size={size} />+{(delta * 100).toFixed(1)}%
      </span>
    );
  }
  return (
    <span className={`inline-flex items-center gap-0.5 ${cls} font-semibold text-red-600`}>
      <ArrowDown size={size} />
      {(delta * 100).toFixed(1)}%
    </span>
  );
}
