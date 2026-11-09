"""Questionnaire definition validation (P03-T03): types, options, branching and scoring.

Input is the list of question dicts as sent by the builder (PUT /hr/jobs/{id}/questionnaire).
Returns ``{"<index>": {"field": ["message", ...]}}``; empty dict means valid. Pure Python.
"""

from __future__ import annotations

import re
from typing import Any

TYPES = {
    "yes_no",
    "single_choice",
    "multiple_choice",
    "number",
    "short_text",
    "long_text",
    "date",
    "file_upload",
    "scale",
    "availability",
    "salary_expectation",
}
CHOICE_TYPES = {"single_choice", "multiple_choice"}
NUMERIC_TYPES = {"number", "scale", "salary_expectation", "availability"}
TEXT_TYPES = {"short_text", "long_text"}
SCORING_MODES = {"none", "exact", "options", "range", "rubric_text", "human"}
MODES_BY_TYPE: dict[str, set[str]] = {
    "yes_no": {"none", "exact", "human"},
    "single_choice": {"none", "exact", "options", "human"},
    "multiple_choice": {"none", "options", "human"},
    "number": {"none", "range", "exact", "human"},
    "scale": {"none", "range", "exact", "human"},
    "short_text": {"none", "rubric_text", "human"},
    "long_text": {"none", "rubric_text", "human"},
    "date": {"none", "human"},
    "file_upload": {"none", "human"},
    "availability": {"none", "range", "human"},
    # FR-M08-01: salary expectations are never scored (avoid pay-based screening by default).
    "salary_expectation": {"none"},
}
BRANCH_OPS = {"eq", "neq", "in", "not_in", "gte", "lte", "answered"}
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,59}$")
MAX_QUESTIONS = 60


def _err(errors: dict[str, dict[str, list[str]]], idx: int, field: str, msg: str) -> None:
    errors.setdefault(str(idx), {}).setdefault(field, []).append(msg)


def _option_values(q: dict[str, Any]) -> list[str]:
    if q.get("type") == "yes_no":
        return ["yes", "no"]
    return [str(o.get("value", "")) for o in q.get("options") or []]


def validate_questions(questions: list[dict[str, Any]]) -> dict[str, dict[str, list[str]]]:
    errors: dict[str, dict[str, list[str]]] = {}
    if len(questions) > MAX_QUESTIONS:
        _err(errors, 0, "non_field_errors", f"At most {MAX_QUESTIONS} questions are allowed.")
    earlier: dict[str, dict[str, Any]] = {}
    for idx, q in enumerate(questions):
        key = str(q.get("key", ""))
        qtype = q.get("type")
        if not KEY_RE.match(key):
            _err(errors, idx, "key", "Use 1-60 lowercase letters, numbers, '-' or '_'.")
        elif key in earlier:
            _err(errors, idx, "key", "Each question needs a unique key.")
        if qtype not in TYPES:
            _err(errors, idx, "type", "Unknown question type.")
        if not str(q.get("prompt", "")).strip():
            _err(errors, idx, "prompt", "The question text is required.")

        # options
        options = q.get("options") or []
        if qtype in CHOICE_TYPES:
            values = [str(o.get("value", "")).strip() for o in options]
            if len(options) < 2:
                _err(errors, idx, "options", "Choice questions need at least two options.")
            if any(not v for v in values) or any(
                not str(o.get("label", "")).strip() for o in options
            ):
                _err(errors, idx, "options", "Every option needs a label and a value.")
            if len(set(values)) != len(values):
                _err(errors, idx, "options", "Option values must be unique.")
        elif options and qtype != "yes_no":
            _err(errors, idx, "options", "Only choice questions have options.")

        # config
        config = q.get("config") or {}
        if qtype in NUMERIC_TYPES and {"min", "max"} <= set(config):
            try:
                if float(config["min"]) > float(config["max"]):
                    _err(errors, idx, "config", "Minimum must not exceed maximum.")
            except (TypeError, ValueError):
                _err(errors, idx, "config", "Minimum and maximum must be numbers.")
        if qtype == "long_text" and "word_limit" in config:
            limit = config["word_limit"]
            if not isinstance(limit, int) or not 1 <= limit <= 2000:
                _err(errors, idx, "config", "Word limit must be between 1 and 2000.")

        # scoring
        scoring = q.get("scoring") or {"mode": "none"}
        mode = scoring.get("mode", "none")
        if mode not in SCORING_MODES:
            _err(errors, idx, "scoring", "Unknown scoring mode.")
        elif qtype in MODES_BY_TYPE and mode not in MODES_BY_TYPE[qtype]:
            _err(
                errors, idx, "scoring", f"'{mode}' scoring is not available for this question type."
            )
        elif mode == "exact" and scoring.get("expected") in (None, "", []):
            _err(errors, idx, "scoring", "Set the expected answer.")
        elif (
            mode == "exact"
            and qtype in {"yes_no", "single_choice"}
            and str(scoring.get("expected")) not in _option_values(q)
        ):
            _err(errors, idx, "scoring", "The expected answer must be one of the options.")
        elif mode == "options" and not any(o.get("points") not in (None, "") for o in options):
            _err(errors, idx, "scoring", "Give points to at least one option.")
        elif mode == "range":
            bands = scoring.get("bands") or []
            if not bands or any(
                "min" not in b or "max" not in b or "points" not in b for b in bands
            ):
                _err(errors, idx, "scoring", "Range scoring needs bands with min, max and points.")
        elif mode == "rubric_text" and not (scoring.get("keywords") or scoring.get("criteria")):
            _err(errors, idx, "scoring", "Add keywords or criteria for text scoring.")

        # knock-out: needs an eligibility answer to compare against (never auto-rejects)
        if q.get("is_knockout"):
            if qtype not in {"yes_no", "single_choice", "number"}:
                _err(
                    errors,
                    idx,
                    "is_knockout",
                    "Only yes/no, single choice or number questions can be eligibility checks.",
                )
            elif q.get("knockout_expected") in (None, "", []):
                _err(errors, idx, "is_knockout", "Set the answer that meets the requirement.")

        # branching: may only reference earlier questions (prevents cycles by construction)
        show_if = (q.get("branching") or {}).get("show_if")
        if show_if:
            ref = str(show_if.get("question", ""))
            op = show_if.get("op")
            if ref == key:
                _err(errors, idx, "branching", "A question cannot depend on itself.")
            elif ref not in earlier:
                _err(errors, idx, "branching", "Conditions may only refer to earlier questions.")
            if op not in BRANCH_OPS:
                _err(errors, idx, "branching", "Unknown condition.")
            elif ref in earlier and op in {"eq", "neq", "in", "not_in"}:
                allowed = _option_values(earlier[ref])
                wanted = show_if.get("value")
                wanted_list = wanted if isinstance(wanted, list) else [wanted]
                if allowed and any(str(w) not in allowed for w in wanted_list):
                    _err(
                        errors,
                        idx,
                        "branching",
                        "The condition value must be an option of that question.",
                    )
        if KEY_RE.match(key) and key not in earlier:
            earlier[key] = q
    return errors
