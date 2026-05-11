import { CANONICAL_LABELS } from '@shared/lib/canonicalLabels';
import { labelColor } from '@shared/lib/labelColors';

interface Props {
  value: string;
  onChange: (value: string) => void;
  /** The source label — excluded from the dropdown since remapping to itself is a no-op. */
  exclude?: string;
  disabled?: boolean;
}

/**
 * Dropdown selector for remapping a detector label to a canonical PHI label.
 *
 * Shows "keep as-is" as the default empty option, then lists all canonical
 * labels with color-coded styling.
 */
export default function CanonicalLabelSelect({ value, onChange, exclude, disabled }: Props) {
  return (
    <select
      className="min-w-0 flex-1 rounded border border-gray-200 bg-gray-50 px-1.5 py-0.5 text-xs text-gray-700 focus:border-blue-300 focus:bg-white focus:outline-none disabled:opacity-40"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      style={value ? { color: labelColor(value).text, fontWeight: 600 } : undefined}
    >
      <option value="">keep as-is</option>
      {CANONICAL_LABELS.filter((l) => l !== exclude).map((label) => (
        <option key={label} value={label}>
          {label}
        </option>
      ))}
    </select>
  );
}
