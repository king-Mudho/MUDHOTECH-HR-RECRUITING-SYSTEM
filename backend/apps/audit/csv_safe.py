"""CSV cells safe to open in spreadsheets: neutralise formula injection (CLAUDE.md §10)."""

from __future__ import annotations

from typing import Any

DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def cell(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.startswith(DANGEROUS):
        return "'" + text
    return text
