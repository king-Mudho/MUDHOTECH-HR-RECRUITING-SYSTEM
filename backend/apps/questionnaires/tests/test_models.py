"""Questionnaire model invariants (P03-T03)."""

from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, transaction

from apps.jobs.tests.factories import JobFactory
from apps.questionnaires.models import Question, Questionnaire, QuestionOption, QuestionResponse

pytestmark = pytest.mark.django_db


def _questionnaire() -> Questionnaire:
    job = JobFactory()
    return Questionnaire.objects.create(
        organisation=job.organisation, job_version=job.current_version
    )


def test_question_keys_unique_per_questionnaire_and_option_values_unique() -> None:
    qn = _questionnaire()
    q = Question.objects.create(
        organisation=qn.organisation, questionnaire=qn, key="licence", type="yes_no", prompt="?"
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        Question.objects.create(
            organisation=qn.organisation, questionnaire=qn, key="licence", type="yes_no", prompt="?"
        )
    QuestionOption.objects.create(organisation=qn.organisation, question=q, label="A", value="a")
    with pytest.raises(IntegrityError), transaction.atomic():
        QuestionOption.objects.create(
            organisation=qn.organisation, question=q, label="B", value="a"
        )


def test_one_response_per_question_per_application() -> None:
    qn = _questionnaire()
    q = Question.objects.create(
        organisation=qn.organisation, questionnaire=qn, key="a", type="yes_no", prompt="?"
    )
    app_id = uuid.uuid4()
    QuestionResponse.objects.create(organisation=qn.organisation, application_id=app_id, question=q)
    with pytest.raises(IntegrityError), transaction.atomic():
        QuestionResponse.objects.create(
            organisation=qn.organisation, application_id=app_id, question=q
        )


def test_flagged_question_blocks_publishing_until_exception_reason() -> None:
    qn = _questionnaire()
    q = Question(
        organisation=qn.organisation,
        questionnaire=qn,
        key="age",
        type="number",
        prompt="How old are you?",
        protected_topic_flag=[{"topic": "age"}],
    )
    assert q.blocks_publishing
    q.protected_exception_reason = "Statutory minimum age 18 for mine underground work."
    assert not q.blocks_publishing


def test_job_version_has_at_most_one_questionnaire() -> None:
    qn = _questionnaire()
    with pytest.raises(IntegrityError), transaction.atomic():
        Questionnaire.objects.create(organisation=qn.organisation, job_version=qn.job_version)
