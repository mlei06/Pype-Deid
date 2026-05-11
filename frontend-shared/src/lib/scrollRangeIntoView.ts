function collectTextNodes(root: HTMLElement): Text[] {
  const out: Text[] = [];
  const walk = (n: Node) => {
    if (n.nodeType === Node.TEXT_NODE) out.push(n as Text);
    else n.childNodes.forEach((c) => walk(c));
  };
  walk(root);
  return out;
}

/**
 * Scroll a container so the text range [start, end) in `root` is brought into view.
 */
export function scrollTextRangeIntoView(
  root: HTMLElement,
  _fullText: string,
  start: number,
  end: number,
  opts?: ScrollIntoViewOptions,
): void {
  if (start < 0 || start >= end) return;

  const textNodes = collectTextNodes(root);
  const range = document.createRange();
  let offset = 0;
  let startSet = false;

  for (const tn of textNodes) {
    const len = tn.length;
    const nodeEnd = offset + len;

    if (!startSet && start < nodeEnd) {
      range.setStart(tn, Math.max(0, start - offset));
      startSet = true;
    }
    if (startSet && end <= nodeEnd) {
      range.setEnd(tn, Math.min(len, end - offset));
      try {
        const el =
          range.commonAncestorContainer.nodeType === Node.TEXT_NODE
            ? (range.commonAncestorContainer.parentElement ?? root)
            : (range.commonAncestorContainer as HTMLElement);
        el.scrollIntoView({ block: 'center', inline: 'nearest', ...(opts ?? {}) });
      } catch {
        /* ignore */
      }
      return;
    }
    offset = nodeEnd;
  }
}
