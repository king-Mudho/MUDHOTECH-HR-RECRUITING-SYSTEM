"""Questionnaire services: definition save + protected-topic exceptions (P03-T03/T04)."""

from __future__ import annotations

import pytest

from apps.audit.models import AuditEvent
from apps.core.exceptions import ConflictError, DomainError, PermissionDeniedError
from apps.jobs.tests.factories import JobFactory
from apps.organisations.tests.factories import make_org_with_team
from apps.questionnaires.models import Questionnaire
from apps.questionnaires.services import (
    blocking_questions,
    record_protected_exception,
    replace_questions,
)

pytestmark = pytest.mark.django_db

REASON = "Mining Act requires underground workers to be at least 18 years old."


@pytest.fixture
def setup():  # type: ignore[no-untyped-def]
    team = make_org_with_team()
    job = JobFactory(organisation=team.org)
    qn = Questionnaire.objects.create(organisation=team.org, job_version=job.current_version)
    return team, qn


def _questions() -> list[dict]:  # type: ignore[type-arg]
    return [
        {"key": "age", "type": "number", "prompt": "What is your age?"},
        {
            "key": "licence",
            "type": "single_choice",
            "prompt": "Which driver's licence class do you hold?",
            "options": [
                {"label": "Class 4", "value": "c4", "points": "5"},
                {"label": "Class 2", "value": "c2", "points": 10},
            ],
            "scoring": {"mode": "options"},
        },
    ]


def test_replace_questions_flags_protected_topics(setup) -> None:  # type: ignore[no-untyped-def]
    team, qn = setup
    saved = replace_questions(qn, _questions(), actor=team.recruiter)
    assert [q.key for q in saved] == ["age", "licence"]
    assert saved[0].protected_topic_flag[0]["topic"] == "age"
    assert not saved[1].protected_topic_flag
    assert saved[1].options.count() == 2
    assert [q.key for q in blocking_questions(qn)] == ["age"]


def test_replace_rejects_invalid_definition(setup) -> None:  # type: ignore[no-untyped-def]
    team, qn = setup
    with pytest.raises(DomainError) as exc:
        replace_questions(qn, [{"key": "x", "type": "essay", "prompt": "?"}], actor=team.recruiter)
    assert "type" in exc.value.details["0"]


def test_hr_manager_records_exception_audited(setup) -> None:  # type: ignore[no-untyped-def]
    team, qn = setup
    age = replace_questions(qn, _questions(), actor=team.recruiter)[0]
    record_protected_exception(age, actor=team.hr_manager, reason=REASON)
    age.refresh_from_db()
    assert not age.blocks_publishing and blocking_questions(qn) == []
    event = AuditEvent.objects.get(action="question.protected_exception_recorded")
    assert event.reason == REASON and event.target_id == str(age.pk)


@pytest.mark.parametrize("role", ["recruiter", "hiring_manager", "panelist", "auditor"])
def test_other_roles_cannot_record_exception(setup, role: str) -> None:  # type: ignore[no-untyped-def]
    team, qn = setup
    age = replace_questions(qn, _questions(), actor=team.recruiter)[0]
    with pytest.raises(PermissionDeniedError):
        record_protected_exception(age, actor=getattr(team, role), reason=REASON)


def test_cross_tenant_manager_cannot_record_exception(setup) -> None:  # type: ignore[no-untyped-def]
    team, qn = setup
    other = make_org_with_team()
    age = replace_questions(qn, _questions(), actor=team.recruiter)[0]
    with pytest.raises(PermissionDeniedError):
        record_protected_exception(age, actor=other.hr_manager, reason=REASON)


def test_exception_requires_reason_and_flag(setup) -> None:  # type: ignore[no-untyped-def]
    team, qn = setup
    age, licence = replace_questions(qn, _questions(), actor=team.recruiter)
    with pytest.raises(DomainError):
        record_protected_exception(age, actor=team.hr_manager, reason="because")
    with pytest.raises(DomainError):
        record_protected_exception(licence, actor=team.hr_manager, reason=REASON)


def test_exception_survives_resave_but_not_rewording(setup) -> None:  # type: ignore[no-untyped-def]
    team, qn = setup
    age = replace_questions(qn, _questions(), actor=team.recruiter)[0]
    record_protected_exception(age, actor=team.hr_manager, reason=REASON)
    resaved = replace_questions(qn, _questions(), actor=team.recruiter)
    assert resaved[0].protected_exception_reason == REASON
    reworded = _questions()
    reworded[0]["prompt"] = "How old are you?"
    assert replace_questions(qn, reworded, actor=team.recruiter)[0].blocks_publishing


def test_approved_questionnaire_is_locked(setup) -> None:  # type: ignore[no-untyped-def]
    team, qn = setup
    age = replace_questions(qn, _questions(), actor=team.recruiter)[0]
    qn.status = Questionnaire.Status.APPROVED
    qn.save()
    with pytest.raises(ConflictError):
        replace_questions(qn, _questions(), actor=team.recruiter)
    with pytest.raises(ConflictError):
        record_protected_exception(age, actor=team.hr_manager, reason=REASON)
