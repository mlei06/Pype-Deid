"""Parse txt/json/csv phrase lists for :class:`~pypedeid.pipes.whitelist.WhitelistPipe`."""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path


def _strip_comment_line(line: str) -> str:
    line = line.strip()
    if not line or line.startswith("#"):
        return ""
    return line


def parse_list_text(content: str, *, filename: str | None = None) -> list[str]:
    """Parse newline-delimited terms (blank lines and ``#`` comments ignored)."""
    terms: list[str] = []
    for raw in content.splitlines():
        s = _strip_comment_line(raw)
        if s:
            terms.append(s)
    return terms


def parse_list_json(content: str) -> list[str]:
    data = json.loads(content)
    if isinstance(data, list):
        return [str(x).strip() for x in data if str(x).strip()]
    if isinstance(data, dict):
        for key in ("terms", "items", "values", "names"):
            if key in data and isinstance(data[key], list):
                return [str(x).strip() for x in data[key] if str(x).strip()]
        out: list[str] = []
        for v in data.values():
            if isinstance(v, str) and v.strip():
                out.append(v.strip())
        return out
    raise ValueError("JSON list file must be an array or an object with a list field")


def parse_list_csv(content: str) -> list[str]:
    """Use the first column of each row as the term (skip header if non-numeric first row)."""
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        return []
    start = 0
    if rows[0] and rows[0][0].lower() in ("term", "name", "value", "text", "phrase"):
        start = 1
    terms: list[str] = []
    for row in rows[start:]:
        if row and row[0].strip():
            terms.append(row[0].strip())
    return terms


def parse_list_file(content: str, filename: str | None = None) -> list[str]:
    """Dispatch on file extension / sniff JSON."""
    name = (filename or "").lower()
    stripped = content.lstrip()
    if stripped.startswith(("[", "{")):
        try:
            return parse_list_json(content)
        except json.JSONDecodeError:
            pass
    if name.endswith(".json"):
        return parse_list_json(content)
    if name.endswith(".csv"):
        return parse_list_csv(content)
    return parse_list_text(content, filename=filename)


def load_terms_from_path(path: Path) -> list[str]:
    return parse_list_file(path.read_text(encoding="utf-8"), filename=path.name)


def term_to_list_pattern(term: str) -> re.Pattern[str]:
    """Build a case-insensitive pattern: word boundaries; multi-word allows flexible whitespace."""
    parts = [p for p in re.split(r"\s+", term.strip()) if p]
    if not parts:
        return re.compile(r"(?!x)x")  # never matches
    escaped = [re.escape(p) for p in parts]
    if len(escaped) == 1:
        return re.compile(r"\b" + escaped[0] + r"\b", re.IGNORECASE)
    inner = r"\s+".join(escaped)
    return re.compile(r"\b" + inner + r"\b", re.IGNORECASE)
