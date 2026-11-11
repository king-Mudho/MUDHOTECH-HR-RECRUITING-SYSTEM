"""Applicant-tracking actions for HR (P05-T07): status changes with reason codes, notes with
@mentions, tags and recruiter assignment. Views stay thin; every write is audited.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet

from apps.audit import services as audit
from apps.core.exceptions import (
    DomainError,
    NotFoundError,
    PermissionDeniedError,
    StaleVersionError,
)
from apps.core.time import now
from apps.notifications import delivery as notifications
from apps.organisations import rbac
from apps.organisations.models import Membership, OrganisationPolicy, Role

from . import state_machine as sm
from .hr import applications_visible_to
from .models import Application, ApplicationNote, DecisionReason, Status
from .services import transition

MAX_TAGS = 10
TAG_RE = re.compile(r"[^a-z0-9-]+")
NOTE_MAX = 5000
MAX_MENTIONS = 10

# Which reason list a target status needs (None = optional).
REASON_LIST = {
    Status.SHORTLISTED: DecisionReason.AppliesTo.SHORTLIST,
    Status.NOT_SELECTED: DecisionReason.AppliesTo.NOT_SELECTED,
    Status.ON_HOLD: DecisionReason.AppliesTo.HOLD,
}
# Outcomes the candidate is told about, after the organisation's delay (FR-M14-05, ADR-014).
OUTCOME_NOTIFICATIONS = {Status.SHORTLISTED: "shortlisted", Status.NOT_SELECTED: "not_selected"}


def _visible(membership: Membership, application_id: Any, *, lock: bool = False) -> Application:
    qs = applications_visible_to(membership).select_related("job", "organisation", "candidate_user")
    if lock:
        qs = qs.select_for_update(of=("self",))
    app = qs.filter(pk=application_id).first()
    if app is None:
        raise NotFoundError()
    return app


# --------------------------------------------------------------------------- decisions
def decision_reasons(org: Any, applies_to: str | None = None) -> QuerySet[DecisionReason]:
    qs = DecisionReason.objects.filter(
        Q(organisation__isnull=True) | Q(organisation=org), active=True
    )
    return qs.filter(applies_to=applies_to) if applies_to else qs


def allowed_targets(membership: Membership, app: Application) -> list[str]:
    """Statuses this person may move the application to (drives the kanban, T08)."""
    targets = []
    for to in sm.allowed_targets(app.status, sm.STAFF):
        if to in sm.HUMAN_ONLY_TARGETS and not rbac.can(membership.role, "applications.decide"):
            continue
        if sm.is_reopen(app.status, to) and membership.role not in rbac.ADMIN_HR:
            continue
        if not rbac.can(membership.role, "applications.transition"):
            continue
        targets.append(to)
    return targets


def _reason_list_for(frm: str, to: str) -> str | None:
    if sm.is_reopen(frm, to):
        return DecisionReason.AppliesTo.OVERRIDE
    return REASON_LIST.get(to)  # type: ignore[call-overload]


def hr_transition(
    membership: Membership,
    actor: Any,
    application_id: Any,
    *,
    to_status: str,
    reason_code: str = "",
    reason_text: str = "",
    lock_version: int | None = None,
) -> Application:
    """Human status change from the HR workspace, validated by the state machine."""
    with transaction.atomic():
        app = _visible(membership, application_id, lock=True)
        if lock_version is not None and lock_version != app.lock_version:
            raise StaleVersionError(details={"lock_version": app.lock_version})
        if to_status in sm.HUMAN_ONLY_TARGETS and not rbac.can(
            membership.role, "applications.decide"
        ):
            raise PermissionDeniedError(
                message="Only HR managers can record this decision.",
                details={"required_action": "applications.decide"},
            )
        list_name = _reason_list_for(app.status, to_status)
        label = ""
        if list_name:
            reason = (
                decision_reasons(app.organisation_id, list_name).filter(code=reason_code).first()
            )
            if reason is None:
                raise DomainError(
                    "validation_error",
                    "Choose a reason for this decision.",
                    details={
                        "reason_code": [
                            "Pick one of: "
                            + ", ".join(
                                decision_reasons(app.organisation_id, list_name).values_list(
                                    "code", flat=True
                                )
                            )
                        ]
                    },
                )
            label = reason.label
            if reason_code == "other" and len(reason_text.strip()) < 5:
                raise DomainError(
                    "validation_error",
                    "Please explain the reason.",
                    details={"reason_text": ["Required when the reason is 'Other'."]},
                )
        text = reason_text.strip() or label
        app = transition(
            app,
            to_status,
            actor=actor,
            reason=text,
            reason_code=reason_code,
            metadata={"via": "hr_workspace"},
        )
        key = OUTCOME_NOTIFICATIONS.get(to_status)  # type: ignore[call-overload]
        if key:
            policy = OrganisationPolicy.objects.filter(organisation_id=app.organisation_id).first()
            delay = timedelta(minutes=policy.notification_delay_minutes if policy else 15)
            notifications.notify(
                app.candidate_user,
                key,
                {
                    "organisation_name": app.organisation.name,
                    "job_title": app.job.title,
                    "application_url": f"{settings.FRONTEND_URL}/candidate/applications/{app.pk}",
                    "application_id": app.pk,
                },
                dedupe_key=f"{key}:{app.pk}:{app.lock_version}",
                organisation=app.organisation_id,
                scheduled_for=now() + delay,  # time to undo a mistake before the candidate hears
            )
    return app


# ------------------------------------------------------------------------------- notes
def visible_notes(
    membership: Membership, user: Any, application_id: Any
) -> QuerySet[ApplicationNote]:
    app = _visible(membership, application_id)
    return (
        ApplicationNote.objects.for_org(app.organisation_id)
        .filter(application=app)
        .filter(Q(visibility=ApplicationNote.Visibility.TEAM) | Q(author=user))
        .select_related("author")
    )


def _plain(text: str) -> str:
    import nh3

    return nh3.clean(text or "", tags=set()).strip()


def add_note(
    membership: Membership,
    actor: Any,
    application_id: Any,
    *,
    body: str,
    mentions: list[Any] | None = None,
    visibility: str = ApplicationNote.Visibility.TEAM,
) -> ApplicationNote:
    app = _visible(membership, application_id)
    text = _plain(body)[:NOTE_MAX]
    if not text:
        raise DomainError(
            "validation_error", "Write a note first.", details={"body": ["Required."]}
        )
    mentioned = list(dict.fromkeys(str(m) for m in (mentions or [])))
    if mentioned and visibility == ApplicationNote.Visibility.PRIVATE:
        raise DomainError(
            "validation_error",
            "Private notes can't mention colleagues.",
            details={"mentions": ["Make the note visible to the team to mention someone."]},
        )
    if len(mentioned) > MAX_MENTIONS:
        raise DomainError(
            "validation_error",
            "Too many mentions.",
            details={"mentions": [f"At most {MAX_MENTIONS}."]},
        )
    members = {
        str(m.user_id): m
        for m in Membership.objects.for_org(app.organisation_id)
        .filter(user_id__in=mentioned, status=Membership.Status.ACTIVE)
        .select_related("user")
    }
    unknown = [m for m in mentioned if m not in members]
    blind = [
        m
        for m in mentioned
        if m in members and not applications_visible_to(members[m]).filter(pk=app.pk).exists()
    ]
    if unknown or blind:
        raise DomainError(
            "validation_error",
            "You can only mention colleagues who can see this application.",
            details={"mentions": unknown + blind},
        )
    with transaction.atomic():
        note = ApplicationNote.objects.create(
            organisation_id=app.organisation_id,
            application=app,
            author=actor,
            body=text,
            mentions=mentioned,
            visibility=visibility,
        )
        audit.record(
            actor=actor,
            action="application.note_added",
            target=note,
            organisation=app.organisation_id,
            after={
                "application_id": str(app.pk),
                "visibility": visibility,
                "mentions": len(mentioned),
            },
        )
        for user_id in mentioned:
            member = members[user_id]
            if member.user_id == getattr(actor, "pk", None):
                continue
            notifications.notify(
                member.user,
                "note_mention",
                {
                    "mention_author": actor.display_name,
                    "job_title": app.job.title,
                    "note_url": f"{settings.FRONTEND_URL}/hr/applications/{app.pk}#notes",
                    "application_id": app.pk,
                },
                dedupe_key=f"note_mention:{note.pk}:{member.user_id}",
                organisation=app.organisation_id,
                channels=("inapp",),
            )
    return note


# -------------------------------------------------------------------------- tags / assign
def normalise_tags(raw: list[str]) -> list[str]:
    tags: list[str] = []
    for item in raw:
        tag = TAG_RE.sub("-", str(item).strip().lower()).strip("-")[:40]
        if tag and tag not in tags:
            tags.append(tag)
    if len(tags) > MAX_TAGS:
        raise DomainError(
            "validation_error", "Too many tags.", details={"tags": [f"At most {MAX_TAGS}."]}
        )
    return tags


def set_tags(
    membership: Membership, actor: Any, application_id: Any, tags: list[str]
) -> Application:
    clean = normalise_tags(tags)
    with transaction.atomic():
        app = _visible(membership, application_id, lock=True)
        before = list(app.tags)
        app.tags = clean
        app.save(update_fields=["tags", "updated_at"])
        audit.record(
            actor=actor,
            action="application.tags_changed",
            target=app,
            organisation=app.organisation_id,
            before={"tags": before},
            after={"tags": clean},
        )
    return app


ASSIGNABLE_ROLES = {Role.ORG_ADMIN, Role.HR_MANAGER, Role.RECRUITER}


def assign(membership: Membership, actor: Any, application_id: Any, user_id: Any) -> Application:
    with transaction.atomic():
        app = _visible(membership, application_id, lock=True)
        assignee = None
        if user_id is not None:
            target = (
                Membership.objects.for_org(app.organisation_id)
                .filter(user_id=user_id, status=Membership.Status.ACTIVE, role__in=ASSIGNABLE_ROLES)
                .select_related("user")
                .first()
            )
            if target is None or not applications_visible_to(target).filter(pk=app.pk).exists():
                raise DomainError(
                    "validation_error",
                    "Assign the application to a recruiter who works on this vacancy.",
                    details={"user_id": ["Not an active recruiter on this vacancy."]},
                )
            assignee = target.user
        before = str(app.assigned_recruiter_id) if app.assigned_recruiter_id else None
        app.assigned_recruiter = assignee
        app.save(update_fields=["assigned_recruiter", "updated_at"])
        audit.record(
            actor=actor,
            action="application.assigned",
            target=app,
            organisation=app.organisation_id,
            before={"assigned_recruiter": before},
            after={"assigned_recruiter": str(assignee.pk) if assignee else None},
        )
    return app
