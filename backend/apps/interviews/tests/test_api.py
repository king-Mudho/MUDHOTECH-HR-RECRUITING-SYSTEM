"""P12-T06: interview API behaviour beyond the role matrix - panel-only visibility, conflict
warnings, candidate endpoints (own interviews only, booking, calendar file).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Status
from apps.applications.tests.factories import make_application, published_job
from apps.core import time as mhrs_time
from apps.interviews import scheduling
from apps.organisations.models import Membership
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


def staff(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


@pytest.fixture
def ctx() -> dict[str, Any]:
    from apps.jobs.models import JobAssignment

    team = make_org_with_team()
    job = published_job(organisation=team.org)
    app = make_application(job, status=Status.SHORTLISTED)
    members = {m.user_id: m for m in Membership.objects.for_org(team.org)}
    for user, role in ((team.recruiter, "recruiter"), (team.hiring_manager, "hiring_manager")):
        JobAssignment.objects.create(
            organisation=team.org, job=job, membership=members[user.pk], role_on_job=role
        )
    return {"team": team, "app": app, "lead": members[team.hr_manager.pk]}


def at(hours: int) -> str:
    return (mhrs_time.now() + timedelta(hours=hours)).replace(microsecond=0).isoformat()


def test_create_returns_conflict_warnings(ctx: dict[str, Any]) -> None:
    team = ctx["team"]
    client = staff(team.recruiter, team.org)
    body = {
        "stage": "Technical",
        "mode": "video",
        "starts_at": at(48),
        "panel": [{"membership_id": str(ctx["lead"].pk), "role": "lead"}],
    }
    first = client.post(f"/api/v1/hr/applications/{ctx['app'].pk}/interviews/", body, format="json")
    assert first.status_code == 201 and first.json()["conflicts"] == []
    other = make_application(ctx["app"].job, status=Status.SHORTLISTED)
    second = client.post(f"/api/v1/hr/applications/{other.pk}/interviews/", body, format="json")
    assert second.status_code == 201 and len(second.json()["conflicts"]) == 1  # EC-INT-01
    bad = client.post(
        f"/api/v1/hr/applications/{other.pk}/interviews/",
        {**body, "panel": [{"membership_id": str(make_org_with_team().org.pk)}]},
        format="json",
    )
    assert bad.status_code == 422


def test_panelist_sees_only_interviews_they_sit_on(ctx: dict[str, Any]) -> None:
    team = ctx["team"]
    iv = scheduling.create_interview(
        ctx["app"],
        actor=team.recruiter,
        stage="Technical",
        mode="video",
        panel=[(ctx["lead"], "lead")],
        starts_at=mhrs_time.now() + timedelta(days=2),
    ).interview
    panelist = staff(team.panelist, team.org)
    assert panelist.get(f"/api/v1/hr/interviews/{iv.pk}/").status_code == 404
    assert panelist.get("/api/v1/hr/interviews/").json()["count"] == 0
    hm = staff(team.hiring_manager, team.org)  # view_all, application visible (interview stage)
    assert hm.get(f"/api/v1/hr/interviews/{iv.pk}/").status_code == 200
    lead = staff(team.hr_manager, team.org).get(f"/api/v1/hr/interviews/{iv.pk}/").json()
    assert lead["on_panel"] is True and lead["ai"] is None  # ADR-019 default


def test_candidate_endpoints(ctx: dict[str, Any]) -> None:
    team, app = ctx["team"], ctx["app"]
    iv = scheduling.create_interview(
        app,
        actor=team.recruiter,
        stage="Technical",
        mode="video",
        panel=[(ctx["lead"], "lead")],
        slots=[mhrs_time.now() + timedelta(days=2), mhrs_time.now() + timedelta(days=3)],
        video_link="https://meet.example.test/abc",
    ).interview
    me = APIClient()
    me.force_login(app.candidate_user)
    rows = me.get(f"/api/v1/applications/{app.pk}/interviews/").json()
    assert len(rows) == 1 and len(rows[0]["slots"]) == 2 and rows[0]["video_link"] == ""
    assert me.get(f"/api/v1/interviews/{iv.pk}/calendar.ics").status_code == 409  # not booked yet
    stranger = APIClient()
    stranger.force_login(UserFactory())
    assert stranger.get(f"/api/v1/applications/{app.pk}/interviews/").json() == []
    slot = rows[0]["slots"][1]["id"]
    assert (
        stranger.post(
            f"/api/v1/interviews/{iv.pk}/book/", {"slot_id": slot}, format="json"
        ).status_code
        == 404
    )
    booked = me.post(f"/api/v1/interviews/{iv.pk}/book/", {"slot_id": slot}, format="json")
    assert booked.status_code == 200 and booked.json()["status"] == "scheduled"
    assert booked.json()["video_link"] == "https://meet.example.test/abc"  # shown once scheduled
    ics = me.get(f"/api/v1/interviews/{iv.pk}/calendar.ics")
    assert ics.status_code == 200 and ics["Content-Type"].startswith("text/calendar")
    assert b"BEGIN:VCALENDAR" in ics.content and ics["Cache-Control"] == "no-store"
