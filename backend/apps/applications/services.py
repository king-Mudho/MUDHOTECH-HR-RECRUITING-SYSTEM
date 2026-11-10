"""Application services (P04-T05 onwards).

Duplicate policy (``OrganisationPolicy.duplicate_policy``, D-04):
* ``one_active`` - one active application per vacancy; withdrawn/abandoned ones free the slot
  (EC-APP-02/03). Enforced by the ``active_key`` partial unique constraint.
* ``allow_resubmit_replace`` - one active at a time; submitting a new one replaces the previous
  (handled at submit, P04-T08).
* ``allow_multiple`` - no restriction (``active_key`` stays NULL).
"""

from __future__ import annotations

import re
from typing import Any

from django.db import IntegrityError, transaction

from apps.audit import services as audit
from apps.core.exceptions import DomainError
from apps.core.time import now
from apps.jobs.models import Job, JobStatus
from apps.organisations.models import DuplicatePolicy, Organisation, OrganisationPolicy

from .models import INACTIVE_STATUSES, Application, ReferenceCounter, Status


class DuplicateApplicationError(DomainError):
    code = "conflict.duplicate_application"
    status_code = 409
    default_message = "You have already applied for this vacancy."


def org_code(org: Organisation) -> str:
    """Upper-case code for references, from the slug ('mudhotech-demo-ltd' -> 'MUDHOTEC')."""
    return (re.sub(r"[^A-Z0-9]", "", org.slug.upper()) or "ORG")[:8]


def next_reference(org: Organisation, year: int | None = None) -> str:
    """``MHRS-<ORG>-<YYYY>-<NNNNNN>``; gap-free per org and year under concurrency (row lock)."""
    year = year or now().year
    with transaction.atomic():
        counter, _ = ReferenceCounter.objects.for_org(org).get_or_create(
            organisation=org, year=year
        )
        counter = ReferenceCounter.objects.for_org(org).select_for_update().get(pk=counter.pk)
        counter.last_value += 1
        counter.save(update_fields=["last_value", "updated_at"])
        return f"MHRS-{org_code(org)}-{year}-{counter.last_value:06d}"


def duplicate_policy(org: Any) -> str:
    policy = OrganisationPolicy.objects.filter(organisation=org).first()
    return policy.duplicate_policy if policy else DuplicatePolicy.ONE_ACTIVE


def active_key_for(application: Application) -> str | None:
    if application.status in INACTIVE_STATUSES:
        return None
    if duplicate_policy(application.organisation_id) == DuplicatePolicy.ALLOW_MULTIPLE:
        return None
    return f"{application.job_id}:{application.candidate_user_id}"


def active_application(job: Job, user: Any) -> Application | None:
    return (
        Application.objects.for_org(job.organisation_id)
        .filter(job=job, candidate_user=user)
        .exclude(status__in=INACTIVE_STATUSES)
        .order_by("-created_at")
        .first()
    )


def _open_for_applications(job: Job) -> None:
    if job.status != JobStatus.PUBLISHED or job.published_version_id is None:
        raise DomainError(
            "job_not_accepting",
            "This vacancy is not accepting applications.",
            status_code=422,
        )
    if job.closes_at is not None and job.closes_at <= now():
        raise DomainError(
            "deadline_passed", "The closing date for this vacancy has passed.", status_code=422
        )


@transaction.atomic
def start_or_resume_draft(
    job: Job, user: Any, *, source: dict[str, Any] | None = None
) -> tuple[Application, bool]:
    """Return ``(application, created)``. An existing draft is resumed (EC-APP-02); a submitted
    application under a one-active policy is a 409 that links to it."""
    job = Job.objects.unscoped().select_related("organisation").get(pk=job.pk)
    _open_for_applications(job)
    policy = duplicate_policy(job.organisation_id)
    existing = active_application(job, user)
    if existing is not None:
        if existing.status == Status.DRAFT:
            return existing, False
        if policy == DuplicatePolicy.ONE_ACTIVE:
            raise DuplicateApplicationError(
                details={"application_id": str(existing.pk), "reference": existing.reference}
            )
    assert job.published_version_id is not None  # guaranteed by _open_for_applications
    app = Application(
        organisation_id=job.organisation_id,
        job=job,
        job_version_id=job.published_version_id,
        candidate_user=user,
        source=source or {},
    )
    # allow_resubmit_replace keeps the submitted one active until the new draft is submitted.
    has_active_submitted = existing is not None and existing.status != Status.DRAFT
    app.active_key = None if has_active_submitted else active_key_for(app)
    try:
        with transaction.atomic():
            app.save()
    except IntegrityError:  # a concurrent request created the active application first
        existing = active_application(job, user)
        if existing is not None and existing.status == Status.DRAFT:
            return existing, False
        raise DuplicateApplicationError(
            details={"application_id": str(existing.pk) if existing else None}
        ) from None
    audit.record(
        actor=user,
        action="application.draft_started",
        target=app,
        organisation=job.organisation_id,
        after={"job_id": str(job.pk)},
    )
    return app, True


# ------------------------------------------------------------------------------ state machine
class ApplicationTransitionError(DomainError):
    code = "conflict.invalid_transition"
    status_code = 409
    default_message = "This status change is not allowed."


def _actor_kind(application: Application, actor: Any, actor_type: str) -> str:
    """Resolve and authorise who is acting: candidate (owner), staff (member) or system."""
    from apps.organisations import rbac
    from apps.organisations.selectors import active_membership

    from . import state_machine as sm

    if actor_type == "system":
        if actor is not None:
            raise ApplicationTransitionError(message="System transitions have no human actor.")
        return sm.SYSTEM
    if actor is None or not getattr(actor, "is_authenticated", False):
        raise ApplicationTransitionError(message="A signed-in person must make this change.")
    membership = active_membership(actor, application.organisation_id)
    if membership is not None and rbac.can(membership.role, "applications.transition"):
        return sm.STAFF
    if application.candidate_user_id == actor.pk:
        return sm.CANDIDATE
    from apps.core.exceptions import PermissionDeniedError

    raise PermissionDeniedError()


def transition(
    application: Application,
    to: str,
    *,
    actor: Any = None,
    actor_type: str = "human",
    reason: str = "",
    reason_code: str = "",
    metadata: dict[str, Any] | None = None,
) -> Application:
    """The only way to change an application's status (backend/CLAUDE.md rule 3)."""
    from apps.core import outbox
    from apps.organisations import rbac
    from apps.organisations.selectors import active_membership

    from . import state_machine as sm
    from .models import ApplicationStatusEvent

    with transaction.atomic():
        app = (
            Application.objects.for_org(application.organisation_id)
            .select_for_update()
            .get(pk=application.pk)
        )
        frm = app.status
        rule = sm.rule_for(frm, to)
        if rule is None:
            raise ApplicationTransitionError(
                details={"from": frm, "to": to, "allowed": sm.allowed_targets(frm)}
            )
        kind = _actor_kind(app, actor, actor_type)
        if kind not in rule.actors:
            raise ApplicationTransitionError(
                message="You can't make this status change.",
                details={"from": frm, "to": to, "actor": kind},
            )
        text = (reason or "").strip()
        if rule.reason_required and len(text) < 5:
            raise DomainError(
                "validation_error",
                "A reason is required for this decision.",
                details={"reason": ["At least 5 characters."]},
            )
        if sm.is_reopen(frm, to):
            membership = active_membership(actor, app.organisation_id)
            if membership is None or membership.role not in rbac.ADMIN_HR:
                from apps.core.exceptions import PermissionDeniedError

                raise PermissionDeniedError(message="Only HR managers can reopen an application.")
        stamp = now()
        app.status = to
        if to == Status.WITHDRAWN:
            app.withdrawn_at = stamp
            app.withdraw_reason = text[:2000]
        new_key = active_key_for(app)
        if new_key != app.active_key:
            app.active_key = new_key
        app.lock_version += 1
        try:
            with transaction.atomic():
                app.save()
        except IntegrityError as exc:
            if "uniq_active_application" not in str(exc):
                raise
            # e.g. reopening while the candidate already has a newer active application
            raise ApplicationTransitionError(
                message="The candidate already has another active application for this vacancy."
            ) from None
        is_human = kind != sm.SYSTEM
        event = ApplicationStatusEvent.objects.create(
            organisation_id=app.organisation_id,
            application=app,
            from_status=frm,
            to_status=to,
            actor=actor if is_human else None,
            actor_type="human" if is_human else "system",
            reason_code=reason_code[:40],
            reason_text=text,
            metadata={**(metadata or {}), "actor_kind": kind},
            at=stamp,
        )
        audit.record(
            actor=actor if is_human else None,
            actor_type="human" if is_human else "system",
            action="application.status_changed",
            target=app,
            organisation=app.organisation_id,
            before={"status": frm},
            after={"status": to, "actor_kind": kind},
            reason=text,
        )
        outbox.emit(
            "application.status_changed",
            app,
            {
                "application_id": str(app.pk),
                "job_id": str(app.job_id),
                "from": frm,
                "to": to,
                "actor_kind": kind,
                "event_id": str(event.pk),
            },
            dedupe_key=f"application.status_changed:{app.pk}:{event.pk}",
            organisation_id=app.organisation_id,
        )
    return app
