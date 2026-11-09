"""Job assignments (P03-T07): who works on which vacancy.

* org_admin / hr_manager see every vacancy of their organisation.
* recruiters and hiring managers see only vacancies they are assigned to.
* EC-ORG-09: deactivating the last recruiter on an open vacancy lists it for reassignment.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import QuerySet

from apps.audit import services as audit
from apps.core.exceptions import DomainError, PermissionDeniedError
from apps.organisations import rbac
from apps.organisations.models import Membership, Role
from apps.organisations.selectors import active_membership

from .models import Job, JobAssignment, JobStatus

OPEN_STATUSES = (
    JobStatus.DRAFT,
    JobStatus.IN_REVIEW,
    JobStatus.APPROVED,
    JobStatus.SCHEDULED,
    JobStatus.PUBLISHED,
    JobStatus.PAUSED,
)
# Which organisation roles may hold each role on a job.
ELIGIBLE_ROLES: dict[str, frozenset[str]] = {
    JobAssignment.RoleOnJob.RECRUITER: rbac.RECRUITING,
    JobAssignment.RoleOnJob.HIRING_MANAGER: frozenset(
        {Role.ORG_ADMIN, Role.HR_MANAGER, Role.RECRUITER, Role.HIRING_MANAGER}
    ),
    JobAssignment.RoleOnJob.APPROVER: rbac.ADMIN_HR,
}


def is_assigned(membership: Membership, job: Any) -> bool:
    return (
        JobAssignment.objects.for_org(membership.organisation_id)
        .filter(job_id=job.pk, membership=membership)
        .exists()
    )


def jobs_visible_to(membership: Membership) -> QuerySet[Job]:
    qs = Job.objects.for_org(membership.organisation_id)
    if membership.role in rbac.ADMIN_HR:
        return qs
    if membership.role not in {Role.RECRUITER, Role.HIRING_MANAGER}:
        return qs.none()
    return qs.filter(assignments__membership=membership).distinct()


def needs_reassignment(membership: Membership) -> list[dict[str, Any]]:
    """Open vacancies on which ``membership`` was the only active recruiter."""
    items = []
    assigned = (
        JobAssignment.objects.for_org(membership.organisation_id)
        .filter(membership=membership, role_on_job=JobAssignment.RoleOnJob.RECRUITER)
        .filter(job__status__in=OPEN_STATUSES)
        .select_related("job")
    )
    for a in assigned:
        others = (
            JobAssignment.objects.for_org(membership.organisation_id)
            .filter(job=a.job, role_on_job=JobAssignment.RoleOnJob.RECRUITER)
            .exclude(membership=membership)
            .filter(membership__status=Membership.Status.ACTIVE)
        )
        if not others.exists():
            items.append(
                {"type": "job", "id": str(a.job_id), "title": a.job.title, "role": "recruiter"}
            )
    return items


@transaction.atomic
def set_assignments(
    job: Job, *, actor: Any, assignments: list[dict[str, Any]]
) -> list[JobAssignment]:
    """Replace the assignment list (PUT /hr/jobs/{id}/assignments). HR manager / admin only."""
    actor_membership = active_membership(actor, job.organisation_id)
    if actor_membership is None or actor_membership.role not in rbac.ADMIN_HR:
        raise PermissionDeniedError()
    job = Job.objects.for_org(job.organisation_id).select_for_update().get(pk=job.pk)
    wanted: set[tuple[str, str]] = set()
    errors: dict[str, dict[str, list[str]]] = {}
    members = {
        str(m.pk): m
        for m in Membership.objects.for_org(job.organisation_id).filter(
            pk__in=[a.get("membership_id") for a in assignments if a.get("membership_id")],
            status=Membership.Status.ACTIVE,
        )
    }
    for i, a in enumerate(assignments):
        role_on_job = a.get("role_on_job")
        member = members.get(str(a.get("membership_id")))
        if role_on_job not in JobAssignment.RoleOnJob.values:
            errors.setdefault(str(i), {})["role_on_job"] = ["Unknown role."]
        elif member is None:
            errors.setdefault(str(i), {})["membership_id"] = ["Not an active team member."]
        elif member.role not in ELIGIBLE_ROLES[role_on_job]:
            errors.setdefault(str(i), {})["membership_id"] = [
                f"A {member.get_role_display().lower()} cannot be assigned as {role_on_job}."
            ]
        else:
            wanted.add((str(member.pk), role_on_job))
    if errors:
        raise DomainError("validation_error", "Fix the highlighted assignments.", details=errors)
    if job.status in OPEN_STATUSES and not any(r == "recruiter" for _, r in wanted):
        raise DomainError(
            "validation_error",
            "An open vacancy needs at least one recruiter.",
            details={"assignments": ["Assign at least one recruiter."]},
        )
    existing = {
        (str(a.membership_id), a.role_on_job): a
        for a in JobAssignment.objects.for_org(job.organisation_id).filter(job=job)
    }
    removed = [a for key, a in existing.items() if key not in wanted]
    for a in removed:
        a.delete()
    for member_id, role_on_job in wanted - set(existing):
        JobAssignment.objects.create(
            organisation=job.organisation,
            job=job,
            membership=members[member_id],
            role_on_job=role_on_job,
        )
    audit.record(
        actor=actor,
        action="job.assignments_updated",
        target=job,
        before={"assignments": sorted(f"{m}:{r}" for m, r in existing)},
        after={"assignments": sorted(f"{m}:{r}" for m, r in wanted)},
    )
    return list(
        JobAssignment.objects.for_org(job.organisation_id)
        .filter(job=job)
        .select_related("membership__user")
    )
