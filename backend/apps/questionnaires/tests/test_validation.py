"""Questionnaire definition validation (P03-T03)."""

from __future__ import annotations

from typing import Any

import pytest

from apps.questionnaires.validation import validate_questions


def q(key: str, qtype: str = "yes_no", **extra: Any) -> dict[str, Any]:
    return {"key": key, "type": qtype, "prompt": f"Question {key}?", "required": True, **extra}


def test_valid_questionnaire_with_branching_and_scoring() -> None:
    questions = [
        q(
            "licence",
            is_knockout=True,
            knockout_expected="yes",
            scoring={"mode": "exact", "expected": "yes", "points": 10},
        ),
        q(
            "licence-class",
            "single_choice",
            options=[
                {"label": "Class 4", "value": "c4", "points": 5},
                {"label": "Class 2", "value": "c2", "points": 10},
            ],
            scoring={"mode": "options"},
            branching={"show_if": {"question": "licence", "op": "eq", "value": "yes"}},
        ),
        q(
            "years",
            "number",
            config={"min": 0, "max": 50, "unit": "years"},
            scoring={
                "mode": "range",
                "bands": [{"min": 0, "max": 2, "points": 25}, {"min": 3, "max": 50, "points": 100}],
            },
        ),
        q(
            "project",
            "long_text",
            config={"word_limit": 300},
            scoring={"mode": "rubric_text", "keywords": ["django", "testing"]},
        ),
        q("salary", "salary_expectation"),
        q("start", "date", required=False),
    ]
    assert validate_questions(questions) == {}


@pytest.mark.parametrize(
    ("questions", "index", "field"),
    [
        ([q("Bad Key")], "0", "key"),
        ([q("a"), q("a")], "1", "key"),
        ([q("a", "essay")], "0", "type"),
        ([{"key": "a", "type": "yes_no", "prompt": "  "}], "0", "prompt"),
        ([q("a", "single_choice", options=[{"label": "Only", "value": "x"}])], "0", "options"),
        (
            [
                q(
                    "a",
                    "single_choice",
                    options=[{"label": "A", "value": "x"}, {"label": "B", "value": "x"}],
                )
            ],
            "0",
            "options",
        ),
        ([q("a", "number", options=[{"label": "A", "value": "x"}])], "0", "options"),
        ([q("a", "number", config={"min": 10, "max": 1})], "0", "config"),
        ([q("a", "long_text", config={"word_limit": 0})], "0", "config"),
        (
            [
                q(
                    "a",
                    "salary_expectation",
                    scoring={"mode": "range", "bands": [{"min": 0, "max": 1, "points": 1}]},
                )
            ],
            "0",
            "scoring",
        ),
        ([q("a", scoring={"mode": "exact"})], "0", "scoring"),
        ([q("a", scoring={"mode": "exact", "expected": "maybe"})], "0", "scoring"),
        ([q("a", "long_text", scoring={"mode": "rubric_text"})], "0", "scoring"),
        ([q("a", "number", scoring={"mode": "range", "bands": [{"min": 0}]})], "0", "scoring"),
        (
            [
                q(
                    "a",
                    "single_choice",
                    options=[{"label": "A", "value": "a"}, {"label": "B", "value": "b"}],
                    scoring={"mode": "options"},
                )
            ],
            "0",
            "scoring",
        ),
        ([q("a", "yes_no", scoring={"mode": "telepathy"})], "0", "scoring"),
        ([q("a", "long_text", is_knockout=True, knockout_expected="x")], "0", "is_knockout"),
        ([q("a", is_knockout=True)], "0", "is_knockout"),
    ],
)
def test_invalid_definitions(questions: list[dict[str, Any]], index: str, field: str) -> None:
    errors = validate_questions(questions)
    assert field in errors.get(index, {}), errors


def test_branching_must_reference_earlier_questions_no_cycles() -> None:
    forward = [q("a", branching={"show_if": {"question": "b", "op": "eq", "value": "yes"}}), q("b")]
    assert "branching" in validate_questions(forward)["0"]
    self_ref = [q("a", branching={"show_if": {"question": "a", "op": "eq", "value": "yes"}})]
    assert "branching" in validate_questions(self_ref)["0"]
    bad_value = [
        q("a"),
        q("b", branching={"show_if": {"question": "a", "op": "eq", "value": "maybe"}}),
    ]
    assert "branching" in validate_questions(bad_value)["1"]
    bad_op = [
        q("a"),
        q("b", branching={"show_if": {"question": "a", "op": "contains", "value": "yes"}}),
    ]
    assert "branching" in validate_questions(bad_op)["1"]
    answered = [
        q("a", "short_text"),
        q("b", branching={"show_if": {"question": "a", "op": "answered"}}),
    ]
    assert validate_questions(answered) == {}


def test_question_limit() -> None:
    errors = validate_questions([q(f"q{i}") for i in range(61)])
    assert "non_field_errors" in errors["0"]
