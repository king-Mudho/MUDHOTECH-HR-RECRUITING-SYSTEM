"""Assisted applications (P04-T11, FR-M07-08, EC-APP-17/18).

A recruiter submits on behalf of a person who needs help (no internet, accessibility). The candidate
still owns the account and the application; the staff member is recorded as the actor, the
application is flagged ``is_assisted`` and the consent record names how consent was given. The
candidate is invited to the account (set-password link) so they can follow or withdraw it.
MVP requires an email address (EC-APP-18).
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.accounts.models import User, normalize_email_address
from apps.audit import services as audit
from apps.core.email import queue_email
from apps.core.exceptions import DomainError, PermissionDeniedError
from apps.jobs.models import Job, JobAssignment
from apps.organisations import rbac
from apps.organisations.selectors import active_membership

from . import services
from .models import Application

CONSENT_METHODS = ("in_person", "phone", "written")


def _authorise(staff: Any, job: Job) -> None:
    membership = active_membership(staff, job.organisation_id)
    if membership is None or not rbac.can(membership.role, "applications.transition"):
        raise PermissionDeniedError()
    if membership.role in rbac.ADMIN_HR:
        return
    assigned = JobAssignment.objects.for_org(job.organisation_id).filter(
        job=job, membership=membership
    )
    if not assigned.exists():
        raise PermissionDeniedError(message="You are not assigned to this vacancy.")


def _candidate(email: str, first_name: str, last_name: str) -> tuple[User, bool]:
    email = normalize_email_address(email)
    user = User.objects.filter(email__iexact=email).first()
    if user is not None:
        return user, False
    user = User.objects.create_user(email=email, password=None)  # unusable until they set one
    user.first_name, user.last_name = first_name[:150], last_name[:150]
    user.save(update_fields=["first_name", "last_name"])
    return user, True


def _invite(user: User, job: Job, staff: Any, created: bool) -> None:
    from allauth.account.adapter import get_adapter
    from allauth.account.forms import default_token_generator
    from allauth.account.utils import user_pk_to_url_str

    lines = [
        f"Hello {user.first_name or ''},",
        "",
        f"{staff.full_name or 'A recruiter'} submitted your application for {job.title} "
        f"at {job.organisation.name} on your behalf, as you agreed.",
    ]
    if created or not user.has_usable_password():
        key = f"{user_pk_to_url_str(user)}-{default_token_generator.make_token(user)}"
        url = get_adapter().get_reset_password_from_key_url(key)
        lines += [
            "",
            "We created an account for you so you can follow your application, correct your "
            "details or withdraw at any time. Set your password here:",
            url,
        ]
    else:
        lines += ["", "You can follow it from your applications page after signing in."]
    lines += ["", "MUDHOTECH HR RECRUITING SYSTEM"]
    queue_email(
        user.email,
        f"Your application for {job.title}",
        "\n".join(lines),
        dedupe_key=f"email.assisted_invite:{user.pk}:{job.pk}",
        organisation_id=job.organisation_id,
    )


def create_assisted_application(
    staff: Any,
    job: Job,
    *,
    email: str,
    first_name: str,
    last_name: str,
    phone: str = "",
    consent_confirmed: bool,
    consent_method: str,
    note: str = "",
    cv: Any = None,
    answers: list[dict[str, Any]] | None = None,
    ip: str | None = None,
) -> Application:
    _authorise(staff, job)
    if not email:
        raise DomainError(  # EC-APP-18: MVP needs an email to give the candidate access
            "validation_error",
            "An email address is required so the candidate can access their application.",
            details={"email": ["Required."]},
        )
    if not consent_confirmed or consent_method not in CONSENT_METHODS:
        raise DomainError(
            "validation_error",
            "Confirm the candidate agreed to apply and how they agreed.",
            details={"consent_method": [f"One of: {', '.join(CONSENT_METHODS)}."]},
        )
    with transaction.atomic():
        user, created = _candidate(email, first_name, last_name)
        if user.pk == staff.pk:
            raise DomainError(
                "validation_error", "You can't make an assisted application for yourself."
            )
        app, _ = services.start_or_resume_draft(job, user, source={"channel": "assisted"})
        services.update_draft(
            user,
            app.pk,
            {"contact": {"first_name": first_name, "last_name": last_name, "phone": phone}},
            lock_version=None,
        )
        if cv is not None:
            from apps.documents.services import direct_upload

            document = direct_upload(user, purpose="cv", uploaded=cv, organisation=job.organisation)
            services.set_documents(
                user, app.pk, [{"document_id": document.pk, "role": "cv", "required_doc_key": "cv"}]
            )
        if answers:
            services.upsert_answers(user, app.pk, answers)
        Application.objects.for_org(job.organisation_id).filter(pk=app.pk).update(
            is_assisted=True, assisted_by=staff, channel="assisted"
        )
        app = services.submit(
            user,
            app.pk,
            accept_privacy=True,
            actor=staff,
            ip=ip,
            assisted={"by": str(staff.pk), "method": consent_method, "note": note[:500]},
        )
        audit.record(
            actor=staff,
            action="application.assisted_created",
            target=app,
            organisation=job.organisation_id,
            after={"candidate_created": created, "consent_method": consent_method},
            reason=note[:500],
        )
        _invite(user, job, staff, created)
    return app
