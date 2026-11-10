"""Answer validation and branching visibility (pure; P04-T07/T08).

Questions are the frozen question rows of the application's job version, given here as plain dicts
``{key, type, required, config, branching, options: [values]}`` in display order. Visibility is
evaluated in order, so a question whose condition depends on a hidden question is hidden too.
Hidden questions' answers are discarded server-side, never stored or scored.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

SHORT_TEXT_MAX = 300
LONG_TEXT_MAX_CHARS = 20000
WORD_RE = re.compile(r"\S+")


def _num(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _matches(op: str, answer: Any, expected: Any) -> bool:
    if op == "answered":
        return answer not in (None, "", [])
    if answer in (None, "", []):
        return False
    values = answer if isinstance(answer, list) else [answer]
    if op in ("eq", "in"):
        wanted = expected if isinstance(expected, list) else [expected]
        return any(str(v) in {str(w) for w in wanted} for v in values)
    if op in ("neq", "not_in"):
        wanted = expected if isinstance(expected, list) else [expected]
        return all(str(v) not in {str(w) for w in wanted} for v in values)
    a, e = _num(answer), _num(expected)
    if a is None or e is None:
        return False
    return a >= e if op == "gte" else a <= e if op == "lte" else False


def visible_keys(questions: list[dict[str, Any]], answers: dict[str, Any]) -> list[str]:
    shown: list[str] = []
    for q in questions:
        show_if = (q.get("branching") or {}).get("show_if")
        if show_if:
            parent = str(show_if.get("question", ""))
            if parent not in shown or not _matches(
                str(show_if.get("op", "eq")), answers.get(parent), show_if.get("value")
            ):
                continue
        shown.append(q["key"])
    return shown


def validate_answer(q: dict[str, Any], value: Any) -> tuple[Any, str | None]:
    """Return ``(value, error)``; ``None``/empty means "not answered" (allowed in a draft)."""
    t = q["type"]
    cfg = q.get("config") or {}
    if value in (None, "", []):
        return None, None
    if t == "yes_no":
        v = str(value).lower()
        return (v, None) if v in ("yes", "no") else (None, "Choose yes or no.")
    if t == "single_choice":
        return (
            (str(value), None)
            if str(value) in q.get("options", [])
            else (None, "Choose one of the options.")
        )
    if t == "multiple_choice":
        if not isinstance(value, list):
            return None, "Choose one or more options."
        chosen = list(dict.fromkeys(str(v) for v in value))
        if any(v not in q.get("options", []) for v in chosen):
            return None, "Choose from the listed options."
        return chosen, None
    if t in ("number", "scale", "availability", "salary_expectation"):
        n = _num(value)
        if n is None:
            return None, "Enter a number."
        lo = _num(cfg.get("min", 1 if t == "scale" else None))
        hi = _num(cfg.get("max", 5 if t == "scale" else None))
        if (lo is not None and n < lo) or (hi is not None and n > hi):
            return None, "This number is outside the allowed range."
        if t == "scale" and n != n.to_integral_value():
            return None, "Choose a whole number."
        return (int(n) if n == n.to_integral_value() else float(n)), None
    if t == "short_text":
        text = str(value).strip()
        if len(text) > SHORT_TEXT_MAX:
            return None, f"Keep this under {SHORT_TEXT_MAX} characters."
        return text, None
    if t == "long_text":
        text = str(value).strip()
        limit = cfg.get("word_limit")
        if len(text) > LONG_TEXT_MAX_CHARS or (limit and len(WORD_RE.findall(text)) > int(limit)):
            return None, f"Keep this under {limit or 'the'} words."
        return text, None
    if t == "date":
        try:
            return date.fromisoformat(str(value)).isoformat(), None
        except ValueError:
            return None, "Enter a valid date."
    if t == "file_upload":
        return str(value), None  # document ownership is checked by the service
    return None, "Unsupported question type."


def missing_required(questions: list[dict[str, Any]], answers: dict[str, Any]) -> list[str]:
    shown = set(visible_keys(questions, answers))
    return [
        q["key"]
        for q in questions
        if q["key"] in shown and q.get("required", True) and answers.get(q["key"]) in (None, "", [])
    ]
