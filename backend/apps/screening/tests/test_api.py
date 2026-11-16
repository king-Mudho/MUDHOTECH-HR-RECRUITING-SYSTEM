"""HR screening API (P07-T10/T11/T12): runs, versions, verification, analytics."""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application, Status
from apps.applications.tests.factories import make_application
from apps.audit.models import AuditEvent
from apps.screening import runs, services
from apps.screening.models import (
    CriterionResult,
    Evaluation,
    EvaluationEvidence,
    HumanVerification,
    ScreeningRun,
)

pytestmark = pytest.mark.django_db


def staff(vacancy: Any) -> APIClient:
    c = APIClient()
    c.force_login(vacancy.team.hr_manager)
    c.credentials(HTTP_X_ORG_ID=str(vacancy.team.org.pk))
    return c


def post(c: APIClient, capture: Any, url: str, data: dict[str, Any]) -> Any:
    with capture(execute=True):
        return c.post(url, data, format="json")


def runs_url(vacancy: Any) -> str:
    return f"/api/v1/hr/jobs/{vacancy.job.pk}/screening-runs/"


def python_claim(app: Application, vacancy: Any) -> Any:
    result = CriterionResult.objects.for_org(app.organisation_id).get(
        evaluation__application=app,
        evaluation__status=Evaluation.Status.SUCCEEDED,
        criterion=vacancy.criteria["python"],
    )
    return (
        EvaluationEvidence.objects.for_org(app.organisation_id)
        .filter(criterion_result=result)
        .first()
        .claim_id
    )


def test_run_evaluates_pending_and_reports_progress(
    read_app: Application, vacancy: Any, django_capture_on_commit_callbacks: Any
) -> None:
    c = staff(vacancy)
    res = post(c, django_capture_on_commit_callbacks, runs_url(vacancy), {"scope": "pending"})
    assert res.status_code == 201, res.json()
    assert res.json()["total"] == 1 and res.json()["trigger"] == "manual"
    run = c.get(f"/api/v1/hr/screening-runs/{res.json()['id']}/").json()
    assert run["status"] == "completed" and run["done"] == 1 and run["progress"] == 1.0
    assert run["failures"] == []
    assert c.get(runs_url(vacancy)).json()[0]["id"] == run["id"]
    assert AuditEvent.objects.filter(action="screening.run_started").exists()

    body = c.get(f"/api/v1/hr/applications/{read_app.pk}/evaluation/").json()
    assert body["version"] == 1 and body["ai_notice"].startswith("AI-assisted suggestion")
    python = next(x for x in body["criteria"] if x["title"].lower().startswith("python"))
    assert python["evidence"] and python["evidence"][0]["snippet"]
    assert body["explanation"]

    # pending scope now selects nothing; the run completes immediately
    again = post(c, django_capture_on_commit_callbacks, runs_url(vacancy), {"scope": "pending"})
    assert again.json()["total"] == 0 and again.json()["status"] == "completed"


def test_failed_scope_retries_processing_errors(
    read_app: Application, vacancy: Any, django_capture_on_commit_callbacks: Any
) -> None:
    services.mark_failed(read_app.pk, "Boom")
    read_app.refresh_from_db()
    assert read_app.status == Status.PROCESSING_ERROR
    c = staff(vacancy)
    res = post(c, django_capture_on_commit_callbacks, runs_url(vacancy), {"scope": "failed"})
    assert res.json()["total"] == 1
    read_app.refresh_from_db()
    assert read_app.status == Status.UNDER_REVIEW and read_app.current_evaluation_id


def test_reevaluation_needs_a_reason_and_keeps_superseded_versions(
    read_app: Application, vacancy: Any, django_capture_on_commit_callbacks: Any
) -> None:
    services.evaluate_application(read_app.pk)
    c = staff(vacancy)
    url = runs_url(vacancy)
    bad = post(
        c, django_capture_on_commit_callbacks, url, {"scope": "all", "use_current_version": True}
    )
    assert bad.status_code == 400 and "reason" in bad.json()["error"]["details"]
    ok = post(
        c,
        django_capture_on_commit_callbacks,
        url,
        {"scope": "all", "use_current_version": True, "reason": "Rubric clarified"},
    )
    assert ok.status_code == 201 and ok.json()["trigger"] == "reevaluation"
    versions = c.get(f"/api/v1/hr/applications/{read_app.pk}/evaluations/").json()
    assert [v["version"] for v in versions] == [2, 1]
    assert [v["status"] for v in versions] == ["succeeded", "superseded"]
    assert versions[0]["trigger"] == "reevaluation"
    old = c.get(f"/api/v1/hr/applications/{read_app.pk}/evaluations/1/")
    assert old.status_code == 200 and old.json()["status"] == "superseded"
    assert c.get(f"/api/v1/hr/applications/{read_app.pk}/evaluations/9/").status_code == 404
    assert Evaluation.objects.for_org(read_app.organisation_id).get(version=2).reason == (
        "Rubric clarified"
    )


def test_selected_scope_requires_ids(vacancy: Any, django_capture_on_commit_callbacks: Any) -> None:
    res = post(
        staff(vacancy), django_capture_on_commit_callbacks, runs_url(vacancy), {"scope": "selected"}
    )
    assert res.status_code == 400


def test_dispatch_chunks_and_counts(vacancy: Any, monkeypatch: Any) -> None:
    from apps.screening import tasks

    sent: list[tuple[Any, ...]] = []
    monkeypatch.setattr(tasks.evaluate_application, "delay", lambda *a: sent.append(a))
    run = ScreeningRun.objects.create(
        organisation=vacancy.team.org,
        job=vacancy.job,
        job_version=vacancy.job.published_version,
        engine_version="x",
        total=120,
    )
    ids = [f"id-{i}" for i in range(120)]
    assert runs.dispatch(run.pk, ids) == 120 and len(sent) == 120
    assert sent[0][1] == "manual" and sent[0][4] is None  # no version override unless re-evaluating
    for _ in range(119):
        runs.record(run, failed=False)
    run.refresh_from_db()
    assert run.finished_at is None
    runs.record(run, failed=True)
    run.refresh_from_db()
    assert run.status == "failed" and run.done == 120 and run.failed == 1 and run.finished_at


def test_confirmed_claim_becomes_human_verified_in_a_new_version(
    read_app: Application, vacancy: Any, django_capture_on_commit_callbacks: Any
) -> None:
    services.evaluate_application(read_app.pk)
    claim_id = python_claim(read_app, vacancy)
    c = staff(vacancy)
    res = post(
        c,
        django_capture_on_commit_callbacks,
        f"/api/v1/hr/claims/{claim_id}/verify/",
        {"decision": "confirmed", "reevaluate": True},
    )
    assert res.status_code == 201, res.json()
    assert res.json()["decision"] == "confirmed"
    body = c.get(f"/api/v1/hr/applications/{read_app.pk}/evaluation/").json()
    assert body["version"] == 2 and body["trigger"] == "verification"
    python = next(x for x in body["criteria"] if x["title"].lower().startswith("python"))
    assert python["evidence_status"] == "human_verified"
    assert HumanVerification.objects.for_org(read_app.organisation_id).count() == 1
    assert AuditEvent.objects.filter(action="screening.claim_verified").exists()
    listed = c.get(f"/api/v1/hr/applications/{read_app.pk}/verifications/").json()
    assert listed[0]["claim_id"] == str(claim_id)


def test_rejecting_needs_a_note_and_drops_the_claim(
    read_app: Application, vacancy: Any, django_capture_on_commit_callbacks: Any
) -> None:
    services.evaluate_application(read_app.pk)
    claim_id = python_claim(read_app, vacancy)
    c = staff(vacancy)
    url = f"/api/v1/hr/claims/{claim_id}/verify/"
    assert (
        post(c, django_capture_on_commit_callbacks, url, {"decision": "rejected"}).status_code
        == 400
    )
    res = post(
        c,
        django_capture_on_commit_callbacks,
        url,
        {"decision": "rejected", "note": "Not in the portfolio", "reevaluate": True},
    )
    assert res.status_code == 201
    evaluation = Evaluation.objects.for_org(read_app.organisation_id).get(
        application=read_app, status=Evaluation.Status.SUCCEEDED
    )
    assert evaluation.version == 2
    ids = set(
        EvaluationEvidence.objects.for_org(read_app.organisation_id)
        .filter(criterion_result__evaluation=evaluation)
        .values_list("claim_id", flat=True)
    )
    assert claim_id not in ids


def test_correction_rejects_unknown_or_locked_fields(
    read_app: Application, vacancy: Any, django_capture_on_commit_callbacks: Any
) -> None:
    services.evaluate_application(read_app.pk)
    claim_id = python_claim(read_app, vacancy)
    url = f"/api/v1/hr/claims/{claim_id}/verify/"
    c = staff(vacancy)
    for values in ({}, {"type": "education"}, {"salary": 1}):
        res = post(
            c, django_capture_on_commit_callbacks, url, {"decision": "corrected", "values": values}
        )
        assert res.status_code == 400, values
    assert not HumanVerification.objects.for_org(read_app.organisation_id).exists()


def test_manual_review_band_hides_scores(read_app: Application, vacancy: Any) -> None:
    evaluation = services.evaluate_application(read_app.pk)
    Evaluation.objects.for_org(read_app.organisation_id).filter(pk=evaluation.pk).update(
        band="manual_review_requested"
    )
    c = staff(vacancy)
    body = c.get(f"/api/v1/hr/applications/{read_app.pk}/evaluation/").json()
    assert body["total_score"] is None and body["criteria"] == [] and body["explanation"] == []
    listed = c.get(f"/api/v1/hr/applications/{read_app.pk}/evaluations/").json()
    assert listed[0]["total_score"] is None


def _evaluation(app: Application, *, score: float, coverage: float, band: str) -> None:
    Evaluation.objects.create(
        organisation_id=app.organisation_id,
        application=app,
        job_version=app.job_version,
        version=1,
        total_score=score,
        coverage=coverage,
        band=band,
        input_hash=str(app.pk),
        engine_version="x",
    )


def test_analytics_distribution_and_warnings(vacancy: Any) -> None:
    apps = [
        make_application(vacancy.job, UserFactory(), status=Status.UNDER_REVIEW) for _ in range(6)
    ]
    for i, app in enumerate(apps):
        _evaluation(app, score=90 + i, coverage=0.4, band="review_needed")
    c = staff(vacancy)
    body = c.get(f"/api/v1/hr/jobs/{vacancy.job.pk}/screening-analytics/").json()
    assert body["evaluated"] == 6 and body["median_score"] == 92.5
    assert {b["band"]: b["count"] for b in body["bands"]}["review_needed"] == 6
    assert body["score_buckets"][9] == {"start": 90, "end": 100, "count": 6}
    assert {w["code"] for w in body["warnings"]} == {"low_coverage", "high_score_saturation"}
    assert "cut-off" in next(w for w in body["warnings"] if w["code"].startswith("high"))["message"]


def test_analytics_small_sample_has_no_warnings(vacancy: Any) -> None:
    app = make_application(vacancy.job, UserFactory(), status=Status.UNDER_REVIEW)
    _evaluation(app, score=95, coverage=0.1, band="review_needed")
    body = staff(vacancy).get(f"/api/v1/hr/jobs/{vacancy.job.pk}/screening-analytics/").json()
    assert body["evaluated"] == 1 and body["warnings"] == []
