"""Phase 12 exit criterion, end to end through the HTTP API.

shortlisted -> interview (candidate books a slot) -> panel scorecards -> offer approved -> issued ->
accepted by the candidate (the recruiter who issued it is told) -> hire recorded -> vacancy closed
-> remaining applicants told after a confirmed close-out. Every step goes through the same endpoints
the UI uses, with the role that would do it in practice, and the candidate only ever sees their own
interview and offer.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.applications.models import Application, Status
from apps.applications.tests.factories import make_application, published_job
from apps.core import time as mhrs_time
from apps.interviews.models import Interview
from apps.jobs.models import Job, JobAssignment, JobStatus
from apps.notifications.models import Notification
from apps.offers.models import HireRecord
from apps.organisations.models import Membership
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


def staff(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


def ok(resp: Any, status: int = 200) -> Any:
    assert resp.status_code == status, (resp.status_code, resp.content[:500])
    return resp.json() if resp.content else None


def later(days: int, hour: int = 9) -> str:
    moment = mhrs_time.now() + timedelta(days=days)
    return moment.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


def keys(user: Any) -> set[str]:
    return set(Notification.objects.filter(recipient_user=user).values_list("key", flat=True))


def test_shortlisted_to_hired_and_vacancy_closed(s3: Any) -> None:
    team = make_org_with_team()
    job = published_job(organisation=team.org)
    members = {m.user_id: m for m in Membership.objects.for_org(team.org)}
    JobAssignment.objects.create(
        organisation=team.org,
        job=job,
        membership=members[team.recruiter.pk],
        role_on_job="recruiter",
    )
    chosen = make_application(job, status=Status.SHORTLISTED)
    candidate_user = chosen.candidate_user
    candidate_user.first_name, candidate_user.last_name = "Rudo", "Chikore"
    candidate_user.save()
    others = [make_application(job, status=s) for s in (Status.UNDER_REVIEW, Status.SHORTLISTED)]

    recruiter = staff(team.recruiter, team.org)
    hr = staff(team.hr_manager, team.org)
    candidate = APIClient()
    candidate.force_login(candidate_user)

    # 1. interview with two proposed times; the panel is the HR manager (lead) + a panelist
    template = ok(
        recruiter.post(
            f"/api/v1/hr/jobs/{job.pk}/scorecard-templates/",
            {"name": "Technical", "extra_competencies": ["Communication"]},
            format="json",
        ),
        201,
    )
    created = ok(
        recruiter.post(
            f"/api/v1/hr/applications/{chosen.pk}/interviews/",
            {
                "stage": "Technical",
                "mode": "video",
                "slots": [later(3), later(4)],
                "video_link": "https://meet.example.test/hire-flow",
                "scorecard_template_id": template["id"],
                "panel": [
                    {"membership_id": str(members[team.hr_manager.pk].pk), "role": "lead"},
                    {"membership_id": str(members[team.panelist.pk].pk), "role": "member"},
                ],
            },
            format="json",
        ),
        201,
    )
    interview_id = created["interview"]["id"] if "interview" in created else created["id"]
    assert "interview_invitation" in keys(candidate_user)

    # 2. the candidate books the second time and can download the calendar file
    mine = ok(candidate.get(f"/api/v1/applications/{chosen.pk}/interviews/"))
    assert [i["id"] for i in mine] == [interview_id]
    slot = mine[0]["slots"][1]["id"]
    booked = ok(
        candidate.post(f"/api/v1/interviews/{interview_id}/book/", {"slot_id": slot}, format="json")
    )
    assert booked["status"] == "scheduled" and booked["video_link"]
    assert candidate.get(f"/api/v1/interviews/{interview_id}/calendar.ics").status_code == 200
    chosen.refresh_from_db()
    assert chosen.status == Status.INTERVIEW

    # 3. the interview takes place (move it into the past instead of waiting three days), then both
    #    panelists submit scorecards and HR sees the consolidated feedback
    Interview.objects.filter(pk=interview_id).update(
        starts_at=mhrs_time.now() - timedelta(hours=2), ends_at=mhrs_time.now() - timedelta(hours=1)
    )
    criteria = [c["key"] for c in template["criteria"]]
    for user in (team.panelist, team.hr_manager):
        ok(
            staff(user, team.org).post(
                f"/api/v1/hr/interviews/{interview_id}/scorecard/submit/",
                {
                    "scores": dict.fromkeys(criteria, 4),
                    "criterion_notes": dict.fromkeys(criteria, "Clear, worked examples."),
                    "overall": 4,
                    "recommendation": "yes",
                    "notes": "Solid technical interview.",
                },
                format="json",
            )
        )
    feedback = ok(hr.get(f"/api/v1/hr/interviews/{interview_id}/feedback/"))
    assert feedback["submitted"] == feedback["panel_size"] == 2 and feedback["outstanding"] == []
    ok(hr.post(f"/api/v1/hr/interviews/{interview_id}/complete/", {}, format="json"))

    # 4. offer drafted by the recruiter, approved by HR, then issued (never issued unapproved)
    offer = ok(
        recruiter.post(
            f"/api/v1/hr/applications/{chosen.pk}/offers/",
            {
                "salary_amount": "1800.00",
                "currency": "USD",
                "period": "month",
                "start_date": (mhrs_time.now() + timedelta(days=30)).date().isoformat(),
                "contract_type": "full_time",
                "expires_at": later(7, 15),
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        ),
        201,
    )
    oid = offer["id"]
    early = recruiter.post(
        f"/api/v1/hr/offers/{oid}/issue/", {}, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4())
    )
    assert early.status_code in (409, 422)  # EC-OFF-01
    for client, step in ((recruiter, "submit"), (hr, "approve"), (recruiter, "issue")):
        ok(
            client.post(
                f"/api/v1/hr/offers/{oid}/{step}/",
                {},
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            )
        )
    chosen.refresh_from_db()
    assert chosen.status == Status.OFFER and "offer_issued" in keys(candidate_user)

    # 5. the candidate signs and accepts; HR is told
    seen = ok(candidate.get(f"/api/v1/applications/{chosen.pk}/offers/"))
    assert seen[0]["status"] == "issued" and seen[0]["letter_document_id"]
    accepted = ok(
        candidate.post(
            f"/api/v1/offers/{oid}/accept/",
            {"typed_name": "Rudo Chikore", "agree": True},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
    )
    assert accepted["status"] == "accepted" and "offer_accepted" in keys(team.recruiter)

    # 6. HR records the hire: application hired, hire record, welcome, prompt to close
    hire = ok(
        hr.post(
            f"/api/v1/hr/offers/{oid}/hire/",
            {"note": "Contract signed"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        ),
        201,
    )
    assert hire["prompt_close"] is True
    chosen.refresh_from_db()
    assert chosen.status == Status.HIRED
    assert HireRecord.objects.for_org(team.org).filter(application=chosen).exists()
    assert "hired_welcome" in keys(candidate_user)

    # 7. close the vacancy (a separate, deliberate action), then confirm the close-out
    ok(hr.post(f"/api/v1/hr/jobs/{job.pk}/close/", {"reason": "Position filled"}, format="json"))
    assert Job.objects.for_org(team.org).get(pk=job.pk).status == JobStatus.CLOSED
    preview = ok(hr.get(f"/api/v1/hr/jobs/{job.pk}/closeout/"))
    assert preview["to_notify"] == len(others)
    result = ok(
        hr.post(
            f"/api/v1/hr/jobs/{job.pk}/closeout/",
            {"fingerprint": preview["fingerprint"]},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
    )
    assert result["notified"] == len(others) and result["skipped"] == []
    statuses = set(
        Application.objects.for_org(team.org)
        .filter(pk__in=[a.pk for a in others])
        .values_list("status", flat=True)
    )
    assert statuses == {Status.NOT_SELECTED}

    # the funnel on the dashboard tells the same story
    funnel = ok(hr.get(f"/api/v1/hr/jobs/{job.pk}/funnel/"))
    stages = {s["stage"]: s["count"] for s in funnel["stages"]}
    assert stages["interviewed"] == stages["offered"] == stages["hired"] == 1
