"""Shortlist workflow (P08-T02/T03; FR-M12-05..07, EC-REV-01..05, 07, 08).

    propose -> decide (draft) -> submit -> approve | return -> [undo within the delay window]

* Proposals are pre-filled with *suggestions* from the AI bands. A suggestion is never a
  decision: every entry starts ``undecided`` and only a person sets a decision.
* "Not selected" and "on hold" need a reason from the organisation's list; overriding the AI band
  (shortlisting a lower match, or not selecting a recommended candidate) needs a reason too and is
  recorded with the AI band, score and coverage at the time of the decision (FR-M12-07).
* Approval needs ``applications.decide``; with dual control on, the proposer cannot approve
  (EC-REV-03). The shortlist row is locked, so a second concurrent approval gets 409
  ``already_processed`` (EC-REV-02). All status changes go through the state machine with the
  approver as the human actor, in one transaction, and candidate notifications are scheduled after
  the organisation's delay (ADR-014).
* Undo is possible until the notifications are due: decisions are reversed by new status events
  and the scheduled notifications are suppressed (EC-REV-04). After that, HR reopens single
  applications with a reason.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import QuerySet

from apps.applications.models import Application, DecisionReason, Status
from apps.audit import services as audit
from apps.core import outbox
from apps.core.exceptions import (
    ConflictError,
    DomainError,
    NotFoundError,
    PermissionDeniedError,
    StaleVersionError,
)
from apps.core.time import now
from apps.jobs.models import Job
from apps.organisations import rbac
from apps.organisations.models import OrganisationPolicy

from .models import Shortlist, ShortlistEntry

D = ShortlistEntry.Decision
DECIDABLE = (Status.UNDER_REVIEW, Status.ON_HOLD)
TARGET = {
    D.SHORTLIST: Status.SHORTLISTED,
    D.NOT_SELECTED: Status.NOT_SELECTED,
    D.HOLD: Status.ON_HOLD,
}
REASON_LIST = {
    D.SHORTLIST: DecisionReason.AppliesTo.SHORTLIST,
    D.NOT_SELECTED: DecisionReason.AppliesTo.NOT_SELECTED,
    D.HOLD: DecisionReason.AppliesTo.HOLD,
}
OUTCOME_KEYS = {D.SHORTLIST: "shortlisted", D.NOT_SELECTED: "not_selected"}
RECOMMENDED, LOWER, ELIGIBILITY = "recommended_for_review", "lower_match", "eligibility_review"
UNCERTAIN_BANDS = ("review_needed", "eligibility_review", "manual_review_requested")


# ------------------------------------------------------------------------------- helpers
def entries_of(shortlist: Shortlist) -> QuerySet[ShortlistEntry]:
    """Entries through the tenant-scoped manager (the strict guard rejects related managers
    that lose the organisation scope after ``select_for_update``)."""
    return ShortlistEntry.objects.for_org(shortlist.organisation_id).filter(shortlist=shortlist)


def _job(membership: Any, job_id: Any) -> Job:
    from apps.jobs.assignments import jobs_visible_to

    job = jobs_visible_to(membership).filter(pk=job_id).first()
    if job is None:
        raise NotFoundError()
    return job


def get_shortlist(membership: Any, shortlist_id: Any, *, lock: bool = False) -> Shortlist:
    qs = Shortlist.objects.for_org(membership.organisation_id)
    if lock:
        qs = qs.select_for_update()
    shortlist = qs.filter(pk=shortlist_id).first()
    if shortlist is None:
        raise NotFoundError()
    _job(membership, shortlist.job_id)  # vacancy visibility (assignment)
    return shortlist


def _policy(org_id: Any) -> OrganisationPolicy | None:
    return OrganisationPolicy.objects.filter(organisation_id=org_id).first()


def _require(membership: Any, action: str, message: str) -> None:
    if not rbac.can(membership.role, action):
        raise PermissionDeniedError(message=message, details={"required_action": action})


def _bump(shortlist: Shortlist, lock_version: int | None) -> None:
    if lock_version is not None and lock_version != shortlist.lock_version:
        raise StaleVersionError(details={"current_version": shortlist.lock_version})
    shortlist.lock_version += 1


def is_override(decision: str, band: str) -> bool:
    """The human decision goes against the AI band (FR-M12-07)."""
    if decision == D.SHORTLIST:
        return band in (LOWER, ELIGIBILITY)
    if decision == D.NOT_SELECTED:
        return band == RECOMMENDED
    return False


def suggestion_for(band: str, rank: int, desired: int | None) -> str:
    """Pre-fill only. Never suggests "not selected": absence of evidence is not a fail."""
    if band == RECOMMENDED and (desired is None or rank < desired):
        return "shortlist"
    if band in UNCERTAIN_BANDS:
        return "review"
    return ""


def _decidable(job: Job, membership: Any) -> list[Application]:
    from apps.applications.hr import applications_visible_to

    return list(
        applications_visible_to(membership)
        .filter(job=job, status__in=DECIDABLE)
        .order_by("-score", "submitted_at", "pk")
    )


# ------------------------------------------------------------------------------- propose
def create_proposal(
    membership: Any, actor: Any, job_id: Any, *, desired_size: int | None = None, notes: str = ""
) -> Shortlist:
    _require(membership, "applications.transition", "You can't propose a shortlist.")
    job = _job(membership, job_id)
    version = job.published_version or job.current_version
    if version is None:
        raise ConflictError(code="conflict.no_version", message="This vacancy has no version.")
    if desired_size is not None and not 1 <= desired_size <= 1000:
        raise DomainError(
            "validation_error",
            "Choose a shortlist size between 1 and 1000.",
            details={"desired_size": ["Between 1 and 1000."]},
        )
    apps = _decidable(job, membership)
    try:
        with transaction.atomic():
            shortlist = Shortlist.objects.create(
                organisation_id=job.organisation_id,
                job=job,
                job_version=version,
                desired_size=desired_size,
                proposed_by=actor,
                notes=notes.strip()[:4000],
            )
            recommended = 0
            entries = []
            for app in apps:
                band = app.ai_band or ""
                entries.append(
                    ShortlistEntry(
                        organisation_id=job.organisation_id,
                        shortlist=shortlist,
                        application=app,
                        suggestion=suggestion_for(band, recommended, desired_size),
                        evaluation_id=app.current_evaluation_id,
                        ai_band_at_decision=band,
                        score_at_decision=app.score,
                        coverage_at_decision=app.coverage,
                    )
                )
                recommended += band == RECOMMENDED
            ShortlistEntry.objects.bulk_create(entries)
            audit.record(
                actor=actor,
                action="shortlist.proposed",
                target=shortlist,
                organisation=job.organisation_id,
                after={
                    "job_id": str(job.pk),
                    "entries": len(entries),
                    "desired_size": desired_size,
                },
            )
    except IntegrityError as exc:
        if "one_open_shortlist_per_job" not in str(exc):
            raise
        raise ConflictError(
            code="conflict.open_shortlist",
            message="This vacancy already has a shortlist in progress.",
        ) from None
    return shortlist


def refresh_entries(membership: Any, actor: Any, shortlist_id: Any) -> int:
    """Add applications that became reviewable after the proposal was created."""
    with transaction.atomic():
        shortlist = get_shortlist(membership, shortlist_id, lock=True)
        if shortlist.status != Shortlist.Status.DRAFT:
            raise ConflictError(code="conflict.not_draft", message="Only a draft can change.")
        known = set(entries_of(shortlist).values_list("application_id", flat=True))
        added = [
            ShortlistEntry(
                organisation_id=shortlist.organisation_id,
                shortlist=shortlist,
                application=app,
                suggestion=suggestion_for(app.ai_band or "", 10**6, shortlist.desired_size),
                evaluation_id=app.current_evaluation_id,
                ai_band_at_decision=app.ai_band or "",
                score_at_decision=app.score,
                coverage_at_decision=app.coverage,
            )
            for app in _decidable(shortlist.job, membership)
            if app.pk not in known
        ]
        ShortlistEntry.objects.bulk_create(added)
        if added:
            shortlist.lock_version += 1
            shortlist.save(update_fields=["lock_version", "updated_at"])
    return len(added)


# ------------------------------------------------------------------------------- decide
def _reason(org_id: Any, decision: str, code: str, override: bool) -> DecisionReason | None:
    from apps.applications.ats import decision_reasons

    if not code:
        return None
    lists = [REASON_LIST[decision]] if decision in REASON_LIST else []  # type: ignore[index]
    if override:
        lists.append(DecisionReason.AppliesTo.OVERRIDE)
    return decision_reasons(org_id).filter(applies_to__in=lists, code=code).first()


def set_decisions(
    membership: Any,
    actor: Any,
    shortlist_id: Any,
    decisions: Iterable[dict[str, Any]],
    *,
    lock_version: int | None = None,
) -> Shortlist:
    """Set or clear decisions on a draft. Each item: application_id, decision, reason_code,
    reason_text. Validation errors name the application so the UI can point at the row."""
    _require(membership, "applications.transition", "You can't change this shortlist.")
    items = list(decisions)
    if not items:
        raise DomainError(
            "validation_error", "No decisions given.", details={"decisions": ["Required."]}
        )
    with transaction.atomic():
        shortlist = get_shortlist(membership, shortlist_id, lock=True)
        if shortlist.status != Shortlist.Status.DRAFT:
            raise ConflictError(
                code="conflict.not_draft", message="Only a draft shortlist can be changed."
            )
        _bump(shortlist, lock_version)
        entries = {
            str(e.application_id): e
            for e in entries_of(shortlist).select_related("application").select_for_update()
        }
        errors: dict[str, list[str]] = {}
        stamp = now()
        changed = Counter[str]()
        for item in items:
            app_id = str(item.get("application_id"))
            entry = entries.get(app_id)
            if entry is None:
                errors[app_id] = ["Not part of this shortlist."]
                continue
            decision = item.get("decision") or D.UNDECIDED
            code = (item.get("reason_code") or "").strip()
            text = (item.get("reason_text") or "").strip()[:2000]
            app = entry.application
            if decision == D.UNDECIDED:
                entry.decision, entry.reason, entry.reason_code, entry.reason_text = (
                    D.UNDECIDED,
                    None,
                    "",
                    "",
                )
                entry.decided_by = entry.decided_at = None
                entry.override = False
                changed[decision] += 1
                continue
            band = app.ai_band or ""
            override = is_override(decision, band)
            reason = _reason(shortlist.organisation_id, decision, code, override)
            needs_reason = decision in (D.NOT_SELECTED, D.HOLD) or override
            if needs_reason and reason is None:
                errors[app_id] = [
                    "Choose a reason (the decision differs from the AI suggestion)."
                    if override
                    else "Choose a reason for this decision."
                ]
                continue
            if code and reason is None:
                errors[app_id] = ["Unknown reason."]
                continue
            if code == "other" and len(text) < 5:
                errors[app_id] = ["Explain the reason ('Other')."]
                continue
            entry.decision = decision
            entry.reason = reason
            entry.reason_code = code
            entry.reason_text = text
            entry.override = override
            entry.decided_by = actor
            entry.decided_at = stamp
            # snapshot what the AI said when the person decided (P08-T03)
            entry.evaluation_id = app.current_evaluation_id
            entry.ai_band_at_decision = band
            entry.score_at_decision = app.score
            entry.coverage_at_decision = app.coverage
            changed[decision] += 1
        if errors:
            raise DomainError(
                "validation_error",
                "Some decisions could not be saved.",
                details={"decisions": errors},
            )
        ShortlistEntry.objects.for_org(shortlist.organisation_id).bulk_update(
            [entries[str(i.get("application_id"))] for i in items],
            [
                "decision",
                "reason",
                "reason_code",
                "reason_text",
                "override",
                "decided_by",
                "decided_at",
                "evaluation",
                "ai_band_at_decision",
                "score_at_decision",
                "coverage_at_decision",
            ],
        )
        shortlist.save(update_fields=["lock_version", "updated_at"])
        audit.record(
            actor=actor,
            action="shortlist.decisions_set",
            target=shortlist,
            organisation=shortlist.organisation_id,
            after={"counts": dict(changed)},
        )
    return shortlist


# ------------------------------------------------------------------------------- summary
def summary(shortlist: Shortlist) -> dict[str, Any]:
    """Counts the approval dialog shows (FR-M12-06; EC-REV-01, EC-REV-08)."""
    entries = list(entries_of(shortlist).all())
    by_decision = Counter(e.decision for e in entries)
    low = sum(
        1
        for e in entries
        if e.coverage_at_decision is not None and e.coverage_at_decision < Decimal("0.6")
    )
    uncertain_not_selected = sum(
        1
        for e in entries
        if e.decision == D.NOT_SELECTED
        and (
            e.ai_band_at_decision in UNCERTAIN_BANDS
            or (e.coverage_at_decision is not None and e.coverage_at_decision < Decimal("0.6"))
        )
    )
    shortlisted = by_decision[D.SHORTLIST]
    return {
        "total": len(entries),
        "undecided": by_decision[D.UNDECIDED],
        "shortlist": shortlisted,
        "not_selected": by_decision[D.NOT_SELECTED],
        "hold": by_decision[D.HOLD],
        "overrides": sum(1 for e in entries if e.override),
        "low_coverage": low,
        "uncertain_not_selected": uncertain_not_selected,
        "reasons": dict(
            Counter(e.reason_code for e in entries if e.decision != D.UNDECIDED and e.reason_code)
        ),
        "above_desired_size": bool(
            shortlist.desired_size and shortlisted > shortlist.desired_size
        ),  # EC-REV-08: allowed, info only
    }


# ------------------------------------------------------------------------------- submit
def submit(
    membership: Any, actor: Any, shortlist_id: Any, *, lock_version: int | None = None
) -> Shortlist:
    _require(membership, "applications.transition", "You can't submit this shortlist.")
    with transaction.atomic():
        shortlist = get_shortlist(membership, shortlist_id, lock=True)
        if shortlist.status != Shortlist.Status.DRAFT:
            raise ConflictError(
                code="already_processed", message="This shortlist was already submitted."
            )
        counts = summary(shortlist)
        if counts["total"] == counts["undecided"]:
            raise DomainError(
                "validation_error",
                "Make at least one decision before asking for approval.",
                details={"decisions": ["None set."]},
            )
        _bump(shortlist, lock_version)
        shortlist.status = Shortlist.Status.PENDING_APPROVAL
        shortlist.submitted_at = now()
        shortlist.save(update_fields=["status", "submitted_at", "lock_version", "updated_at"])
        audit.record(
            actor=actor,
            action="shortlist.submitted",
            target=shortlist,
            organisation=shortlist.organisation_id,
            after=counts,
        )
        outbox.emit(
            "shortlist.submitted",
            shortlist,
            {"shortlist_id": str(shortlist.pk), "job_id": str(shortlist.job_id)},
            dedupe_key=f"shortlist.submitted:{shortlist.pk}:{shortlist.lock_version}",
            organisation_id=shortlist.organisation_id,
        )
    return shortlist


# ------------------------------------------------------------------------------- approve
def _check_approver(membership: Any, actor: Any, shortlist: Shortlist) -> None:
    _require(membership, "applications.decide", "Only HR managers can approve a shortlist.")
    policy = _policy(shortlist.organisation_id)
    if (
        policy is not None
        and policy.shortlist_dual_control
        and shortlist.proposed_by_id == actor.pk
    ):
        raise PermissionDeniedError(
            code="self_approval_forbidden",
            message="Dual control is on: someone other than the proposer must approve.",
        )


def _notify(app: Application, decision: str, shortlist: Shortlist, when: Any) -> None:
    from apps.notifications import delivery as notifications

    key = OUTCOME_KEYS.get(decision)  # type: ignore[call-overload]
    if not key:
        return
    notifications.notify(
        app.candidate_user,
        key,
        {
            "organisation_name": app.organisation.name,
            "job_title": app.job.title,
            "application_url": f"{settings.FRONTEND_URL}/candidate/applications/{app.pk}",
            "application_id": app.pk,
        },
        dedupe_key=f"{key}:{app.pk}:shortlist:{shortlist.pk}",
        organisation=app.organisation_id,
        scheduled_for=when,
    )


def approve(
    membership: Any, actor: Any, shortlist_id: Any, *, lock_version: int | None = None
) -> Shortlist:
    from apps.applications.services import transition

    with transaction.atomic():
        shortlist = get_shortlist(membership, shortlist_id, lock=True)
        if shortlist.status != Shortlist.Status.PENDING_APPROVAL:
            raise ConflictError(
                code="already_processed", message="This shortlist has already been processed."
            )
        _check_approver(membership, actor, shortlist)
        _bump(shortlist, lock_version)
        policy = _policy(shortlist.organisation_id)
        delay = timedelta(minutes=policy.notification_delay_minutes if policy else 15)
        stamp = now()
        notify_after = stamp + delay
        applied = Counter[str]()
        entries = list(
            entries_of(shortlist)
            .exclude(decision=D.UNDECIDED)
            .select_related("application", "application__organisation", "application__job")
            .select_for_update(of=("self",))
        )
        for entry in entries:
            app = Application.objects.for_org(shortlist.organisation_id).get(
                pk=entry.application_id
            )
            target = TARGET[entry.decision]  # type: ignore[index]
            if app.status == Status.WITHDRAWN:
                entry.apply_note = "withdrawn"  # EC-REV-07: no outcome, no message
            elif app.status == target:
                entry.apply_note = "already_in_status"
            elif app.status not in DECIDABLE:
                entry.apply_note = f"status_changed:{app.status}"[:40]
            else:
                label = entry.reason.label if entry.reason else ""
                transition(
                    app,
                    target,
                    actor=actor,
                    reason=entry.reason_text or label or "Shortlist decision",
                    reason_code=entry.reason_code,
                    metadata={
                        "via": "shortlist",
                        "shortlist_id": str(shortlist.pk),
                        "decided_by": str(entry.decided_by_id),
                        "override": entry.override,
                    },
                )
                entry.applied_at = stamp
                applied[entry.decision] += 1
                _notify(entry.application, entry.decision, shortlist, notify_after)
        ShortlistEntry.objects.for_org(shortlist.organisation_id).bulk_update(
            entries, ["applied_at", "apply_note"]
        )
        shortlist.status = Shortlist.Status.APPROVED
        shortlist.approved_by = [*shortlist.approved_by, actor.pk]
        shortlist.approved_at = stamp
        shortlist.notify_after = notify_after
        shortlist.save(
            update_fields=[
                "status",
                "approved_by",
                "approved_at",
                "notify_after",
                "lock_version",
                "updated_at",
            ]
        )
        audit.record(
            actor=actor,
            action="shortlist.approved",
            target=shortlist,
            organisation=shortlist.organisation_id,
            after={"applied": dict(applied), "notify_after": notify_after.isoformat()},
        )
        outbox.emit(
            "shortlist.approved",
            shortlist,
            {"shortlist_id": str(shortlist.pk), "job_id": str(shortlist.job_id)},
            dedupe_key=f"shortlist.approved:{shortlist.pk}",
            organisation_id=shortlist.organisation_id,
        )
    return shortlist


def return_for_changes(
    membership: Any, actor: Any, shortlist_id: Any, *, reason: str, lock_version: int | None = None
) -> Shortlist:
    """The approver sends the proposal back to draft with a reason (the "reject" action)."""
    text = reason.strip()
    if len(text) < 5:
        raise DomainError(
            "validation_error",
            "Say what should change.",
            details={"reason": ["At least 5 characters."]},
        )
    with transaction.atomic():
        shortlist = get_shortlist(membership, shortlist_id, lock=True)
        if shortlist.status != Shortlist.Status.PENDING_APPROVAL:
            raise ConflictError(
                code="already_processed", message="This shortlist has already been processed."
            )
        _require(membership, "applications.decide", "Only HR managers can review a shortlist.")
        _bump(shortlist, lock_version)
        shortlist.status = Shortlist.Status.DRAFT
        shortlist.returned_by = actor
        shortlist.return_reason = text[:2000]
        shortlist.save(
            update_fields=["status", "returned_by", "return_reason", "lock_version", "updated_at"]
        )
        audit.record(
            actor=actor,
            action="shortlist.returned",
            target=shortlist,
            organisation=shortlist.organisation_id,
            reason=text,
        )
    return shortlist


# ------------------------------------------------------------------------------- undo
def undo(
    membership: Any, actor: Any, shortlist_id: Any, *, reason: str, lock_version: int | None = None
) -> Shortlist:
    from apps.applications.services import transition
    from apps.notifications.models import Notification, NotificationStatus

    text = reason.strip()
    if len(text) < 5:
        raise DomainError(
            "validation_error",
            "Say why the shortlist is undone.",
            details={"reason": ["At least 5 characters."]},
        )
    with transaction.atomic():
        shortlist = get_shortlist(membership, shortlist_id, lock=True)
        if shortlist.status != Shortlist.Status.APPROVED:
            raise ConflictError(
                code="already_processed", message="Only an approved shortlist can be undone."
            )
        _require(membership, "applications.decide", "Only HR managers can undo a shortlist.")
        if shortlist.notify_after is None or now() >= shortlist.notify_after:
            raise ConflictError(
                code="conflict.undo_window_closed",
                message="Candidates have been told. Reopen individual applications with a reason.",
            )
        _bump(shortlist, lock_version)
        applied = list(
            entries_of(shortlist).filter(applied_at__isnull=False).select_for_update(of=("self",))
        )
        reversed_ = 0
        for entry in applied:
            app = Application.objects.for_org(shortlist.organisation_id).get(
                pk=entry.application_id
            )
            if app.status != TARGET[entry.decision]:  # type: ignore[index]
                continue  # changed since (e.g. withdrawn): leave it
            transition(
                app,
                Status.UNDER_REVIEW,
                actor=actor,
                reason=f"Shortlist undone: {text}"[:2000],
                reason_code="shortlist_undone",
                metadata={"via": "shortlist_undo", "shortlist_id": str(shortlist.pk), "undo": True},
            )
            reversed_ += 1
        keys = [
            f"{OUTCOME_KEYS[e.decision]}:{e.application_id}:shortlist:{shortlist.pk}"  # type: ignore[index]
            for e in applied
            if e.decision in OUTCOME_KEYS
        ]
        cancelled = 0
        for key in keys:
            cancelled += Notification.objects.filter(
                dedupe_key__startswith=f"{key}:", status=NotificationStatus.QUEUED
            ).update(status=NotificationStatus.SUPPRESSED, last_error="shortlist_undone")
        ShortlistEntry.objects.for_org(shortlist.organisation_id).filter(
            pk__in=[e.pk for e in applied]
        ).update(applied_at=None, apply_note="undone")
        shortlist.status = Shortlist.Status.UNDONE
        shortlist.undone_at = now()
        shortlist.undone_by = actor
        shortlist.undo_reason = text[:2000]
        shortlist.save(
            update_fields=[
                "status",
                "undone_at",
                "undone_by",
                "undo_reason",
                "lock_version",
                "updated_at",
            ]
        )
        audit.record(
            actor=actor,
            action="shortlist.undone",
            target=shortlist,
            organisation=shortlist.organisation_id,
            after={"reversed": reversed_, "notifications_cancelled": cancelled},
            reason=text,
        )
    return shortlist
