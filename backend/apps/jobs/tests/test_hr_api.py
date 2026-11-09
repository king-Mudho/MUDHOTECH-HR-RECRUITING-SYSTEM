"""HR vacancy APIs (P03-T11): end-to-end flow, validation envelopes, locks and visibility."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.core.time import now
from apps.jobs.models import Job, JobStatus
from apps.jobs.tests.test_services import CRITERIA, QUESTIONS, draft_job
from apps.organisations.models import Membership
from apps.organisations.tests.factories import LocationFactory, OrgTeam

pytestmark = pytest.mark.django_db


def client_for(team: OrgTeam, role: str) -> APIClient:
    c = APIClient()
    c.force_login(getattr(team, role))
    c.credentials(HTTP_X_ORG_ID=str(team.org.pk))
    return c


def test_recruiter_creates_hr_approves_and_job_goes_public(team: OrgTeam) -> None:
    """Exit criterion 1 through the API."""
    rec, hr = client_for(team, "recruiter"), client_for(team, "hr_manager")
    loc = LocationFactory(organisation=team.org)
    res = rec.post(
        "/api/v1/hr/jobs/",
        {
            "title": "Software Developer",
            "closes_at": (now() + timedelta(days=14)).isoformat(),
            "location_ids": [str(loc.pk)],
            "summary": "Build and maintain web applications.",
            "responsibilities_html": "<p>Write <strong>tested</strong> code</p>",
            "required_documents": ["cv"],
            "salary_min": "900.00",
            "salary_max": "1500.00",
            "salary_currency": "USD",
        },
        format="json",
    )
    assert res.status_code == 201, res.content
    job_id = res.json()["id"]
    url = f"/api/v1/hr/jobs/{job_id}"
    assert rec.put(f"{url}/criteria/", {"criteria": CRITERIA}, format="json").status_code == 200
    assert (
        rec.put(f"{url}/questionnaire/", {"questions": QUESTIONS}, format="json").status_code == 200
    )
    lint = rec.post(f"{url}/lint/?stage=submit").json()
    assert lint["ready"] is True
    assert (
        rec.post(f"{url}/submit-for-approval/", {}, format="json").json()["status"] == "in_review"
    )
    assert hr.post(f"{url}/approve/", {"comment": "Looks good"}, format="json").json()[
        "status"
    ] == ("approved")
    body = hr.post(f"{url}/publish/").json()
    assert body["status"] == JobStatus.PUBLISHED and body["published_version_number"] == 1
    public = APIClient().get("/api/v1/jobs/?q=software developer").json()
    assert [r["id"] for r in public["results"]] == [job_id]
    events = [e["action"] for e in rec.get(f"{url}/events/").json()]
    assert events == ["created", "submitted", "approved", "published"]


def test_detail_includes_version_criteria_rubric_questions(team: OrgTeam) -> None:
    job = draft_job(team)
    body = client_for(team, "recruiter").get(f"/api/v1/hr/jobs/{job.pk}/").json()
    assert body["version"]["number"] == 1 and body["lock_version"] == job.lock_version
    assert [c["title"] for c in body["criteria"]] == ["Python", "2 years web development"]
    assert body["rubric"]["total_weight"] == 100
    assert [q["key"] for q in body["questions"]] == ["portfolio"]


def test_validation_errors_use_envelope(team: OrgTeam) -> None:
    rec = client_for(team, "recruiter")
    job = draft_job(team)
    res = rec.post("/api/v1/hr/jobs/", {"title": "X", "organisation": "evil"}, format="json")
    assert res.status_code == 400 and res.json()["error"]["code"] == "validation_error"
    res = rec.put(
        f"/api/v1/hr/jobs/{job.pk}/criteria/",
        {"criteria": [{"type": "skill", "importance": "essential", "title": "Go"}]},
        format="json",
    )
    assert res.status_code == 400
    assert "justification" in res.json()["error"]["details"]["0"]
    rubric = [{"key": "technical", "weight": 90, "bands": [{"score": 0, "descriptor": "x"}]}]
    res = rec.put(f"/api/v1/hr/jobs/{job.pk}/rubric/", {"categories": rubric}, format="json")
    assert res.status_code == 400 and "total_weight" in res.json()["error"]["details"]


def test_stale_lock_returns_409(team: OrgTeam) -> None:
    """EC-JOB-07."""
    job = draft_job(team)
    rec, hr = client_for(team, "recruiter"), client_for(team, "hr_manager")
    url = f"/api/v1/hr/jobs/{job.pk}/"
    ok = rec.patch(url, {"lock_version": job.lock_version, "openings": 2}, format="json")
    assert ok.status_code == 200 and ok.json()["openings"] == 2
    stale = hr.patch(url, {"lock_version": job.lock_version, "openings": 3}, format="json")
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "conflict.stale_version"
    missing = hr.patch(url, {"openings": 3}, format="json")
    assert missing.status_code == 400


def test_publish_blocked_returns_checklist(team: OrgTeam) -> None:
    """EC-JOB-01."""
    rec = client_for(team, "recruiter")
    job_id = rec.post("/api/v1/hr/jobs/", {"title": "Accountant"}, format="json").json()["id"]
    res = rec.post(f"/api/v1/hr/jobs/{job_id}/submit-for-approval/", {}, format="json")
    assert res.status_code == 422 and res.json()["error"]["code"] == "job_not_ready"
    failing = {c["id"] for c in res.json()["error"]["details"]["checks"]}
    assert {"description", "essential_criterion", "deadline"} <= failing


def test_invalid_transition_409(team: OrgTeam) -> None:
    job = draft_job(team)
    res = client_for(team, "hr_manager").post(f"/api/v1/hr/jobs/{job.pk}/pause/", {}, format="json")
    assert res.status_code == 409 and res.json()["error"]["code"] == "conflict.invalid_transition"


def test_unassigned_recruiter_cannot_see_job(team: OrgTeam) -> None:
    from apps.accounts.tests.factories import UserFactory
    from apps.organisations.tests.factories import MembershipFactory

    job = draft_job(team)
    other = UserFactory()
    MembershipFactory(organisation=team.org, user=other, role="recruiter")
    c = APIClient()
    c.force_login(other)
    c.credentials(HTTP_X_ORG_ID=str(team.org.pk))
    assert c.get(f"/api/v1/hr/jobs/{job.pk}/").status_code == 404
    assert c.get("/api/v1/hr/jobs/").json()["count"] == 0
    hr = client_for(team, "hr_manager")
    membership = Membership.objects.for_org(team.org).get(user=other)
    res = hr.put(
        f"/api/v1/hr/jobs/{job.pk}/assignments/",
        {"assignments": [{"membership_id": str(membership.pk), "role_on_job": "recruiter"}]},
        format="json",
    )
    assert res.status_code == 200
    assert c.get(f"/api/v1/hr/jobs/{job.pk}/").status_code == 200


def test_list_filters(team: OrgTeam) -> None:
    a = draft_job(team)
    b = draft_job(team)
    Job.objects.for_org(team.org).filter(pk=b.pk).update(status="archived", title="Nurse")
    hr = client_for(team, "hr_manager")
    ids = lambda res: [r["id"] for r in res.json()["results"]]  # noqa: E731
    assert ids(hr.get("/api/v1/hr/jobs/?status=draft")) == [str(a.pk)]
    assert ids(hr.get("/api/v1/hr/jobs/?search=nurse")) == [str(b.pk)]
    assert len(ids(hr.get("/api/v1/hr/jobs/?status=draft,archived&ordering=title"))) == 2
    assert ids(client_for(team, "recruiter").get("/api/v1/hr/jobs/?assigned=me")) == [
        str(b.pk),
        str(a.pk),
    ] or set(ids(client_for(team, "recruiter").get("/api/v1/hr/jobs/?assigned=me"))) == {
        str(a.pk),
        str(b.pk),
    }


def test_protected_exception_endpoint(team: OrgTeam) -> None:
    job = draft_job(team)
    rec = client_for(team, "recruiter")
    rec.put(
        f"/api/v1/hr/jobs/{job.pk}/questionnaire/",
        {
            "questions": [
                *QUESTIONS,
                {"key": "age", "type": "number", "prompt": "What is your age?"},
            ]
        },
        format="json",
    )
    body: dict[str, Any] = rec.get(f"/api/v1/hr/jobs/{job.pk}/").json()
    assert body["questions"][1]["protected_topic_flag"][0]["topic"] == "age"
    hr = client_for(team, "hr_manager")
    url = f"/api/v1/hr/jobs/{job.pk}/questions/%s/protected-exception/"
    reason = {"reason": "Statutory minimum age applies to this licensed role."}
    assert hr.post(url % "nope", reason, format="json").status_code == 404
    res = hr.post(url % "age", reason, format="json")
    assert res.status_code == 200 and res.json()["protected_exception_reason"]
    assert rec.post(url % "age", reason, format="json").status_code == 403


def test_ai_suggestions_disabled_by_default(team: OrgTeam) -> None:
    job = draft_job(team)
    res = client_for(team, "recruiter").post(f"/api/v1/hr/jobs/{job.pk}/ai-suggestions/")
    assert res.status_code == 403 and res.json()["error"]["code"] == "feature_disabled"


def test_versions_and_new_version(team: OrgTeam) -> None:
    from apps.jobs.tests.test_services import published_job

    job = published_job(team)
    hr = client_for(team, "hr_manager")
    res = hr.post(
        f"/api/v1/hr/jobs/{job.pk}/new-version/", {"reason": "Update requirements"}, format="json"
    )
    assert res.status_code == 201 and res.json()["version"]["number"] == 2
    assert res.json()["published_version_number"] == 1
    versions = hr.get(f"/api/v1/hr/jobs/{job.pk}/versions/").json()
    assert [(v["number"], v["status"]) for v in versions] == [(2, "draft"), (1, "approved")]
