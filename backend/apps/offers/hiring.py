"""Hiring close-out (docs/01 M17, P12-T05).

* ``record_hire`` - HR confirms the person after an **accepted** offer: hire record (separate from
  screening data), application ``offer -> hired`` (a human decision), audit. The result says whether
  every opening is now filled so the UI can *prompt* to close the vacancy - closing stays a
  separate, deliberate action.
* ``closeout_preview`` / ``confirm_closeout`` - final outcome messages to the remaining applicants
  happen **only after a person confirms** the exact list they previewed: the preview returns a
  fingerprint of the affected applications, and the confirmation is refused if anything changed in
  between. Each application goes through the same single-application decision service
  (``ats.hr_transition``: permission, reason code, audit, the organisation's notification delay with
  undo), so close-out can never do more than the person could do one by one. Applications still
  being processed, or with a live offer, are left alone and listed.
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

from django.db import transaction

from apps.applications import ats
from apps.applications.hr import applications_visible_to
from apps.applications.models import Status
from apps.audit import services as audit
from apps.core import time as mhrs_time
from apps.core.exceptions import ConflictError, DomainError, NotFoundError, PermissionDeniedError
from apps.jobs.assignments import jobs_visible_to
from apps.jobs.models import Job, JobStatus
from apps.organisations import rbac
from apps.organisations.models import Membership

from .models import LIVE_STATUSES, HireRecord, Offer, OfferStatus
from .services import openings

CLOSABLE = (Status.UNDER_REVIEW, Status.ON_HOLD, Status.SHORTLISTED, Status.INTERVIEW, Status.OFFER)
IN_PROGRESS = (
    Status.SUBMITTED,
    Status.PROCESSING,
    Status.NEEDS_INFORMATION,
    Status.PROCESSING_ERROR,
)
MAX_CLOSEOUT = 1000


def record_hire(
    membership: Membership,
    actor: Any,
    offer_id: Any,
    *,
    start_date: date | None = None,
    note: str = "",
) -> dict[str, Any]:
    if not rbac.can(membership.role, "hires.record"):
        raise PermissionDeniedError(message="Only HR managers can record a hire.")
    with transaction.atomic():
        offer = (
            Offer.objects.for_org(membership.organisation_id)
            .select_for_update()
            .select_related("application__job")
            .filter(pk=offer_id)
            .first()
        )
        if offer is None:
            raise NotFoundError()
        if offer.status != OfferStatus.ACCEPTED:
            raise DomainError(
                "offer_not_accepted",
                "A hire can only be recorded after the offer is accepted.",
                409,
            )
        app = offer.application
        start = start_date or offer.start_date
        text = f"Hire confirmed; starts {start:%d %B %Y}" + (
            f". {note.strip()}" if note.strip() else ""
        )
        ats.hr_transition(membership, actor, app.pk, to_status=Status.HIRED, reason_text=text[:500])
        if HireRecord.objects.for_org(app.organisation_id).filter(application=app).exists():
            raise ConflictError(code="hire_exists", message="A hire is already recorded.")
        hire = HireRecord.objects.create(
            organisation_id=app.organisation_id,
            application=app,
            offer=offer,
            start_date=start,
            recorded_by=actor,
            recorded_at=mhrs_time.now(),
        )
        audit.record(
            actor=actor,
            action="hiring.hire_recorded",
            target=hire,
            organisation=app.organisation_id,
            after={"start_date": start.isoformat(), "offer_id": str(offer.pk)},
        )
        counter = openings(app.job)
        job = app.job
    return {
        "hire": hire,
        "openings": counter,
        # prompt only: closing the vacancy is a separate, explicit action (jobs.close)
        "prompt_close": counter["remaining"] == 0
        and job.status in (JobStatus.PUBLISHED, JobStatus.PAUSED),
    }


# --- close-out ------------------------------------------------------------------------------------
def _job(membership: Membership, job_id: Any) -> Job:
    job = jobs_visible_to(membership).filter(pk=job_id).first()
    if job is None:
        raise NotFoundError()
    return job


def closeout_preview(membership: Membership, job_id: Any) -> dict[str, Any]:
    if not rbac.can(membership.role, "applications.decide"):
        raise PermissionDeniedError(message="Only HR managers can close out a vacancy.")
    job = _job(membership, job_id)
    apps = list(
        applications_visible_to(membership)
        .filter(job=job)
        .exclude(status__in=(Status.DRAFT, Status.ABANDONED))
        .values("pk", "status", "reference")
    )
    live = set(
        Offer.objects.for_org(job.organisation_id)
        .filter(application__job=job, status__in=LIVE_STATUSES)
        .values_list("application_id", flat=True)
    )
    to_notify, in_progress, open_offers = [], [], []
    for a in apps:
        if a["status"] in IN_PROGRESS:
            in_progress.append(a)
        elif a["pk"] in live:
            open_offers.append(a)
        elif a["status"] in CLOSABLE:
            to_notify.append(a)
    ids = sorted(str(a["pk"]) for a in to_notify)
    fingerprint = hashlib.sha256(("|".join(ids)).encode()).hexdigest()[:32]
    by_status: dict[str, int] = {}
    for a in to_notify:
        by_status[a["status"]] = by_status.get(a["status"], 0) + 1
    return {
        "job_id": str(job.pk),
        "openings": openings(job),
        "to_notify": len(to_notify),
        "to_notify_by_status": by_status,
        "still_in_progress": [
            {"id": str(a["pk"]), "reference": a["reference"]} for a in in_progress
        ],
        "with_open_offer": [{"id": str(a["pk"]), "reference": a["reference"]} for a in open_offers],
        "fingerprint": fingerprint,
        "_ids": ids,
    }


def confirm_closeout(
    membership: Membership,
    actor: Any,
    job_id: Any,
    *,
    fingerprint: str,
    reason_code: str = "position_filled",
    reason_text: str = "",
) -> dict[str, Any]:
    """Move every previewed application to ``not_selected`` (human decision, delayed message)."""
    preview = closeout_preview(membership, job_id)
    if fingerprint != preview["fingerprint"]:
        raise ConflictError(
            code="closeout_changed",
            message="The applications changed since you reviewed them. Review the list again.",
            details={"to_notify": preview["to_notify"]},
        )
    ids = preview["_ids"]
    if not ids:
        raise DomainError("nothing_to_close", "There are no remaining applications to notify.", 409)
    if len(ids) > MAX_CLOSEOUT:
        raise DomainError(
            "validation_error", f"At most {MAX_CLOSEOUT} applications at a time.", 422
        )
    done, skipped = [], []
    for app_id in ids:
        try:
            with transaction.atomic():
                ats.hr_transition(
                    membership,
                    actor,
                    app_id,
                    to_status=Status.NOT_SELECTED,
                    reason_code=reason_code,
                    reason_text=reason_text,
                )
            done.append(app_id)
        except (DomainError, PermissionDeniedError, NotFoundError) as exc:
            skipped.append({"application_id": app_id, "reason": getattr(exc, "code", "error")})
    audit.record(
        actor=actor,
        action="hiring.closeout_confirmed",
        target=("jobs.Job", job_id),
        organisation=membership.organisation_id,
        after={"notified": len(done), "skipped": len(skipped), "reason_code": reason_code},
    )
    return {"notified": len(done), "skipped": skipped}
