"""Applicants table (P08-T05, EC-JOB-17): filters, cursor pagination, saved views, bulk."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application, Status
from apps.applications.tests.factories import make_application, published_job
from apps.jobs.models import JobAssignment
from apps.messaging.models import ClarificationRequest
from apps.organisations.models import Membership, OrganisationPolicy
from apps.organisations.tests.factories import make_org_with_team
from apps.shortlisting.models import Shortlist

pytestmark = pytest.mark.django_db


def staff(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


def app_with(job: Any, i: int, **fields: Any) -> Application:
    app = make_application(job, UserFactory(), status=fields.pop("status", Status.UNDER_REVIEW))
    Application.objects.unscoped().filter(pk=app.pk).update(
        candidate_profile_snapshot={"first_name": f"Person{i}", "last_name": "Test"}, **fields
    )
    app.refresh_from_db()
    return app


@pytest.fixture
def world() -> Any:
    team = make_org_with_team()
    OrganisationPolicy.objects.filter(organisation=team.org).update(blind_review_default=False)
    job = published_job(organisation=team.org, title="Software Developer")
    recruiter = Membership.objects.get(user=team.recruiter, organisation=team.org)
    JobAssignment.objects.create(
        organisation=team.org, job=job, membership=recruiter, role_on_job="recruiter"
    )
    apps = {
        "top": app_with(
            job,
            1,
            ai_band="recommended_for_review",
            score=Decimal("91"),
            coverage=Decimal("1"),
            essentials_met=3,
            essentials_unknown=0,
            essentials_not_evidenced=0,
            tags=["priority"],
        ),
        "unsure": app_with(
            job,
            2,
            ai_band="review_needed",
            score=Decimal("55"),
            coverage=Decimal("0.4"),
            essentials_met=1,
            essentials_unknown=2,
            essentials_not_evidenced=0,
            flags=["low_ocr_confidence"],
        ),
        "weak": app_with(
            job,
            3,
            ai_band="lower_match",
            score=Decimal("30"),
            coverage=Decimal("0.8"),
            essentials_met=2,
            essentials_unknown=0,
            essentials_not_evidenced=1,
        ),
        "manual": app_with(job, 4, ai_band="manual_review_requested"),
        "error": app_with(job, 5, status=Status.PROCESSING_ERROR),
    }
    return team, job, apps


def ids(res: Any) -> list[str]:
    return [r["id"] for r in res.json()["results"]]


def test_filters_and_ordering(world: Any) -> None:
    team, job, a = world
    c = staff(team.recruiter, team.org)
    url = f"/api/v1/hr/jobs/{job.pk}/applications/"
    body = c.get(url).json()
    assert body["count"] == 5
    # default: score high to low, unscored last
    assert ids(c.get(url))[:3] == [str(a["top"].pk), str(a["unsure"].pk), str(a["weak"].pk)]
    assert ids(c.get(url, {"band": "review_needed,lower_match"})) == [
        str(a["unsure"].pk),
        str(a["weak"].pk),
    ]
    assert ids(c.get(url, {"min_score": 50})) == [str(a["top"].pk), str(a["unsure"].pk)]
    assert ids(c.get(url, {"coverage_lt": "0.6"})) == [str(a["unsure"].pk)]
    assert ids(c.get(url, {"flags": "low_ocr_confidence"})) == [str(a["unsure"].pk)]
    assert ids(c.get(url, {"essentials": "unknown"})) == [str(a["unsure"].pk)]
    assert ids(c.get(url, {"essentials": "not_evidenced"})) == [str(a["weak"].pk)]
    assert ids(c.get(url, {"essentials": "all_met"})) == [str(a["top"].pk)]
    assert ids(c.get(url, {"tag": "priority"})) == [str(a["top"].pk)]
    assert ids(c.get(url, {"status": "processing_error"})) == [str(a["error"].pk)]
    assert ids(c.get(url, {"ordering": "score"}))[0] == str(a["weak"].pk)
    assert ids(c.get(url, {"ordering": "coverage"}))[0] == str(a["unsure"].pk)
    row = next(r for r in body["results"] if r["id"] == str(a["top"].pk))
    assert row["essentials"] == {"met": 3, "unknown": 0, "not_evidenced": 0}
    assert row["ai_band"] == "recommended_for_review" and row["score"] == 91.0
    manual = next(r for r in body["results"] if r["id"] == str(a["manual"].pk))
    assert manual["score"] is None and manual["essentials"] is None  # EC-AI-12


def test_cursor_pagination_walks_every_row_once(world: Any) -> None:
    team, job, _ = world
    for i in range(12):
        app_with(job, 10 + i, ai_band="review_needed", score=Decimal(str(40 + i % 3)))
    c = staff(team.recruiter, team.org)
    seen: list[str] = []
    cursor = ""
    while True:
        params: dict[str, Any] = {"page_size": 5}
        if cursor:
            params["cursor"] = cursor
        body = c.get(f"/api/v1/hr/jobs/{job.pk}/applications/", params).json()
        assert body["count"] == 17
        seen += [r["id"] for r in body["results"]]
        cursor = body["next_cursor"]
        if not cursor:
            break
    assert len(seen) == 17 and len(set(seen)) == 17


def test_blind_search_matches_reference_only(world: Any) -> None:
    team, job, a = world
    c = staff(team.recruiter, team.org)
    url = f"/api/v1/hr/jobs/{job.pk}/applications/"
    assert ids(c.get(url, {"search": "Person1"})) == [str(a["top"].pk)]
    OrganisationPolicy.objects.filter(organisation=team.org).update(blind_review_default=True)
    assert ids(c.get(url, {"search": "Person1"})) == []  # would reveal who is behind an alias
    ref = a["top"].reference
    assert ids(c.get(url, {"search": ref})) == [str(a["top"].pk)]


def test_saved_views_are_private(world: Any) -> None:
    team, _, _ = world
    mine = staff(team.recruiter, team.org)
    res = mine.post(
        "/api/v1/hr/saved-views/",
        {"name": "Unsure", "params": {"band": "review_needed", "evil": "x", "search": "Rudo"}},
        format="json",
    )
    assert res.status_code == 201
    assert res.json()["params"] == {"band": "review_needed"}  # unknown keys and searches dropped
    dup = mine.post("/api/v1/hr/saved-views/", {"name": "Unsure", "params": {}}, format="json")
    assert dup.status_code == 409
    assert [v["name"] for v in mine.get("/api/v1/hr/saved-views/").json()] == ["Unsure"]
    other = staff(team.hr_manager, team.org)
    assert other.get("/api/v1/hr/saved-views/").json() == []
    view_id = res.json()["id"]
    assert other.delete(f"/api/v1/hr/saved-views/{view_id}/").status_code == 404
    assert mine.delete(f"/api/v1/hr/saved-views/{view_id}/").status_code == 204


def test_bulk_tag_assign_and_clarification(world: Any) -> None:
    team, job, a = world
    c = staff(team.recruiter, team.org)
    url = f"/api/v1/hr/jobs/{job.pk}/applications/bulk/"
    chosen = [str(a["top"].pk), str(a["unsure"].pk)]
    res = c.post(url, {"action": "tag", "application_ids": chosen, "tags": ["Call"]}, format="json")
    assert res.status_code == 200 and res.json()["done"] == 2
    assert set(Application.objects.for_org(team.org).get(pk=a["top"].pk).tags) == {
        "priority",
        "call",
    }
    res = c.post(url, {"action": "assign_me", "application_ids": chosen}, format="json")
    assert res.json()["done"] == 2
    assert (
        Application.objects.for_org(team.org).filter(assigned_recruiter=team.recruiter).count() == 2
    )
    mine = c.get(f"/api/v1/hr/jobs/{job.pk}/applications/", {"assigned": "me"}).json()
    assert mine["count"] == 2 and mine["results"][0]["assigned_name"]
    res = c.post(
        url,
        {
            "action": "clarification",
            "application_ids": chosen,
            "questions": [{"prompt": "Can you share a code sample?"}],
        },
        format="json",
    )
    assert res.json()["done"] == 2
    assert ClarificationRequest.objects.for_org(team.org).count() == 2
    other = make_org_with_team()
    foreign = make_application(published_job(organisation=other.org), UserFactory())
    res = c.post(
        url, {"action": "tag", "application_ids": [str(foreign.pk)], "tags": ["x"]}, format="json"
    )
    assert res.json()["done"] == 0
    assert res.json()["skipped"] == [{"application_id": str(foreign.pk), "reason": "not_found"}]


def test_bulk_propose_shortlist_records_the_person_s_picks(world: Any) -> None:
    team, job, a = world
    c = staff(team.recruiter, team.org)
    res = c.post(
        f"/api/v1/hr/jobs/{job.pk}/applications/bulk/",
        {"action": "propose_shortlist", "application_ids": [str(a["top"].pk), str(a["error"].pk)]},
        format="json",
    )
    body = res.json()
    assert res.status_code == 200 and body["done"] == 1
    assert body["skipped"] == [{"application_id": str(a["error"].pk), "reason": "not_reviewable"}]
    shortlist = Shortlist.objects.for_org(team.org).get(pk=body["shortlist_id"])
    assert shortlist.status == "draft"  # nothing is decided until approval
    entry = shortlist.entries.get(application=a["top"])
    assert entry.decision == "shortlist" and entry.decided_by == team.recruiter
    assert Application.objects.for_org(team.org).get(pk=a["top"].pk).status == "under_review"


def test_hiring_manager_cannot_bulk(world: Any) -> None:
    team, job, a = world
    res = staff(team.hiring_manager, team.org).post(
        f"/api/v1/hr/jobs/{job.pk}/applications/bulk/",
        {"action": "assign_me", "application_ids": [str(a["top"].pk)]},
        format="json",
    )
    assert res.status_code == 403
