"""Interview scheduling (docs/01 M16, P12-T02).

* ``create_interview`` - a fixed time (status *scheduled*) or several offered slots (*proposed*, the
  candidate books one). The first interview moves the application ``shortlisted -> interview``.
* ``book_slot`` - candidate self-booking; the interview and its slots are row-locked so two tabs or
  two people can never book twice (one booked slot per interview is also a database constraint).
* ``reschedule`` / ``cancel`` - reason required; ICS ``SEQUENCE`` increases; reminders re-arm.
* ``mark_no_show`` / ``mark_completed`` - a no-show is recorded, never a rejection (EC-INT-03).
* ``panel_conflicts`` - overlapping interviews of a panelist: a warning, HR decides (EC-INT-01).
* ``send_due_reminders`` - 24 h and 1 h reminders (beat).

Times are stored in UTC; each interview keeps the IANA timezone it was arranged in, and every
message shows the time in that zone with its UTC offset (EC-INT-02).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet

from apps.applications.models import Application, Status
from apps.applications.services import transition
from apps.audit import services as audit
from apps.core import time as mhrs_time
from apps.core.exceptions import DomainError, PermissionDeniedError
from apps.notifications import delivery as notifications
from apps.organisations.models import Membership

from .models import (
    OPEN_STATUSES,
    Interview,
    InterviewMode,
    InterviewPanelist,
    InterviewSlot,
    InterviewStatus,
    PanelRole,
    ScorecardTemplate,
)

SCHEDULABLE = (Status.SHORTLISTED, Status.INTERVIEW)
MAX_SLOTS = 12
REMINDERS = (("24h", timedelta(hours=24)), ("1h", timedelta(hours=1)))


@dataclass
class Scheduled:
    interview: Interview
    conflicts: list[dict[str, Any]] = field(default_factory=list)  # EC-INT-01 warnings


# --- helpers --------------------------------------------------------------------------------------
def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise DomainError(
            "validation_error", "Unknown timezone.", 422, {"timezone": ["Use an IANA zone name."]}
        ) from None


def format_when(starts_at: datetime | None, tz_name: str) -> str:
    """``Tuesday 24 November 2026, 10:00 (Africa/Harare, UTC+02:00)``: arranged zone + offset."""
    if starts_at is None:
        return "a time you choose in your account"
    local = starts_at.astimezone(zone(tz_name))
    offset = local.strftime("%z")
    return f"{local:%A %d %B %Y, %H:%M} ({tz_name}, UTC{offset[:3]}:{offset[3:]})"


def _staff_membership(actor: Any, organisation_id: Any) -> Membership:
    membership = (
        Membership.objects.for_org(organisation_id)
        .filter(user=actor, status=Membership.Status.ACTIVE)
        .first()
    )
    if membership is None:
        raise PermissionDeniedError(
            message="Only staff of this organisation can manage interviews."
        )
    return membership


def _validate_window(starts_at: datetime, ends_at: datetime) -> None:
    if starts_at.tzinfo is None:
        raise DomainError("validation_error", "Times must include a timezone.", 422)
    if ends_at <= starts_at:
        raise DomainError("validation_error", "An interview must end after it starts.", 422)
    if starts_at <= mhrs_time.now():
        raise DomainError(
            "validation_error",
            "Interview times must be in the future.",
            422,
            {"starts_at": ["Choose a future time."]},
        )


def _context(interview: Interview, app: Application, **extra: Any) -> dict[str, Any]:
    job = app.job
    where = {
        InterviewMode.IN_PERSON: interview.location or "Details in your account",
        InterviewMode.VIDEO: "The link is in your account",
        InterviewMode.PHONE: "The employer will call you",
    }[InterviewMode(interview.mode)]
    return {
        "organisation_name": app.organisation.name,
        "job_title": job.title,
        "interview_stage": interview.stage,
        "interview_when": format_when(interview.starts_at, interview.timezone),
        "interview_mode": InterviewMode(interview.mode).label,
        "interview_where": where,
        "interview_url": f"{settings.FRONTEND_URL}/candidate/applications/{app.pk}#interviews",
        **extra,
    }


def panel_conflicts(
    memberships: Iterable[Membership],
    starts_at: datetime,
    ends_at: datetime,
    *,
    exclude: Interview | None = None,
) -> list[dict[str, Any]]:
    """Open interviews of these panelists that overlap the window (EC-INT-01: warn, never block)."""
    out: list[dict[str, Any]] = []
    for m in memberships:
        qs: QuerySet[InterviewPanelist] = InterviewPanelist.objects.for_org(
            m.organisation_id
        ).filter(
            membership=m,
            interview__status__in=OPEN_STATUSES,
            interview__starts_at__lt=ends_at,
            interview__ends_at__gt=starts_at,
        )
        if exclude is not None:
            qs = qs.exclude(interview=exclude)
        for p in qs.select_related("interview"):
            out.append(
                {
                    "membership_id": str(m.pk),
                    "interview_id": str(p.interview_id),
                    "starts_at": p.interview.starts_at.isoformat()
                    if p.interview.starts_at
                    else None,
                    "ends_at": p.interview.ends_at.isoformat() if p.interview.ends_at else None,
                }
            )
    return out


def _emit_changed(iv: Interview) -> None:
    """P15-T02: calendar sync and other integrations react after commit (never inside the
    business transaction, and their failures never affect the interview)."""
    from apps.core import outbox

    outbox.emit(
        "interview.changed",
        iv,
        {"interview_id": str(iv.pk), "status": iv.status, "sequence": iv.sequence},
        dedupe_key=f"interview.changed:{iv.pk}:{iv.sequence}:{iv.status}:{iv.lock_version}",
        organisation_id=iv.organisation_id,
    )


def calendar_conflicts(
    memberships: Iterable[Membership], starts_at: datetime, ends_at: datetime
) -> list[dict[str, Any]]:
    """Busy times from panelists' connected calendars (P15-T02); warn, never block."""
    from apps.integrations.calendar_sync import external_busy

    return external_busy(list(memberships), starts_at, ends_at)


# --- create ---------------------------------------------------------------------------------------
def create_interview(
    application: Application,
    *,
    actor: Any,
    stage: str,
    mode: str,
    panel: Sequence[tuple[Membership, str]],
    starts_at: datetime | None = None,
    slots: Sequence[datetime] = (),
    duration_minutes: int = 45,
    timezone: str = "Africa/Harare",
    location: str = "",
    video_link: str = "",
    instructions: str = "",
    scorecard_template: ScorecardTemplate | None = None,
) -> Scheduled:
    _staff_membership(actor, application.organisation_id)
    zone(timezone)
    stage = stage.strip()
    if not stage:
        raise DomainError(
            "validation_error", "Name the interview stage.", 422, {"stage": ["Required."]}
        )
    if mode not in InterviewMode.values:
        raise DomainError(
            "validation_error", "Unknown interview mode.", 422, {"mode": ["Invalid."]}
        )
    if mode == InterviewMode.IN_PERSON and not location.strip():
        raise DomainError("validation_error", "Give the address.", 422, {"location": ["Required."]})
    if (starts_at is None) == (not slots):
        raise DomainError(
            "validation_error", "Give either a time or a list of times to choose from.", 422
        )
    if len(slots) > MAX_SLOTS:
        raise DomainError("validation_error", f"Offer at most {MAX_SLOTS} times.", 422)
    if not panel:
        raise DomainError(
            "validation_error", "Add at least one panelist.", 422, {"panel": ["Required."]}
        )
    duration = timedelta(minutes=duration_minutes)
    windows = [(s, s + duration) for s in ([starts_at] if starts_at else sorted(set(slots)))]
    for s, e in windows:
        _validate_window(s, e)
    memberships = [m for m, _role in panel]
    for m in memberships:
        if m.organisation_id != application.organisation_id or m.status != Membership.Status.ACTIVE:
            raise DomainError(
                "validation_error", "Panelists must be active staff of this organisation.", 422
            )
    if scorecard_template and scorecard_template.organisation_id != application.organisation_id:
        raise DomainError("validation_error", "Unknown scorecard template.", 422)

    with transaction.atomic():
        app = (
            Application.objects.for_org(application.organisation_id)
            .select_for_update()
            .get(pk=application.pk)
        )
        if app.status not in SCHEDULABLE:
            raise DomainError(
                "invalid_state",
                "Only shortlisted applications can be invited to an interview.",
                409,
                {"status": app.status},
            )
        interview = Interview.objects.create(
            organisation_id=app.organisation_id,
            application=app,
            stage=stage[:60],
            mode=mode,
            location=location.strip()[:300],
            video_link=video_link.strip(),
            duration_minutes=duration_minutes,
            timezone=timezone,
            instructions=instructions.strip(),
            scorecard_template=scorecard_template,
            created_by=actor,
            status=InterviewStatus.SCHEDULED if starts_at else InterviewStatus.PROPOSED,
            starts_at=windows[0][0] if starts_at else None,
            ends_at=windows[0][1] if starts_at else None,
        )
        seen: set[Any] = set()
        for m, role in panel:
            if m.pk in seen:
                continue
            seen.add(m.pk)
            InterviewPanelist.objects.create(
                organisation_id=app.organisation_id,
                interview=interview,
                membership=m,
                role=role if role in PanelRole.values else PanelRole.MEMBER,
            )
        if not starts_at:
            InterviewSlot.objects.bulk_create(
                InterviewSlot(
                    organisation_id=app.organisation_id, interview=interview, starts_at=s, ends_at=e
                )
                for s, e in windows
            )
        if app.status == Status.SHORTLISTED:
            transition(
                app, Status.INTERVIEW, actor=actor, reason=f"Interview arranged: {stage}"[:200]
            )
        audit.record(
            actor=actor,
            action="interviews.created",
            target=interview,
            organisation=app.organisation,
            after={
                "stage": interview.stage,
                "mode": mode,
                "status": interview.status,
                "slots": len(windows) if not starts_at else 0,
                "panel": len(seen),
            },
        )
        notifications.notify(
            app.candidate_user,
            "interview_invitation",
            _context(interview, app),
            dedupe_key=f"interview_invitation:{interview.pk}:{interview.sequence}",
            organisation=app.organisation,
        )
        if interview.starts_at is not None:
            _emit_changed(interview)
    conflicts: list[dict[str, Any]] = []
    for s, e in windows:
        conflicts += panel_conflicts(memberships, s, e, exclude=interview)
        conflicts += calendar_conflicts(memberships, s, e)
    return Scheduled(interview, conflicts)


# --- candidate booking ----------------------------------------------------------------------------
def book_slot(interview: Interview, slot_id: Any, *, candidate: Any) -> Interview:
    with transaction.atomic():
        iv = (
            Interview.objects.for_org(interview.organisation_id)
            .select_for_update()
            .select_related("application__job", "application__organisation")
            .get(pk=interview.pk)
        )
        app = iv.application
        if app.candidate_user_id != getattr(candidate, "pk", None):
            raise PermissionDeniedError(message="This is not your interview.")
        if iv.status != InterviewStatus.PROPOSED:
            raise DomainError(
                "interview_not_bookable", "This interview is no longer open for booking.", 409
            )
        slots = {
            s.pk: s
            for s in InterviewSlot.objects.for_org(iv.organisation_id)
            .select_for_update()
            .filter(interview=iv)
        }
        slot = slots.get(slot_id) or next(
            (s for k, s in slots.items() if str(k) == str(slot_id)), None
        )
        if slot is None:
            raise DomainError("not_found", "That time is not available.", 404)
        if slot.starts_at <= mhrs_time.now():
            raise DomainError("slot_in_past", "That time has passed; choose another.", 409)
        stamp = mhrs_time.now()
        slot.booked, slot.booked_at = True, stamp
        slot.save(update_fields=["booked", "booked_at", "updated_at"])
        iv.status = InterviewStatus.SCHEDULED
        iv.starts_at, iv.ends_at = slot.starts_at, slot.ends_at
        iv.lock_version += 1
        iv.save(update_fields=["status", "starts_at", "ends_at", "lock_version", "updated_at"])
        audit.record(
            actor=candidate,
            action="interviews.booked",
            target=iv,
            organisation=app.organisation,
            after={"slot_id": str(slot.pk), "starts_at": slot.starts_at.isoformat()},
            actor_type="human",
        )
        for p in iv.panelists.select_related("membership__user"):
            if p.role == PanelRole.LEAD or iv.created_by_id == p.membership.user_id:
                notifications.notify(
                    p.membership.user,
                    "interview_booked",
                    {
                        "job_title": app.job.title,
                        "reference": app.reference,
                        "interview_stage": iv.stage,
                        "interview_when": format_when(iv.starts_at, iv.timezone),
                        "interview_url": f"{settings.FRONTEND_URL}/hr/interviews/{iv.pk}",
                    },
                    dedupe_key=f"interview_booked:{iv.pk}:{p.pk}:{iv.sequence}",
                    organisation=app.organisation,
                    channels=("inapp",),
                )
        _emit_changed(iv)
    return iv


# --- changes by HR --------------------------------------------------------------------------------
def _reason(reason: str) -> str:
    text = (reason or "").strip()
    if len(text) < 5:
        raise DomainError(
            "validation_error", "A reason is required.", 422, {"reason": ["At least 5 characters."]}
        )
    return text[:500]


def _locked(interview: Interview) -> Interview:
    return (
        Interview.objects.for_org(interview.organisation_id)
        .select_for_update()
        .select_related("application__job", "application__organisation")
        .get(pk=interview.pk)
    )


def reschedule(
    interview: Interview,
    *,
    actor: Any,
    reason: str,
    starts_at: datetime | None = None,
    slots: Sequence[datetime] = (),
) -> Scheduled:
    _staff_membership(actor, interview.organisation_id)
    text = _reason(reason)
    if (starts_at is None) == (not slots):
        raise DomainError(
            "validation_error", "Give either a new time or new times to choose from.", 422
        )
    with transaction.atomic():
        iv = _locked(interview)
        if iv.status not in OPEN_STATUSES:
            raise DomainError("invalid_state", "Only open interviews can be rescheduled.", 409)
        duration = timedelta(minutes=iv.duration_minutes)
        windows = [(s, s + duration) for s in ([starts_at] if starts_at else sorted(set(slots)))]
        for s, e in windows:
            _validate_window(s, e)
        before = {
            "status": iv.status,
            "starts_at": iv.starts_at.isoformat() if iv.starts_at else None,
        }
        InterviewSlot.objects.for_org(iv.organisation_id).filter(interview=iv).delete()
        if starts_at:
            iv.status, iv.starts_at, iv.ends_at = (
                InterviewStatus.SCHEDULED,
                windows[0][0],
                windows[0][1],
            )
        else:
            iv.status, iv.starts_at, iv.ends_at = InterviewStatus.PROPOSED, None, None
            InterviewSlot.objects.bulk_create(
                InterviewSlot(
                    organisation_id=iv.organisation_id, interview=iv, starts_at=s, ends_at=e
                )
                for s, e in windows
            )
        iv.sequence += 1
        iv.lock_version += 1
        iv.status_reason = text
        iv.reminder_24h_sent_at = iv.reminder_1h_sent_at = None
        iv.save()
        app = iv.application
        audit.record(
            actor=actor,
            action="interviews.rescheduled",
            target=iv,
            organisation=app.organisation,
            before=before,
            after={
                "status": iv.status,
                "starts_at": iv.starts_at.isoformat() if iv.starts_at else None,
            },
            reason=text,
        )
        notifications.notify(
            app.candidate_user,
            "interview_rescheduled",
            _context(iv, app, reason=text),
            dedupe_key=f"interview_rescheduled:{iv.pk}:{iv.sequence}",
            organisation=app.organisation,
        )
        _emit_changed(iv)
    memberships = [p.membership for p in iv.panelists.select_related("membership")]
    conflicts: list[dict[str, Any]] = []
    for s, e in windows:
        conflicts += panel_conflicts(memberships, s, e, exclude=iv)
        conflicts += calendar_conflicts(memberships, s, e)
    return Scheduled(iv, conflicts)


def cancel(interview: Interview, *, actor: Any, reason: str) -> Interview:
    _staff_membership(actor, interview.organisation_id)
    text = _reason(reason)
    with transaction.atomic():
        iv = _locked(interview)
        if iv.status not in OPEN_STATUSES:
            raise DomainError("invalid_state", "Only open interviews can be cancelled.", 409)
        when = format_when(iv.starts_at, iv.timezone) if iv.starts_at else "the time offered"
        iv.status = InterviewStatus.CANCELLED
        iv.status_reason = text
        iv.sequence += 1
        iv.lock_version += 1
        iv.save(update_fields=["status", "status_reason", "sequence", "lock_version", "updated_at"])
        app = iv.application
        audit.record(
            actor=actor,
            action="interviews.cancelled",
            target=iv,
            organisation=app.organisation,
            reason=text,
        )
        notifications.notify(
            app.candidate_user,
            "interview_cancelled",
            {
                **_context(iv, app, reason=text),
                "interview_when": when,
                "application_url": f"{settings.FRONTEND_URL}/candidate/applications/{app.pk}",
            },
            dedupe_key=f"interview_cancelled:{iv.pk}:{iv.sequence}",
            organisation=app.organisation,
        )
        _emit_changed(iv)
    return iv


def _after_start(iv: Interview, what: str) -> None:
    if iv.status != InterviewStatus.SCHEDULED or iv.starts_at is None:
        raise DomainError("invalid_state", f"Only scheduled interviews can be marked {what}.", 409)
    if iv.starts_at > mhrs_time.now():
        raise DomainError(
            "invalid_state", f"An interview can be marked {what} once it has started.", 409
        )


def mark_no_show(interview: Interview, *, actor: Any, note: str = "") -> Interview:
    """EC-INT-03: recorded only; the application keeps its status (reschedule or decide later)."""
    _staff_membership(actor, interview.organisation_id)
    with transaction.atomic():
        iv = _locked(interview)
        _after_start(iv, "as a no-show")
        iv.status = InterviewStatus.NO_SHOW
        iv.status_reason = note.strip()[:500]
        iv.lock_version += 1
        iv.save(update_fields=["status", "status_reason", "lock_version", "updated_at"])
        audit.record(
            actor=actor,
            action="interviews.no_show",
            target=iv,
            organisation=iv.application.organisation,
            reason=iv.status_reason,
        )
    return iv


def mark_completed(interview: Interview, *, actor: Any) -> Interview:
    _staff_membership(actor, interview.organisation_id)
    with transaction.atomic():
        iv = _locked(interview)
        _after_start(iv, "completed")
        iv.status = InterviewStatus.COMPLETED
        iv.lock_version += 1
        iv.save(update_fields=["status", "lock_version", "updated_at"])
        audit.record(
            actor=actor,
            action="interviews.completed",
            target=iv,
            organisation=iv.application.organisation,
        )
    return iv


# --- reminders (beat) -----------------------------------------------------------------------------
def send_due_reminders(now: datetime | None = None) -> int:
    """24 h and 1 h before each scheduled interview, once per schedule (re-armed on reschedule)."""
    now = now or mhrs_time.now()
    sent = 0
    for label, before in REMINDERS:
        stamp_field = f"reminder_{label}_sent_at"
        due = Interview.objects.unscoped().filter(
            Q(status=InterviewStatus.SCHEDULED),
            Q(starts_at__gt=now),
            Q(starts_at__lte=now + before),
            Q(**{f"{stamp_field}__isnull": True}),
        )
        if label == "24h":  # not when the 1 h window has already started (booked at short notice)
            due = due.filter(starts_at__gt=now + timedelta(hours=1))
        for pk in due.values_list("pk", flat=True):
            with transaction.atomic():
                iv = (
                    Interview.objects.unscoped()
                    .select_for_update(skip_locked=True)
                    .select_related("application__job", "application__organisation")
                    .filter(pk=pk, **{f"{stamp_field}__isnull": True})
                    .first()
                )
                if iv is None or iv.application.status != Status.INTERVIEW:
                    continue
                setattr(iv, stamp_field, now)
                iv.save(update_fields=[stamp_field, "updated_at"])
                app = iv.application
                notifications.notify(
                    app.candidate_user,
                    "interview_reminder",
                    _context(iv, app),
                    dedupe_key=f"interview_reminder:{iv.pk}:{iv.sequence}:{label}",
                    organisation=app.organisation,
                )
                sent += 1
    return sent
