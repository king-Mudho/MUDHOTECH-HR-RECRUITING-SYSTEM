"""Prohibited-question linter (P03-T04, FR-M08-06) - positive and negative samples."""

from __future__ import annotations

import pytest

from apps.questionnaires.linter import TOPICS, lint_question, lint_text


@pytest.mark.parametrize(
    ("prompt", "topic"),
    [
        ("What is your age?", "age"),
        ("Please state your date of birth", "age"),
        ("How old are you?", "age"),
        ("Which church do you attend?", "religion"),
        ("What is your religion?", "religion"),
        ("What is your tribe?", "tribe_ethnicity"),
        ("What is your totem (mutupo)?", "tribe_ethnicity"),
        ("Are you married?", "marital_family"),
        ("What is your marital status?", "marital_family"),
        ("How many children do you have?", "marital_family"),
        ("Are you pregnant or planning to have children?", "pregnancy"),
        ("What is your HIV status?", "health_hiv"),
        ("Do you have any chronic illness?", "health_hiv"),
        ("Do you have a disability?", "disability"),
        ("Which political party do you support?", "political"),
        ("Are you a ZANU-PF member?", "political"),
        ("Do you hold an MDC or CCC party card?", "political"),
        ("Please upload a recent photo", "appearance"),
        ("What is your national ID number?", "national_id"),
        ("What is your gender?", "gender_sex"),
    ],
)
def test_flags_protected_topics(prompt: str, topic: str) -> None:
    topics = {w.topic for w in lint_question(prompt)}
    assert topic in topics, (prompt, topics)


@pytest.mark.parametrize(
    "prompt",
    [
        "How many years of Python experience do you have?",
        "Do you hold a valid class 4 driver's licence?",
        "Are you legally permitted to work in Zimbabwe?",
        "Describe a project where you used Django REST Framework.",
        "What is your notice period?",
        "Are you willing to relocate to Bulawayo?",
        "Which programming languages are you most comfortable with?",
        "Can you work night shifts as required by the role?",
        "Describe your experience with single sign-on (SSO).",
        "Do you have experience managing a team?",
        "What is your expected salary range?",
    ],
)
def test_job_related_questions_pass(prompt: str) -> None:
    assert lint_question(prompt) == [], prompt


def test_help_text_and_options_are_checked_and_deduplicated() -> None:
    warnings = lint_question(
        "Tell us about yourself",
        help_text="Include your age and marital status",
        options=["Married", "Single", "Prefer not to say"],
    )
    topics = sorted(w.topic for w in warnings)
    assert topics == ["age", "marital_family"]
    fields = {w.topic: w.field for w in warnings}
    assert fields["age"] == "help_text"


def test_warning_payload_explains_why() -> None:
    [warning] = lint_text("What is your religion?")
    payload = warning.as_dict()
    assert set(payload) == {"topic", "matched", "explanation", "field"}
    assert payload["matched"].lower() == "religion"
    assert "protected" in payload["explanation"]


def test_every_topic_has_explanation_and_patterns() -> None:
    for topic, (explanation, patterns) in TOPICS.items():
        assert explanation and patterns, topic
    assert lint_text("") == []
