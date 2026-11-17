"""Evaluating applications (P07-T09): versioned, idempotent, explainable, never consequential."""

from __future__ import annotations

import json
from typing import Any

import pytest
from django.db import connection

from apps.applications.models import Application, ApplicationStatusEvent, Status
from apps.applications.services import transition
from apps.audit.models import AuditEvent
from apps.core.models import OutboxEvent
from apps.questionnaires.models import QuestionResponse
from apps.resumes.models import ClaimCorrection, ExtractedClaim
from apps.screening import services
from apps.screening.models import CriterionResult, Evaluation, EvaluationEvidence, Trigger

pytestmark = pytest.mark.django_db


def answer(app: Application, question: Any, value: Any) -> None:
    QuestionResponse.objects.create(
        organisation_id=app.organisation_id, application=app, question=question, value=value
    )


def test_full_evaluation_is_stored_explained_and_moves_to_review(
    read_app: Application, vacancy: Any
) -> None:
    assert read_app.status == Status.PROCESSING
    answer(read_app, vacancy.knockout, "yes")
    answer(read_app, vacancy.years, 7)
    evaluation = services.evaluate_application(read_app.pk)
    assert evaluation is not None and evaluation.version == 1
    assert evaluation.status == Evaluation.Status.SUCCEEDED
    assert evaluation.band == "recommended_for_review" and evaluation.total_score > 70
    assert float(evaluation.coverage) == 1.0
    results = {
        r.criterion_id: r
        for r in CriterionResult.objects.for_org(read_app.organisation_id).filter(
            evaluation=evaluation
        )
    }
    python = results[vacancy.criteria["python"].pk]
    assert python.assessable and python.score in (75, 100)  # listed 75 (2026.11.2) / used 100
    assert python.evidence_status == "explicit"
    evidence = EvaluationEvidence.objects.for_org(read_app.organisation_id).filter(
        criterion_result=python
    )
    assert evidence.exists() and evidence.first().claim_id is not None

    read_app.refresh_from_db()
    assert read_app.status == Status.UNDER_REVIEW  # system move; never a consequential status
    assert read_app.ai_band == "recommended_for_review"
    assert (
        read_app.current_evaluation_id == evaluation.pk and read_app.score == evaluation.total_score
    )
    last = ApplicationStatusEvent.objects.filter(application=read_app).order_by("-at").first()
    assert last.actor_type == "system" and last.to_status == Status.UNDER_REVIEW
    assert OutboxEvent.objects.filter(event_type="screening.completed").count() == 1
    assert AuditEvent.objects.filter(action="screening.evaluated").exists()

    sentences = json.loads(evaluation.explanation)
    assert sentences and all(s["citations"] or s["kind"] == "gap" for s in sentences)
    with connection.cursor() as cursor:
        cursor.execute("SELECT explanation FROM screening_evaluation")
        raw = cursor.fetchone()[0]
    assert "Granite Labs" not in raw and "Python" not in raw  # encrypted at rest


def test_idempotent_and_versioned(read_app: Application, vacancy: Any) -> None:
    first = services.evaluate_application(read_app.pk)
    assert first is not None
    assert services.evaluate_application(read_app.pk) is None  # same input, nothing new
    again = services.evaluate_application(
        read_app.pk, force=True, trigger=Trigger.MANUAL, reason="HR asked for a re-run"
    )
    assert again is not None and again.version == 2 and again.trigger == Trigger.MANUAL
    first.refresh_from_db()
    assert first.status == Evaluation.Status.SUPERSEDED  # kept, not overwritten
    assert Evaluation.objects.for_org(read_app.organisation_id).count() == 2


def test_candidate_correction_creates_a_new_version(read_app: Application, vacancy: Any) -> None:
    services.evaluate_application(read_app.pk)
    python_claim = next(
        c
        for c in ExtractedClaim.objects.for_org(read_app.organisation_id).filter(claim_type="skill")
        if c.skill_id == str(vacancy.criteria["python"].skill_id)
    )
    ClaimCorrection.objects.create(
        organisation_id=read_app.organisation_id,
        claim=python_claim,
        corrected_by=read_app.candidate_user,
        payload=json.dumps({"type": "skill", "fields": {}, "remove": True}),
    )
    second = services.evaluate_application(read_app.pk, trigger=Trigger.CORRECTION)
    assert second is not None and second.version == 2
    python = CriterionResult.objects.for_org(read_app.organisation_id).get(
        evaluation=second, criterion=vacancy.criteria["python"]
    )
    # the listed skill is gone; Django in the duties still implies Python (inferred, capped)
    assert python.evidence_status in ("inferred", "missing")


def test_knockout_routes_to_eligibility_review(read_app: Application, vacancy: Any) -> None:
    answer(read_app, vacancy.knockout, "no")
    evaluation = services.evaluate_application(read_app.pk)
    assert evaluation is not None and evaluation.band == "eligibility_review"
    read_app.refresh_from_db()
    assert read_app.status == Status.UNDER_REVIEW  # a person decides


# EC-AI-12: objection to automated processing -> manual_review_requested
def test_objection_gives_manual_review_and_withdrawn_is_skipped(vacancy: Any, act: Any) -> None:
    from apps.applications.models import Application as App
    from apps.resumes import services as resumes
    from apps.resumes.tests.test_extraction_flow import attach, submitted_app

    app = submitted_app(org=vacancy.team.org, objection=True)
    App.objects.unscoped().filter(pk=app.pk).update(
        job=vacancy.job, job_version=vacancy.job.published_version
    )
    app.refresh_from_db()
    attach(app)
    act(resumes.start, app.pk)
    evaluation = services.evaluate_application(app.pk)
    assert evaluation is not None and evaluation.band == "manual_review_requested"
    transition(app, Status.WITHDRAWN, actor=app.candidate_user, reason="Taking another offer")
    assert services.evaluate_application(app.pk, force=True) is None


def test_final_failure_parks_the_application(read_app: Application) -> None:
    services.mark_failed(read_app.pk, "RuntimeError")
    read_app.refresh_from_db()
    assert read_app.status == Status.PROCESSING_ERROR
    assert AuditEvent.objects.filter(action="screening.failed").exists()


# EC-AI-11 / EC-AI-10: redelivered task (acks_late) is idempotent per input - no new version
def test_task_and_consumer_gate(read_app: Application, settings: Any) -> None:
    from apps.screening.tasks import evaluate_application

    assert evaluate_application.apply(args=(str(read_app.pk),)).get() == "v1"
    assert evaluate_application.apply(args=(str(read_app.pk),)).get() == "skipped"
    assert evaluate_application.acks_late  # a dead worker's task is redelivered, not lost


def test_llm_gate_requires_flag_policy_and_provider(read_app: Application, settings: Any) -> None:
    from apps.core.models import FeatureFlag

    assert services.llm_service(read_app).enabled is False  # defaults: off
    settings.LLM_PROVIDER = "anthropic"
    assert services.llm_service(read_app).enabled is False  # no platform flag, no org policy
    FeatureFlag.objects.create(key="llm", enabled=True)
    policy = read_app.organisation.policy
    policy.llm_enabled = True
    policy.save()
    read_app.organisation.refresh_from_db()
    from django.core.cache import cache

    cache.clear()
    assert services.llm_service(read_app).enabled is True


def test_tenant_scoping(read_app: Application) -> None:
    from apps.organisations.tests.factories import make_org_with_team

    services.evaluate_application(read_app.pk)
    other = make_org_with_team().org
    assert Evaluation.objects.for_org(other.pk).count() == 0
    assert CriterionResult.objects.for_org(other.pk).count() == 0
