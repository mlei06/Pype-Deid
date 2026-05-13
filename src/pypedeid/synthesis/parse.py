"""Parse model completions into :class:`SynthesisResult` (note + label → surface strings)."""

from __future__ import annotations

import json
import re
from typing import Any

from pypedeid.synthesis.types import SynthesisResult


def parse_synthesis_response(text: str) -> SynthesisResult:
    """
    Expects either:

    - ``Clinical Note: "....", PHI: {json-ish dict}``
    - or a trailing JSON object for PHI after ``PHI:``
    """
    raw = text.strip()
    note = ""
    phi: dict[str, list[str]] = {}

    q = re.search(
        r'Clinical\s+Note:\s*"((?:\\.|[^"])*)"',
        raw,
        re.IGNORECASE | re.DOTALL,
    )
    if q:
        note = _unescape_json_string(q.group(1))
    else:
        cn_match = re.search(
            r"Clinical\s+Note:\s*([^\n]+)",
            raw,
            re.IGNORECASE,
        )
        if cn_match:
            note = cn_match.group(1).strip().strip(",").strip()

    phi_match = re.search(r"PHI:\s*(.+)", raw, re.IGNORECASE | re.DOTALL)
    if phi_match:
        phi_blob = phi_match.group(1).strip()
        # Drop trailing prose after first full brace-balanced dict
        phi = _parse_phi_blob(phi_blob)
    elif not note:
        # Maybe whole message is JSON
        phi = _try_parse_json_object(raw)
        if isinstance(phi, dict) and "clinical_note" in phi:
            note = str(phi.get("clinical_note", ""))
            inner = phi.get("phi") or phi.get("PHI") or phi.get("entities")
            if isinstance(inner, dict):
                phi = {str(k): [str(x) for x in v] if isinstance(v, list) else [str(v)] for k, v in inner.items()}  # type: ignore[assignment]
            else:
                phi = {}
        else:
            phi = {}

    if not note and raw:
        note = raw

    return SynthesisResult(
        clinical_note=note.strip(),
        phi_entities=_normalize_phi(phi),
        raw_completion=text,
    )


def _unescape_json_string(s: str) -> str:
    try:
        return json.loads(f'"{s}"')
    except json.JSONDecodeError:
        return s.replace('\\"', '"')


def _parse_phi_blob(blob: str) -> dict[str, list[str]]:
    blob = blob.strip()
    # Strip trailing sentence if model added explanation
    for cut in ["\n\n", "\nPlease", "\nNote:", "\n```"]:
        if cut in blob:
            blob = blob.split(cut)[0].strip()

    # Prefer {...} substring
    brace_start = blob.find("{")
    brace_end = blob.rfind("}")
    if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
        inner = blob[brace_start : brace_end + 1]
        parsed = _try_parse_json_object(inner)
        if parsed:
            return parsed

    parsed = _try_parse_json_object(blob)
    if parsed:
        return parsed

    return _parse_phi_loose(blob)


def _try_parse_json_object(s: str) -> dict[str, list[str]]:
    s2 = s.strip()
    if not s2.startswith("{"):
        return {}
    try:
        obj = json.loads(s2)
    except json.JSONDecodeError:
        try:
            obj = json.loads(_fix_json_quotes(s2))
        except json.JSONDecodeError:
            return {}
    if not isinstance(obj, dict):
        return {}
    out: dict[str, list[str]] = {}
    for k, v in obj.items():
        key = str(k)
        if isinstance(v, list):
            out[key] = [str(x) for x in v]
        elif v is None:
            out[key] = []
        else:
            out[key] = [str(v)]
    return out


def _fix_json_quotes(s: str) -> str:
    # Replace single quotes with double for keys only — best-effort
    return re.sub(r"'([^']*)':", r'"\1":', s)


def _parse_phi_loose(blob: str) -> dict[str, list[str]]:
    """Fallback: "KEY":["a","b"], "KEY2":["c"]"""
    out: dict[str, list[str]] = {}
    for m in re.finditer(r'"([^"]+)"\s*:\s*(\[[^\]]*\])', blob):
        key, arr_raw = m.group(1), m.group(2)
        try:
            arr = json.loads(arr_raw)
            if isinstance(arr, list):
                out[key] = [str(x) for x in arr]
        except json.JSONDecodeError:
            continue
    return out


def _normalize_phi(phi: Any) -> dict[str, list[str]]:
    if not isinstance(phi, dict):
        return {}
    out: dict[str, list[str]] = {}
    for k, v in phi.items():
        key = str(k)
        if isinstance(v, list):
            out[key] = [str(x) for x in v]
        elif v is None:
            out[key] = []
        else:
            out[key] = [str(v)]
    return out
