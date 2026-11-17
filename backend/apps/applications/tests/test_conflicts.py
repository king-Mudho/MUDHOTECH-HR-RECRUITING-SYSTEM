"""Role visibility and conflicts of interest (P08-T09; EC-REV-09, EC-REV-11, EC-ACC-09/10)."""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application, ConflictDeclaration, Status
from apps.applications.tests.factories import make_application, published_job
from apps.audit.models import AuditEvent
from apps.jobs.models import JobAssignment
from apps.organisations.models import Membership, OrganisationPolicy
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


def staff(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


@pytest.fixture
def world() -> Any:
    team = make_org_with_team()
    OrganisationPolicy.objects.filter(organisation=team.org).update(blind_review_default=False)
    job = published_job(organisation=team.org, title="Software Developer")
    for user, role in ((team.recruiter, "recruiter"), (team.hiring_manager, "hiring_manager")):
        JobAssignment.objects.create(
            organisation=team.org,
            job=job,
            membership=Membership.objects.get(user=user, organisation=team.org),
            role_on_job=role,
        )
    review = make_application(job, UserFactory(), status=Status.UNDER_REVIEW)
    short = make_application(job, UserFactory(), status=Status.SHORTLISTED)
    return team, job, review, short


def listed(client: APIClient, job: Any) -> set[str]:
    return {
        r["id"] for r in client.get(f"/api/v1/hr/jobs/{job.pk}/applications/").json()["results"]
    }


def test_hiring_manager_sees_the_shortlist_only_unless_granted(world: Any) -> None:
    team, job, review, short = world
    hm = staff(team.hiring_manager, team.org)
    assert listed(hm, job) == {str(short.pk)}  # EC-REV-09
    assert hm.get(f"/api/v1/hr/applications/{review.pk}/").status_code == 404
    assert hm.get(f"/api/v1/hr/applications/{short.pk}/").status_code == 200
    JobAssignment.objects.filter(job=job, role_on_job="hiring_manager").update(sees_full_pool=True)
    assert listed(hm, job) == {str(review.pk), str(short.pk)}
    assert listed(staff(team.recruiter, team.org), job) == {str(review.pk), str(short.pk)}


def test_hiring_manager_cannot_be_mentioned_on_hidden_applications(world: Any) -> None:
    team, _, review, _ = world
    res = staff(team.recruiter, team.org).post(
        f"/api/v1/hr/applications/{review.pk}/notes/",
        {"body": "Have a look", "mentions": [str(team.hiring_manager.pk)]},
        format="json",
    )
    assert res.status_code == 400  # they cannot see it, so they cannot be pulled in


def test_declared_conflict_hides_the_application_and_unassigns(world: Any) -> None:
    team, job, review, _ = world
    Application.objects.unscoped().filter(pk=review.pk).update(assigned_recruiter=team.recruiter)
    rec = staff(team.recruiter, team.org)
    url = f"/api/v1/hr/applications/{review.pk}/declare-conflict/"
    assert rec.post(url, {"reason": ""}, format="json").status_code == 400
    res = rec.post(url, {"reason": "She is my cousin"}, format="json")
    assert res.status_code == 201
    assert str(review.pk) not in listed(rec, job)
    assert rec.get(f"/api/v1/hr/applications/{review.pk}/").status_code == 404
    review.refresh_from_db()
    assert review.assigned_recruiter_id is None  # EC-REV-11: reassigned
    event = AuditEvent.objects.get(action="application.conflict_declared")
    assert event.actor_id == team.recruiter.pk and event.reason == "She is my cousin"
    # colleagues still see it
    assert str(review.pk) in listed(staff(team.hr_manager, team.org), job)
    assert ConflictDeclaration.objects.for_org(team.org).count() == 1


def test_staff_cannot_open_their_own_application(world: Any) -> None:
    team, job, review, _ = world
    own = make_application(job, team.recruiter, status=Status.UNDER_REVIEW)
    rec = staff(team.recruiter, team.org)
    res = rec.get(f"/api/v1/hr/applications/{own.pk}/")
    assert res.status_code == 403 and res.json()["error"]["code"] == "conflict_of_interest"
    assert AuditEvent.objects.filter(action="application.conflict_blocked").exists()
    # EC-ACC-10: no access to that vacancy's applications at all
    assert listed(rec, job) == set()
    assert rec.get(f"/api/v1/hr/applications/{review.pk}/").status_code == 404
    # HR managers still see everything, including the staff application
    assert str(own.pk) in listed(staff(team.hr_manager, team.org), job)


def test_staff_applications_are_for_hr_managers_only(world: Any) -> None:
    team, _job, _, _ = world
    other_job = published_job(organisation=team.org, title="Analyst")
    JobAssignment.objects.create(
        organisation=team.org,
        job=other_job,
        membership=Membership.objects.get(user=team.recruiter, organisation=team.org),
        role_on_job="recruiter",
    )
    colleague = make_application(other_job, team.panelist, status=Status.UNDER_REVIEW)
    assert str(colleague.pk) not in listed(staff(team.recruiter, team.org), other_job)
    assert str(colleague.pk) in listed(staff(team.hr_manager, team.org), other_job)
    assert str(colleague.pk) in listed(staff(team.admin, team.org), other_job)
