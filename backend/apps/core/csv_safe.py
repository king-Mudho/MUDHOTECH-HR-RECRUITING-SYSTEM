"""Spreadsheet-safe CSV cells (EC-PRV-08, CLAUDE.md §10): neutralise formula injection.

Every CSV/XLSX export of user-entered text must pass values through ``cell``.
"""

from __future__ import annotations

from typing import Any

DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def cell(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.startswith(DANGEROUS):
        return "'" + text
    return text


def row(values: list[Any]) -> list[str]:
    return [cell(v) for v in values]
