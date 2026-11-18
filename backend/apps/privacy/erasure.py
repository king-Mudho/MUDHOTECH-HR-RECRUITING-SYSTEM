"""Deletion and anonymisation (P09-T04; EC-PRV-01/02/05, EC-ACC-13; CDPA right to erasure).

``erase(user, organisation_id)`` removes a person's data held for one employer;
``organisation_id=None`` (an account-level request) does it for every employer and then
anonymises the account itself.

* Legal holds win: if any active hold covers the person, one of their applications or its vacancy,
  nothing is erased and ``LegalHoldError`` says so (the request goes ``on_hold``; EC-PRV-01).
* Active applications are first withdrawn by the person (EC-PRV-02 / EC-ACC-13), through the state
  machine, so the employer's records stay consistent.
* Personal data is replaced, not just hidden: the profile snapshot, answers, clarification
  answers, messages, notes, extraction text and claims, evidence snippets and explanations, and
  notification payloads; files are deleted from storage (EC-PRV-05: in versioned buckets this
  writes a delete marker and the lifecycle rule expires old versions).
* What remains is minimal and anonymous: ids, statuses, dates, scores and the audit trail (which
  records counts and ids only). Backups expire on their own schedule (EC-PRV-10).
"""

from __future__ import annotations

import logging
import uuid
from collections import Counter
from typing import Any

from django.db import transaction

from apps.audit import services as audit
from apps.core import storage
from apps.core.exceptions import ConflictError
from apps.core.time import now

from .services import is_held

log = logging.getLogger("mhrs.privacy")
ERASED = "[erased]"
TERMINAL = ("hired", "not_selected", "withdrawn", "offer_declined", "abandoned", "draft")


class LegalHoldError(ConflictError):
    code = "legal_hold"
    default_message = "Some of this data is under a legal hold and cannot be deleted yet."


def _held(user: Any, applications: list[Any]) -> bool:
    for app in applications:
        if is_held(
            app.organisation_id,
            application_id=app.pk,
            candidate_id=user.pk,
            job_id=app.job_id,
        ):
            return True
    return False


def _delete_file(doc: Any, counts: Counter[str]) -> None:
    if doc.deleted_at is not None:
        return
    try:
        storage.delete_object(doc.bucket or "documents", doc.storage_key)
    except Exception:  # storage outage: the row is still marked, a retention run retries
        log.warning("erasure: could not delete object", extra={"document_id": str(doc.pk)})
        counts["files_failed"] += 1
        return
    doc.original_filename = ERASED
    doc.storage_key = f"erased/{doc.pk}"
    doc.deleted_at = now()
    doc.save(update_fields=["original_filename", "storage_key", "deleted_at", "updated_at"])
    counts["files"] += 1


def _erase_application(app: Any, counts: Counter[str]) -> None:
    from apps.applications.models import ApplicationDocument, ApplicationNote
    from apps.messaging.models import ClarificationRequest, Message
    from apps.questionnaires.models import QuestionResponse
    from apps.resumes.models import ExtractionRun
    from apps.screening.models import Evaluation, EvaluationEvidence, HumanVerification

    org = app.organisation_id
    app.candidate_profile_snapshot = {"erased": True}
    app.withdraw_reason = ""
    app.save(update_fields=["candidate_profile_snapshot", "withdraw_reason", "updated_at"])
    counts["responses"] += (
        QuestionResponse.objects.for_org(org).filter(application=app).update(value=None)
    )
    for clar in ClarificationRequest.objects.for_org(org).filter(application=app):
        clar.answers = [{"id": a.get("id"), "text": ERASED} for a in clar.answers or []]
        clar.save(update_fields=["answers", "updated_at"])
    counts["messages"] += (
        Message.objects.unscoped()
        .filter(thread__application=app)
        .update(body=ERASED, attachment_document_ids=[])
    )
    counts["notes"] += (
        ApplicationNote.objects.for_org(org).filter(application=app).update(body=ERASED)
    )
    counts["extraction_runs"] += (
        ExtractionRun.objects.for_org(org).filter(application=app).delete()[0]
    )
    counts["evidence"] += (
        EvaluationEvidence.objects.for_org(org)
        .filter(criterion_result__evaluation__application=app)
        .update(snippet="")
    )
    Evaluation.objects.for_org(org).filter(application=app).update(explanation="", summary="")
    HumanVerification.objects.for_org(org).filter(application=app).update(
        corrected_payload="", note=""
    )
    # interview feedback written about the person (P12): notes go, numeric ratings stay so the
    # organisation's interview statistics remain consistent (they no longer identify anyone)
    from apps.interviews.models import Interview, Scorecard

    counts["scorecards"] += (
        Scorecard.objects.for_org(org)
        .filter(interview__application=app)
        .update(criterion_notes="", notes="")
    )
    Interview.objects.for_org(org).filter(application=app).update(status_reason="")
    for link in (
        ApplicationDocument.objects.for_org(org).filter(application=app).select_related("document")
    ):
        _delete_file(link.document, counts)
    counts["applications"] += 1


def erase(user: Any, organisation_id: Any = None, *, actor: Any = None) -> dict[str, int]:
    """Erase the person's data for one employer (or everything, ``organisation_id=None``)."""
    from apps.applications.models import Application
    from apps.applications.services import transition
    from apps.notifications.models import Notification

    apps = list(
        Application.objects.unscoped()
        .filter(candidate_user=user)
        .exclude(status__in=["draft"])
        .select_related("organisation")
    )
    if organisation_id is not None:
        apps = [a for a in apps if str(a.organisation_id) == str(organisation_id)]
    if _held(user, apps):
        raise LegalHoldError()
    counts: Counter[str] = Counter()
    with transaction.atomic():
        for app in apps:
            if app.status not in TERMINAL:
                app = transition(
                    app,
                    "withdrawn",
                    actor=user,
                    actor_type="candidate",
                    reason="Withdrawn because the candidate asked for their data to be deleted",
                    metadata={"via": "erasure"},
                )
                counts["withdrawn"] += 1
            _erase_application(app, counts)
        notes = Notification.objects.filter(recipient_user=user)
        if organisation_id is not None:
            notes = notes.filter(organisation_id=organisation_id)
        counts["notifications"] += notes.update(payload={})
        if organisation_id is None:
            _erase_account(user, counts)
        audit.record(
            actor=actor,
            actor_type="human" if actor is not None else "system",
            action="privacy.erased",
            target=("user", str(user.pk)),
            organisation=organisation_id,
            after=dict(counts),
        )
    return dict(counts)


def _erase_account(user: Any, counts: Counter[str]) -> None:
    from allauth.account.models import EmailAddress

    from apps.candidates.models import CandidateProfile
    from apps.documents.models import Document
    from apps.resumes.models import ResumeParse

    for doc in Document.objects.filter(owner_user=user):
        _delete_file(doc, counts)
    ResumeParse.objects.filter(owner_user=user).delete()
    counts["profile"] += CandidateProfile.objects.filter(user=user).delete()[0]
    EmailAddress.objects.filter(user=user).delete()
    token = uuid.uuid4().hex[:12]
    user.email = f"erased-{token}@erased.invalid"
    user.first_name = ""
    user.last_name = ""
    user.is_active = False
    user.set_unusable_password()
    user.save()
    counts["account"] += 1


def residual_pii(user_id: Any, values: list[str]) -> dict[str, int]:
    """Verification (exit criterion): occurrences of the person's former identifiers left in the
    database tables that held them. Used by ``verify_erasure`` and the tests."""
    from django.db.models import Q

    from apps.accounts.models import User
    from apps.applications.models import Application
    from apps.documents.models import Document
    from apps.messaging.models import Message

    found: dict[str, int] = {}
    terms = [v for v in values if v and len(v) >= 3]
    if not terms:
        return found
    user_q = Q()
    snap_q = Q()
    doc_q = Q()
    for term in terms:
        user_q |= Q(email__icontains=term) | Q(first_name__iexact=term) | Q(last_name__iexact=term)
        snap_q |= Q(candidate_profile_snapshot__icontains=term)
        doc_q |= Q(original_filename__icontains=term)
    checks = {
        "users": User.objects.filter(pk=user_id).filter(user_q).count(),
        "application_snapshots": Application.objects.unscoped()
        .filter(candidate_user_id=user_id)
        .filter(snap_q)
        .count(),
        "documents": Document.objects.filter(owner_user_id=user_id, deleted_at__isnull=True).count()
        + Document.objects.filter(owner_user_id=user_id).filter(doc_q).count(),
        "messages": Message.objects.unscoped()
        .filter(thread__application__candidate_user_id=user_id)
        .exclude(body=ERASED)
        .count(),
    }
    return {k: v for k, v in checks.items() if v}
