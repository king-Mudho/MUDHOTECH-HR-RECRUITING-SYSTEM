"""Platform administration of tenants (SRS §3.1, FR-M02-04, EC-ORG-07/08)."""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.accounts.models import User
from apps.audit import services as audit
from apps.core import outbox, time
from apps.core.exceptions import InvalidTransitionError
from apps.organisations.models import Organisation

Status = Organisation.Status


def _transition(
    org: Organisation,
    *,
    actor: User,
    allowed_from: set[str],
    to: str,
    action: str,
    reason: str,
    request: Any,
    extra: dict[str, Any] | None = None,
) -> Organisation:
    org = Organisation.objects.select_for_update().get(pk=org.pk)
    if org.status not in allowed_from:
        raise InvalidTransitionError(
            details={"from": org.status, "to": to, "allowed_from": sorted(allowed_from)}
        )
    before = {"status": org.status}
    org.status = to
    for key, value in (extra or {}).items():
        setattr(org, key, value)
    org.save()
    audit.record(
        actor=actor,
        action=action,
        target=org,
        before=before,
        after={"status": to},
        reason=reason,
        request=request,
    )
    # Downstream apps react (hide jobs, pause processing, notify) via idempotent consumers.
    outbox.emit(
        action,
        org,
        {"status": to, "reason": reason},
        dedupe_key=f"{action}:{org.pk}:{time.now().isoformat()}",
    )
    return org


@transaction.atomic
def verify_organisation(
    org: Organisation, *, actor: User, reason: str = "", request: Any = None
) -> Organisation:
    """D-01: platform admin verification moves pending orgs to active (enables publishing)."""
    return _transition(
        org,
        actor=actor,
        allowed_from={Status.PENDING_VERIFICATION},
        to=Status.ACTIVE,
        action="organisation.verified",
        reason=reason,
        request=request,
        extra={"verified_at": time.now(), "verified_by": actor},
    )


@transaction.atomic
def suspend_organisation(
    org: Organisation, *, actor: User, reason: str, request: Any = None
) -> Organisation:
    """EC-ORG-07: public jobs hidden, staff read-only, drafts preserved, processing paused."""
    return _transition(
        org,
        actor=actor,
        allowed_from={Status.ACTIVE, Status.PENDING_VERIFICATION},
        to=Status.SUSPENDED,
        action="organisation.suspended",
        reason=reason,
        request=request,
    )


@transaction.atomic
def reactivate_organisation(
    org: Organisation, *, actor: User, reason: str = "", request: Any = None
) -> Organisation:
    target = Status.ACTIVE if org.verified_at else Status.PENDING_VERIFICATION
    return _transition(
        org,
        actor=actor,
        allowed_from={Status.SUSPENDED},
        to=target,
        action="organisation.reactivated",
        reason=reason,
        request=request,
    )


@transaction.atomic
def close_organisation(
    org: Organisation, *, actor: User, reason: str, request: Any = None
) -> Organisation:
    """EC-ORG-10: the organisation leaves the platform.

    Staff become read-only (closed is a read-only state), open vacancies are closed, and every
    candidate with an application still in progress is told the vacancy is closed. Application
    statuses are not changed (no consequential state without a person); the data is kept per the
    organisation's retention policy and then anonymised by the daily retention run, which counts
    from each vacancy's closing date.
    """
    from apps.applications.models import TERMINAL_STATUSES, Application
    from apps.jobs import services as jobs
    from apps.jobs.models import Job
    from apps.notifications.delivery import notify

    org = _transition(
        org,
        actor=actor,
        allowed_from={Status.ACTIVE, Status.SUSPENDED, Status.PENDING_VERIFICATION},
        to=Status.CLOSED,
        action="organisation.closed",
        reason=reason,
        request=request,
    )
    open_jobs = (
        Job.objects.for_org(org.pk)
        .select_for_update()
        .filter(status__in=["published", "paused", "scheduled"])
    )
    for job in open_jobs:
        jobs._close(job, actor, "The employer has closed its account", automatic=False)
    in_progress = (
        Application.objects.for_org(org.pk)
        .exclude(status__in=[*TERMINAL_STATUSES, "draft"])
        .select_related("job", "candidate_user")
    )
    for app in in_progress:
        notify(
            app.candidate_user,
            "organisation_closed",
            {
                "organisation_name": org.name,
                "job_title": app.job.title,
                "reference": app.reference or "",
            },
            dedupe_key=f"organisation_closed:{app.pk}",
            organisation=org,
        )
    return org
