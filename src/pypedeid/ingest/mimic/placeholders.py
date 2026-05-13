"""Detect MIMIC de-id placeholders ``[**...**]`` in NOTEEVENTS text."""

from __future__ import annotations

import re
from typing import TypedDict


class PlaceholderSpan(TypedDict):
    text: str
    content: str
    start: int
    end: int


_PLACEHOLDER_PATTERN = re.compile(r"\[\*\*([^*]+)\*\*\]")


def extract_placeholders(text: str) -> list[PlaceholderSpan]:
    return [
        {
            "text": m.group(0),
            "content": m.group(1),
            "start": m.start(),
            "end": m.end(),
        }
        for m in _PLACEHOLDER_PATTERN.finditer(text)
    ]
