"""Offer workflow (docs/01 M17, P12-T04). See ``models`` for the states.

* EC-OFF-01: ``issue`` refuses anything that is not ``approved`` - approvals are counted per round,
  by distinct people with ``offers.approve`` who did not draft the offer.
* EC-OFF-02: ``expire_due`` (beat) closes issued offers past their deadline and tells HR; candidates
  get a reminder 48 hours before.
* EC-OFF-03: accepting never fails because openings are full - HR is warned (``openings``) and
  decides.
* EC-OFF-04: if the candidate withdraws the application after accepting, the offer becomes
  ``withdrawn`` and any hire record is cancelled (``on_application_withdrawn``, an outbox consumer).
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction

from apps.applications.models import Application, Status
from apps.applications.services import transition
from apps.audit import services as audit
from apps.audit.services import truncate_ip
from apps.core import storage
from apps.core import time as mhrs_time
from apps.core.exceptions import ConflictError, DomainError, PermissionDeniedError
from apps.documents.models import Document, Purpose, ScanStatus
from apps.interviews.scheduling import format_when
from apps.jobs.models import Currency, EmploymentType, Job, SalaryPeriod
from apps.notifications import delivery as notifications
from apps.organisations import rbac
from apps.organisations.models import Membership, OrganisationPolicy

from . import letter
from .models import (
    LIVE_STATUSES,
    ApprovalDecision,
    HireRecord,
    Offer,
    OfferApproval,
    OfferStatus,
)

EXPIRY_REMINDER = timedelta(hours=48)
ACCEPT_STATEMENT_VERSION = "2026-11"
EDITABLE = (
    "salary_amount",
    "currency",
    "period",
    "start_date",
    "contract_type",
    "conditions",
    "expires_at",
)


# --- helpers --------------------------------------------------------------------------------------
def _membership(actor: Any, organisation_id: Any, action: str) -> Membership:
    m = (
        Membership.objects.for_org(organisation_id)
        .filter(user=actor, status=Membership.Status.ACTIVE)
        .first()
    )
    if m is None or not rbac.can(m.role, action):
        raise PermissionDeniedError(message="You can't do this with offers.")
    return m


def _locked(offer: Offer) -> Offer:
    return (
        Offer.objects.for_org(offer.organisation_id)
        .select_for_update()
        .select_related(
            "application__job", "application__organisation", "application__candidate_user"
        )
        .get(pk=offer.pk)
    )


def _require(offer: Offer, *states: str) -> None:
    if offer.status not in states:
        raise DomainError(
            "invalid_offer_state",
            f"Not possible while the offer is {offer.get_status_display().lower()}.",
            409,
            {"status": offer.status},
        )


def _reason(text: str, field: str = "reason") -> str:
    text = (text or "").strip()
    if len(text) < 5:
        raise DomainError(
            "validation_error", "A reason is required.", 422, {field: ["At least 5 characters."]}
        )
    return text[:500]


def _clean_terms(data: dict[str, Any], current: Offer | None = None) -> dict[str, Any]:
    errors: dict[str, list[str]] = {}
    out: dict[str, Any] = {}
    for name in EDITABLE:
        if name in data:
            out[name] = data[name]
        elif current is not None:
            out[name] = getattr(current, name)
    try:
        amount = Decimal(str(out.get("salary_amount")))
        if amount <= 0 or amount.as_tuple().exponent < -2:  # type: ignore[operator]
            raise InvalidOperation
        out["salary_amount"] = amount
    except (InvalidOperation, ValueError, TypeError):
        errors["salary_amount"] = ["A positive amount with at most 2 decimals."]
    if out.get("currency") not in Currency.values:
        errors["currency"] = ["Unknown currency."]
    if out.get("period") not in SalaryPeriod.values:
        errors["period"] = ["Unknown pay period."]
    if out.get("contract_type") not in EmploymentType.values:
        errors["contract_type"] = ["Unknown contract type."]
    start = out.get("start_date")
    if not isinstance(start, date) or start < mhrs_time.now().date():
        errors["start_date"] = ["A start date from today on."]
    expires = out.get("expires_at")
    if not isinstance(expires, datetime) or expires.tzinfo is None or expires <= mhrs_time.now():
        errors["expires_at"] = ["A deadline in the future (with a timezone)."]
    out["conditions"] = str(out.get("conditions") or "").strip()[:10000]
    if errors:
        raise DomainError("validation_error", "Please check the offer.", 422, errors)
    return out


def _offer_url(app: Application, staff: bool = False) -> str:
    if staff:
        return f"{settings.FRONTEND_URL}/hr/offers?application={app.pk}"
    return f"{settings.FRONTEND_URL}/candidate/applications/{app.pk}#offer"


def _hr_recipients(offer: Offer) -> list[Any]:
    users = {u for u in (offer.created_by, offer.issued_by) if u is not None}
    return sorted(users, key=lambda u: str(u.pk))


def openings(job: Job) -> dict[str, int | bool]:
    """EC-OFF-03: accepted offers + active hires against the vacancy's openings."""
    accepted = (
        Offer.objects.for_org(job.organisation_id)
        .filter(application__job=job, status=OfferStatus.ACCEPTED)
        .count()
    )
    hired = (
        HireRecord.objects.for_org(job.organisation_id)
        .filter(application__job=job, cancelled_at__isnull=True)
        .count()
    )
    taken = max(accepted, hired)
    return {
        "openings": job.openings,
        "accepted": accepted,
        "hired": hired,
        "remaining": max(job.openings - taken, 0),
        "over": taken > job.openings,
    }


# --- drafting and approval ------------------------------------------------------------------------
def create_draft(application: Application, *, actor: Any, data: dict[str, Any]) -> Offer:
    _membership(actor, application.organisation_id, "offers.manage")
    terms = _clean_terms(data)
    policy = OrganisationPolicy.objects.filter(organisation_id=application.organisation_id).first()
    required = min(max(policy.offer_approvals_required if policy else 1, 1), 5)
    with transaction.atomic():
        app = (
            Application.objects.for_org(application.organisation_id)
            .select_for_update()
            .get(pk=application.pk)
        )
        if app.status not in (Status.INTERVIEW, Status.OFFER):
            raise DomainError(
                "invalid_state",
                "Offers can be made after an interview.",
                409,
                {"status": app.status},
            )
        try:
            with transaction.atomic():
                offer = Offer.objects.create(
                    organisation_id=app.organisation_id,
                    application=app,
                    created_by=actor,
                    required_approvals=required,
                    **terms,
                )
        except IntegrityError:
            raise ConflictError(
                code="offer_exists", message="This application already has an open offer."
            ) from None
        audit.record(
            actor=actor,
            action="offers.drafted",
            target=offer,
            organisation=app.organisation_id,
            after={"currency": offer.currency, "required_approvals": required},
        )
    return offer


def update_draft(offer: Offer, *, actor: Any, data: dict[str, Any], lock_version: int) -> Offer:
    _membership(actor, offer.organisation_id, "offers.manage")
    with transaction.atomic():
        o = _locked(offer)
        _require(o, OfferStatus.DRAFT)
        if o.lock_version != lock_version:
            raise ConflictError(
                code="stale_version", message="The offer changed; reload and try again."
            )
        for name, value in _clean_terms(data, o).items():
            setattr(o, name, value)
        o.lock_version += 1
        o.save()
        audit.record(actor=actor, action="offers.updated", target=o, organisation=o.organisation_id)
    return o


def submit_for_approval(offer: Offer, *, actor: Any) -> Offer:
    _membership(actor, offer.organisation_id, "offers.manage")
    with transaction.atomic():
        o = _locked(offer)
        _require(o, OfferStatus.DRAFT)
        _clean_terms({}, o)  # still valid (dates may have passed while it was a draft)
        o.status = OfferStatus.PENDING_APPROVAL
        o.lock_version += 1
        o.save(update_fields=["status", "lock_version", "updated_at"])
        audit.record(
            actor=actor, action="offers.submitted", target=o, organisation=o.organisation_id
        )
    return o


def approve(offer: Offer, *, actor: Any, comment: str = "") -> Offer:
    _membership(actor, offer.organisation_id, "offers.approve")
    with transaction.atomic():
        o = _locked(offer)
        _require(o, OfferStatus.PENDING_APPROVAL)
        if o.created_by_id == getattr(actor, "pk", None):
            raise PermissionDeniedError(
                message="The person who drafted the offer can't approve it."
            )
        try:
            with transaction.atomic():
                OfferApproval.objects.create(
                    organisation_id=o.organisation_id,
                    offer=o,
                    approver=actor,
                    round=o.approval_round,
                    decision=ApprovalDecision.APPROVED,
                    comment=comment.strip()[:2000],
                    at=mhrs_time.now(),
                )
        except IntegrityError:
            raise ConflictError(
                code="already_approved", message="You already approved this offer."
            ) from None
        count = (
            OfferApproval.objects.for_org(o.organisation_id)
            .filter(offer=o, round=o.approval_round, decision=ApprovalDecision.APPROVED)
            .count()
        )
        if count >= o.required_approvals:
            o.status = OfferStatus.APPROVED
        o.lock_version += 1
        o.save(update_fields=["status", "lock_version", "updated_at"])
        audit.record(
            actor=actor,
            action="offers.approved",
            target=o,
            organisation=o.organisation_id,
            after={"approvals": count, "required": o.required_approvals, "status": o.status},
        )
    return o


def return_for_changes(offer: Offer, *, actor: Any, comment: str) -> Offer:
    _membership(actor, offer.organisation_id, "offers.approve")
    text = _reason(comment, "comment")
    with transaction.atomic():
        o = _locked(offer)
        _require(o, OfferStatus.PENDING_APPROVAL, OfferStatus.APPROVED)
        # an approver may change their mind in the same round: their latest decision counts
        OfferApproval.objects.for_org(o.organisation_id).update_or_create(
            offer=o,
            approver=actor,
            round=o.approval_round,
            defaults={
                "organisation_id": o.organisation_id,
                "decision": ApprovalDecision.RETURNED,
                "comment": text,
                "at": mhrs_time.now(),
            },
        )
        o.status = OfferStatus.DRAFT
        o.approval_round += 1  # earlier approvals no longer count
        o.lock_version += 1
        o.save(update_fields=["status", "approval_round", "lock_version", "updated_at"])
        audit.record(
            actor=actor,
            action="offers.returned",
            target=o,
            organisation=o.organisation_id,
            reason=text,
        )
    return o


# --- issuing --------------------------------------------------------------------------------------
def _store_letter(o: Offer) -> Document:
    pdf = letter.render(o)
    app = o.application
    key = f"offers/{o.organisation_id}/{o.pk}/offer-letter-r{o.approval_round}.pdf"
    storage.put_bytes("documents", key, pdf, "application/pdf")
    return Document.objects.create(
        owner_user=app.candidate_user,
        organisation_id=o.organisation_id,
        purpose=Purpose.OFFER_LETTER,
        original_filename=f"Offer letter - {app.job.title}.pdf"[:200],
        declared_mime="application/pdf",
        mime_detected="application/pdf",
        size_bytes=len(pdf),
        sha256=hashlib.sha256(pdf).hexdigest(),
        storage_key=key,
        bucket="documents",
        page_count=None,
        scan_status=ScanStatus.CLEAN,
        scan_engine_version="generated",
        scanned_at=mhrs_time.now(),
    )


def issue(offer: Offer, *, actor: Any) -> Offer:
    """EC-OFF-01: only approved offers are issued; moves the application to ``offer`` (human)."""
    _membership(actor, offer.organisation_id, "offers.manage")
    with transaction.atomic():
        o = _locked(offer)
        if o.status != OfferStatus.APPROVED:
            raise DomainError(
                "offer_not_approved",
                "An offer can only be issued after the required approvals.",
                409,
                {"status": o.status},
            )
        if o.expires_at <= mhrs_time.now():
            raise DomainError(
                "validation_error",
                "The deadline has passed; change it first.",
                422,
                {"expires_at": ["In the past."]},
            )
        app = o.application
        if app.status == Status.INTERVIEW:
            transition(
                app,
                Status.OFFER,
                actor=actor,
                reason="Offer issued after approval",
                reason_code="",
                metadata={"offer_id": str(o.pk)},
            )
        elif app.status != Status.OFFER:
            raise DomainError(
                "invalid_state", "The application is no longer open.", 409, {"status": app.status}
            )
        o.letter_document = _store_letter(o)
        o.status = OfferStatus.ISSUED
        o.issued_at, o.issued_by = mhrs_time.now(), actor
        o.lock_version += 1
        o.save()
        audit.record(
            actor=actor,
            action="offers.issued",
            target=o,
            organisation=o.organisation_id,
            after={"letter_sha256": o.letter_document.sha256},
        )
        notifications.notify(
            app.candidate_user,
            "offer_issued",
            {
                "organisation_name": app.organisation.name,
                "job_title": app.job.title,
                "offer_url": _offer_url(app),
                "deadline": format_when(o.expires_at, app.organisation.default_timezone),
            },
            dedupe_key=f"offer_issued:{o.pk}:{o.approval_round}",
            organisation=app.organisation,
        )
    return o


# --- candidate answers ----------------------------------------------------------------------------
def _own(offer: Offer, candidate: Any) -> Offer:
    o = _locked(offer)
    if o.application.candidate_user_id != getattr(candidate, "pk", None):
        raise PermissionDeniedError(message="This is not your offer.")
    return o


def _normalise(name: str) -> str:
    return " ".join(name.casefold().split())


def accept(
    offer: Offer,
    *,
    candidate: Any,
    typed_name: str,
    agree: bool,
    ip: str | None = None,
    user_agent: str = "",
    counter_offer_note: str = "",
) -> tuple[Offer, dict[str, int | bool]]:
    """Electronic acceptance: typed full name matching the account + acceptance statement ticked."""
    with transaction.atomic():
        o = _own(offer, candidate)
        _require(o, OfferStatus.ISSUED)
        if o.expires_at <= mhrs_time.now():
            raise DomainError("offer_expired", "This offer has expired.", 409)
        expected = _normalise(candidate.full_name or "")
        errors: dict[str, list[str]] = {}
        if not expected or _normalise(typed_name) != expected:
            errors["typed_name"] = ["Type your full name exactly as it appears on your account."]
        if not agree:
            errors["agree"] = ["Tick the statement to accept the offer."]
        if errors:
            raise DomainError("validation_error", "The acceptance is not complete.", 422, errors)
        now = mhrs_time.now()
        o.status = OfferStatus.ACCEPTED
        o.accepted_at = now
        o.counter_offer_note = counter_offer_note.strip()[:2000]
        o.acceptance_meta = {
            "typed_name": typed_name.strip()[:200],
            "statement": f"I accept this offer of employment ({ACCEPT_STATEMENT_VERSION})",
            "accepted_at": now.isoformat(),
            "ip_prefix": truncate_ip(ip),
            "user_agent_sha256": hashlib.sha256(user_agent.encode()).hexdigest()
            if user_agent
            else "",
            "letter_sha256": o.letter_document.sha256 if o.letter_document else "",
        }
        o.lock_version += 1
        o.save()
        app = o.application
        audit.record(
            actor=candidate,
            action="offers.accepted",
            target=o,
            organisation=o.organisation_id,
            actor_type="human",
            after={"ip_prefix": o.acceptance_meta["ip_prefix"]},
        )
        counter = openings(app.job)
        note = (
            f"{counter['accepted']} accepted offer(s) for {counter['openings']} opening(s): "
            "more than the "
            "openings - please decide how to proceed."
            if counter["over"]
            else f"{counter['openings'] - counter['remaining']} of {counter['openings']} "
            "opening(s) now filled."
        )
        for user in _hr_recipients(o):
            notifications.notify(
                user,
                "offer_accepted",
                {
                    "job_title": app.job.title,
                    "reference": app.reference,
                    "offer_url": _offer_url(app, staff=True),
                    "openings_note": note,
                },
                dedupe_key=f"offer_accepted:{o.pk}:{user.pk}",
                organisation=app.organisation,
            )
    return o, counter


def decline(offer: Offer, *, candidate: Any, reason: str = "") -> Offer:
    with transaction.atomic():
        o = _own(offer, candidate)
        _require(o, OfferStatus.ISSUED)
        o.status = OfferStatus.DECLINED
        o.declined_at = mhrs_time.now()
        o.decline_reason = reason.strip()[:2000]
        o.lock_version += 1
        o.save()
        app = o.application
        transition(
            app,
            Status.OFFER_DECLINED,
            actor=candidate,
            actor_type="human",
            reason=o.decline_reason or "Offer declined by the candidate",
        )
        audit.record(
            actor=candidate,
            action="offers.declined",
            target=o,
            organisation=o.organisation_id,
            actor_type="human",
        )
        for user in _hr_recipients(o):
            notifications.notify(
                user,
                "offer_declined",
                {
                    "job_title": app.job.title,
                    "reference": app.reference,
                    "offer_url": _offer_url(app, staff=True),
                },
                dedupe_key=f"offer_declined:{o.pk}:{user.pk}",
                organisation=app.organisation,
            )
    return o


# --- employer withdrawal, expiry ------------------------------------------------------------------
def withdraw(offer: Offer, *, actor: Any, reason: str) -> Offer:
    """The employer withdraws an open offer. The application stays at ``offer``; a person then
    records ``not_selected`` (ADR-030), issues a new offer or reopens it."""
    _membership(actor, offer.organisation_id, "offers.approve")
    text = _reason(reason)
    with transaction.atomic():
        o = _locked(offer)
        _require(
            o,
            OfferStatus.DRAFT,
            OfferStatus.PENDING_APPROVAL,
            OfferStatus.APPROVED,
            OfferStatus.ISSUED,
            OfferStatus.ACCEPTED,
        )
        was_with_candidate = o.status in (OfferStatus.ISSUED, OfferStatus.ACCEPTED)
        o.status = OfferStatus.WITHDRAWN
        o.closed_at, o.close_reason = mhrs_time.now(), text
        o.lock_version += 1
        o.save()
        HireRecord.objects.for_org(o.organisation_id).filter(
            offer=o, cancelled_at__isnull=True
        ).update(cancelled_at=o.closed_at, cancel_reason="Offer withdrawn")
        app = o.application
        audit.record(
            actor=actor,
            action="offers.withdrawn",
            target=o,
            organisation=o.organisation_id,
            reason=text,
        )
        if was_with_candidate:
            notifications.notify(
                app.candidate_user,
                "offer_withdrawn",
                {
                    "organisation_name": app.organisation.name,
                    "job_title": app.job.title,
                    "reason": text,
                    "application_url": f"{settings.FRONTEND_URL}/candidate/applications/{app.pk}",
                },
                dedupe_key=f"offer_withdrawn:{o.pk}",
                organisation=app.organisation,
            )
    return o


def on_application_withdrawn(application_id: Any) -> int:
    """EC-OFF-04: the candidate withdrew the application (possibly after accepting)."""
    app = Application.objects.unscoped().filter(pk=application_id).first()
    if app is None or app.status != Status.WITHDRAWN:
        return 0
    changed = 0
    with transaction.atomic():
        for o in (
            Offer.objects.for_org(app.organisation_id)
            .select_for_update()
            .filter(application=app, status__in=LIVE_STATUSES)
        ):
            o.status = OfferStatus.WITHDRAWN
            o.closed_at, o.close_reason = mhrs_time.now(), "The candidate withdrew the application"
            o.lock_version += 1
            o.save()
            audit.record(
                action="offers.withdrawn_by_candidate",
                target=o,
                organisation=o.organisation_id,
                actor_type="system",
            )
            changed += 1
        HireRecord.objects.for_org(app.organisation_id).filter(
            application=app, cancelled_at__isnull=True
        ).update(
            cancelled_at=mhrs_time.now(), cancel_reason="The candidate withdrew the application"
        )
    return changed


def expire_due(now: datetime | None = None) -> dict[str, int]:
    """EC-OFF-02 (beat): expire overdue issued offers (HR told); remind candidates 48 h before."""
    now = now or mhrs_time.now()
    result = {"expired": 0, "reminded": 0}
    for pk in (
        Offer.objects.unscoped()
        .filter(status=OfferStatus.ISSUED, expires_at__lte=now)
        .values_list("pk", flat=True)
    ):
        with transaction.atomic():
            o = (
                Offer.objects.unscoped()
                .select_for_update(skip_locked=True)
                .select_related("application__job", "application__organisation")
                .filter(pk=pk, status=OfferStatus.ISSUED)
                .first()
            )
            if o is None:
                continue
            o.status = OfferStatus.EXPIRED
            o.closed_at, o.close_reason = now, "No answer before the deadline"
            o.lock_version += 1
            o.save()
            app = o.application
            audit.record(
                action="offers.expired",
                target=o,
                organisation=o.organisation_id,
                actor_type="system",
            )
            for user in _hr_recipients(o):
                notifications.notify(
                    user,
                    "offer_expired",
                    {
                        "job_title": app.job.title,
                        "reference": app.reference,
                        "offer_url": _offer_url(app, staff=True),
                    },
                    dedupe_key=f"offer_expired:{o.pk}:{user.pk}",
                    organisation=app.organisation,
                )
            result["expired"] += 1
    due = Offer.objects.unscoped().filter(
        status=OfferStatus.ISSUED,
        expires_at__gt=now,
        expires_at__lte=now + EXPIRY_REMINDER,
        expiry_reminder_sent_at__isnull=True,
    )
    for pk in due.values_list("pk", flat=True):
        with transaction.atomic():
            o = (
                Offer.objects.unscoped()
                .select_for_update(skip_locked=True)
                .select_related(
                    "application__job", "application__organisation", "application__candidate_user"
                )
                .filter(pk=pk, expiry_reminder_sent_at__isnull=True)
                .first()
            )
            if o is None:
                continue
            o.expiry_reminder_sent_at = now
            o.save(update_fields=["expiry_reminder_sent_at", "updated_at"])
            app = o.application
            notifications.notify(
                app.candidate_user,
                "offer_expiring",
                {
                    "organisation_name": app.organisation.name,
                    "job_title": app.job.title,
                    "offer_url": _offer_url(app),
                    "deadline": format_when(o.expires_at, app.organisation.default_timezone),
                },
                dedupe_key=f"offer_expiring:{o.pk}:{o.approval_round}",
                organisation=app.organisation,
            )
            result["reminded"] += 1
    return result
