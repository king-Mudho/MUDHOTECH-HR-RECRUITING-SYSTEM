"""Job assignments, visibility and reassignment on deactivation (P03-T07, EC-ORG-09)."""

from __future__ import annotations

import pytest

from apps.audit.models import AuditEvent
from apps.core.exceptions import DomainError, PermissionDeniedError
from apps.jobs.assignments import is_assigned, jobs_visible_to, set_assignments
from apps.jobs.tests.factories import JobFactory
from apps.organisations import permissions as perms
from apps.organisations import services as org_services
from apps.organisations.models import Membership
from apps.organisations.tests.factories import OrgTeam, make_org_with_team

pytestmark = pytest.mark.django_db


def m(team: OrgTeam, role: str) -> Membership:
    return Membership.objects.for_org(team.org).get(user=getattr(team, role))


@pytest.fixture
def team() -> OrgTeam:
    return make_org_with_team()


def test_set_assignments_and_visibility(team: OrgTeam) -> None:
    job, other_job = JobFactory(organisation=team.org), JobFactory(organisation=team.org)
    set_assignments(
        job,
        actor=team.hr_manager,
        assignments=[
            {"membership_id": str(m(team, "recruiter").pk), "role_on_job": "recruiter"},
            {"membership_id": str(m(team, "hiring_manager").pk), "role_on_job": "hiring_manager"},
        ],
    )
    assert is_assigned(m(team, "recruiter"), job) and not is_assigned(
        m(team, "recruiter"), other_job
    )
    assert set(jobs_visible_to(m(team, "recruiter"))) == {job}
    assert set(jobs_visible_to(m(team, "hiring_manager"))) == {job}
    assert set(jobs_visible_to(m(team, "hr_manager"))) == {job, other_job}
    assert set(jobs_visible_to(m(team, "admin"))) == {job, other_job}
    assert not jobs_visible_to(m(team, "panelist")).exists()
    assert AuditEvent.objects.filter(action="job.assignments_updated").count() == 1


def test_registered_checker_drives_is_assigned_permission(team: OrgTeam) -> None:
    job = JobFactory(organisation=team.org)
    assert perms._assignment_checker is is_assigned
    set_assignments(
        job,
        actor=team.admin,
        assignments=[{"membership_id": str(m(team, "recruiter").pk), "role_on_job": "recruiter"}],
    )
    assert perms._assignment_checker(m(team, "recruiter"), job)
    assert not perms._assignment_checker(m(team, "hiring_manager"), job)


def test_only_admin_hr_can_assign(team: OrgTeam) -> None:
    job = JobFactory(organisation=team.org)
    payload = [{"membership_id": str(m(team, "recruiter").pk), "role_on_job": "recruiter"}]
    for role in ("recruiter", "hiring_manager", "panelist", "auditor"):
        with pytest.raises(PermissionDeniedError):
            set_assignments(job, actor=getattr(team, role), assignments=payload)


def test_assignment_validation(team: OrgTeam) -> None:
    job = JobFactory(organisation=team.org)
    other = make_org_with_team()
    rec = {"membership_id": str(m(team, "recruiter").pk), "role_on_job": "recruiter"}
    bad = [
        [{"membership_id": str(m(team, "panelist").pk), "role_on_job": "recruiter"}, rec],
        [
            {"membership_id": str(m(other, "recruiter").pk), "role_on_job": "recruiter"}
        ],  # cross-tenant
        [{"membership_id": str(m(team, "recruiter").pk), "role_on_job": "approver"}, rec],
        [{"membership_id": str(m(team, "hiring_manager").pk), "role_on_job": "hiring_manager"}],
    ]
    for payload in bad:
        with pytest.raises(DomainError):
            set_assignments(job, actor=team.hr_manager, assignments=payload)


def test_deactivating_sole_recruiter_lists_job_for_reassignment(team: OrgTeam) -> None:
    """EC-ORG-09."""
    covered, sole = JobFactory(organisation=team.org), JobFactory(organisation=team.org)
    rec = {"membership_id": str(m(team, "recruiter").pk), "role_on_job": "recruiter"}
    hr = {"membership_id": str(m(team, "hr_manager").pk), "role_on_job": "recruiter"}
    set_assignments(covered, actor=team.admin, assignments=[rec, hr])
    set_assignments(sole, actor=team.admin, assignments=[rec])
    result = org_services.deactivate_member(
        membership=m(team, "recruiter"), actor=team.admin, reason="Left the company"
    )
    assert result.needs_reassignment == [
        {"type": "job", "id": str(sole.pk), "title": sole.title, "role": "recruiter"}
    ]
