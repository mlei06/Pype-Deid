import { useMemo } from 'react';
import { labelColor } from '../lib/labelColors';

interface RedactedViewProps {
  text: string;
}

const TAG_RE = /\[([A-Z_]+)\]/g;

export default function RedactedView({ text }: RedactedViewProps) {
  const parts = useMemo(() => {
    const result: { text: string; label: string | null }[] = [];
    let lastIndex = 0;

    for (const match of text.matchAll(TAG_RE)) {
      if (match.index > lastIndex) {
        result.push({ text: text.slice(lastIndex, match.index), label: null });
      }
      result.push({ text: match[0], label: match[1] });
      lastIndex = match.index + match[0].length;
    }

    if (lastIndex < text.length) {
      result.push({ text: text.slice(lastIndex), label: null });
    }

    return result;
  }, [text]);

  return (
    <pre className="whitespace-pre-wrap break-words font-mono text-sm leading-relaxed">
      {parts.map((p, i) => {
        if (!p.label) return <span key={i}>{p.text}</span>;
        const c = labelColor(p.label);
        return (
          <span
            key={i}
            className="rounded px-0.5 font-semibold"
            style={{ backgroundColor: c.bg, color: c.text }}
          >
            {p.text}
          </span>
        );
      })}
    </pre>
  );
}
