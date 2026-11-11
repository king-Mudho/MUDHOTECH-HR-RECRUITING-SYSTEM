"""Clarifications and messages (P05-T06). Writes only happen here; views stay thin."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

import nh3
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import QuerySet

from apps.applications.hr import PRIVATE_STATUSES, applications_visible_to
from apps.applications.models import Application, Status
from apps.applications.services import get_own, transition
from apps.audit import services as audit
from apps.core import outbox
from apps.core.exceptions import ConflictError, DomainError, NotFoundError
from apps.core.time import now
from apps.documents.models import Document, Purpose, ScanStatus
from apps.jobs.models import JobAssignment
from apps.notifications import delivery as notifications
from apps.organisations.models import Membership
from apps.organisations.selectors import active_membership

from .models import (
    ClarificationRequest,
    ClarificationStatus,
    Message,
    MessageThread,
    SenderRole,
)

MAX_QUESTIONS = 5
MAX_TEXT = 5000
MAX_ATTACHMENTS = 3
MIN_DUE = timedelta(hours=1)
MAX_DUE = timedelta(days=30)
REMIND_BEFORE = timedelta(hours=24)
ASKABLE_FROM = {Status.UNDER_REVIEW, Status.PROCESSING}
BAD_SCANS = {ScanStatus.INFECTED, ScanStatus.REJECTED}

# Ready-made questions recruiters can start from (free text is always allowed too).
QUESTION_TEMPLATES: list[dict[str, Any]] = [
    {
        "key": "confirm_qualification",
        "prompt": "Please confirm the qualification you hold and the year you completed it.",
        "allow_upload": True,
    },
    {
        "key": "experience_detail",
        "prompt": "Please describe your experience with the requirement below in more detail.",
        "allow_upload": False,
    },
    {
        "key": "availability",
        "prompt": "When could you start, and what is your notice period?",
        "allow_upload": False,
    },
    {
        "key": "missing_document",
        "prompt": "Please upload the document that was missing from your application.",
        "allow_upload": True,
    },
    {
        "key": "work_authorisation",
        "prompt": "Please confirm you may legally work where this vacancy is based.",
        "allow_upload": False,
    },
]


def plain(text: Any, limit: int = MAX_TEXT) -> str:
    """User text as plain text: every tag removed, trimmed, bounded."""
    return nh3.clean(str(text or ""), tags=set()).strip()[:limit]


def _site() -> str:
    return str(settings.FRONTEND_URL).rstrip("/")


def _clarification_url(app: Application) -> str:
    return f"{_site()}/candidate/applications/{app.pk}#clarifications"


def _candidate_name(app: Application) -> str:
    snap = app.candidate_profile_snapshot or {}
    name = " ".join(p for p in (snap.get("first_name"), snap.get("last_name")) if p)
    return name or "A candidate"


def staff_recipients(app: Application, *extra: Any) -> list[Any]:
    """Assigned recruiters (active) plus anyone passed in, without duplicates."""
    users = {
        a.membership.user_id: a.membership.user
        for a in JobAssignment.objects.for_org(app.organisation_id)
        .filter(
            job_id=app.job_id, role_on_job="recruiter", membership__status=Membership.Status.ACTIVE
        )
        .select_related("membership__user")
    }
    for user in extra:
        if user is not None and getattr(user, "is_active", False):
            users[user.pk] = user
    return list(users.values())


def _visible_application(membership: Membership, application_id: Any) -> Application:
    app = (
        applications_visible_to(membership)
        .select_related("job", "organisation")
        .filter(pk=application_id)
        .first()
    )
    if app is None:
        raise NotFoundError()
    return app


# ------------------------------------------------------------------------ clarifications
def _clean_questions(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not raw or len(raw) > MAX_QUESTIONS:
        raise DomainError(
            "validation_error",
            f"Ask between 1 and {MAX_QUESTIONS} questions.",
            details={"questions": [f"Between 1 and {MAX_QUESTIONS} questions."]},
        )
    out = []
    for item in raw:
        prompt = plain(item.get("prompt"), 1000)
        if not prompt:
            raise DomainError(
                "validation_error",
                "Every question needs some text.",
                details={"questions": ["Empty question."]},
            )
        out.append(
            {
                "id": uuid.uuid4().hex[:12],
                "prompt": prompt,
                "allow_upload": bool(item.get("allow_upload")),
            }
        )
    return out


def request_clarification(
    membership: Membership,
    actor: Any,
    application_id: Any,
    *,
    questions: list[dict[str, Any]],
    due_at: datetime,
    message: str = "",
    criterion_id: Any = None,
) -> ClarificationRequest:
    app = _visible_application(membership, application_id)
    if app.status not in ASKABLE_FROM:
        raise ConflictError(
            "conflict.invalid_transition",
            "You can only ask for clarification while an application is being reviewed.",
        )
    if not (now() + MIN_DUE <= due_at <= now() + MAX_DUE):
        raise DomainError(
            "validation_error",
            "Choose a due date between one hour and 30 days from now.",
            details={"due_at": ["Between one hour and 30 days from now."]},
        )
    cleaned = _clean_questions(questions)
    try:
        with transaction.atomic():
            req = ClarificationRequest.objects.create(
                organisation_id=app.organisation_id,
                application=app,
                criterion_id=criterion_id,
                message=plain(message, 2000),
                questions=cleaned,
                due_at=due_at,
                requested_by=actor,
                previous_status=app.status,
            )
            transition(
                app, Status.NEEDS_INFORMATION, actor=actor, reason_code="clarification_requested"
            )
            audit.record(
                actor=actor,
                action="clarification.requested",
                target=req,
                organisation=app.organisation_id,
                after={"application_id": str(app.pk), "questions": len(cleaned)},
            )
            outbox.emit(
                "clarification.requested",
                req,
                {"clarification_id": str(req.pk), "application_id": str(app.pk)},
                dedupe_key=f"clarification.requested:{req.pk}",
            )
            notifications.notify(
                app.candidate_user,
                "clarification_requested",
                {
                    "organisation_name": app.organisation.name,
                    "job_title": app.job.title,
                    "due_date": due_at.strftime("%d %B %Y"),
                    "clarification_url": _clarification_url(app),
                    "application_id": app.pk,
                },
                dedupe_key=f"clarification_requested:{req.pk}",
                organisation=app.organisation_id,
            )
    except IntegrityError:
        raise ConflictError(
            "conflict.clarification_open", "There is already an open clarification request."
        ) from None
    return req


def staff_clarifications(
    membership: Membership, application_id: Any
) -> QuerySet[ClarificationRequest]:
    app = _visible_application(membership, application_id)
    return ClarificationRequest.objects.for_org(app.organisation_id).filter(application=app)


def own_clarifications(user: Any, application_id: Any) -> QuerySet[ClarificationRequest]:
    app = get_own(user, application_id)
    return ClarificationRequest.objects.for_org(app.organisation_id).filter(application=app)


def _owned_document(user: Any, document_id: Any, purposes: set[str]) -> Document:
    doc = Document.objects.filter(
        pk=document_id, owner_user=user, deleted_at__isnull=True, purpose__in=purposes
    ).first()
    if doc is None or doc.scan_status in BAD_SCANS:
        raise DomainError(
            "validation_error",
            "That file can't be used. Please upload it again.",
            details={"document_id": ["Unknown or unusable file."]},
        )
    return doc


def answer_clarification(
    user: Any, application_id: Any, clarification_id: Any, answers: list[dict[str, Any]]
) -> ClarificationRequest:
    with transaction.atomic():
        app = get_own(user, application_id, lock=True)
        req = (
            ClarificationRequest.objects.for_org(app.organisation_id)
            .select_for_update()
            .filter(pk=clarification_id, application=app)
            .first()
        )
        if req is None:
            raise NotFoundError()
        if req.status != ClarificationStatus.OPEN:
            raise ConflictError(
                "conflict.clarification_closed",
                "This request is no longer open. You can still send the employer a message.",
                details={"status": req.status},
            )
        given = {str(a.get("id")): a for a in answers}
        stored, errors = [], {}
        for q in req.questions:
            a = given.get(q["id"]) or {}
            text = plain(a.get("text"))
            document_id = a.get("document_id") if q.get("allow_upload") else None
            if document_id:
                doc = _owned_document(
                    user, document_id, {Purpose.SUPPORTING, Purpose.MESSAGE_ATTACHMENT, Purpose.CV}
                )
                document_id = str(doc.pk)
            if not text and not document_id:
                errors[q["id"]] = ["Please answer this question."]
            stored.append({"id": q["id"], "text": text, "document_id": document_id})
        if errors:
            raise DomainError("validation_error", "Please answer every question.", details=errors)
        req.answers = stored
        req.status = ClarificationStatus.ANSWERED
        req.answered_at = now()
        req.save(update_fields=["answers", "status", "answered_at", "updated_at"])
        if app.status == Status.NEEDS_INFORMATION:
            transition(app, Status.PROCESSING, actor=user, reason_code="clarification_answered")
        audit.record(
            actor=user,
            action="clarification.answered",
            target=req,
            organisation=app.organisation_id,
            after={"application_id": str(app.pk)},
        )
        outbox.emit(
            "clarification.answered",
            req,
            {"clarification_id": str(req.pk), "application_id": str(app.pk)},
            dedupe_key=f"clarification.answered:{req.pk}",
        )
        for staff in staff_recipients(app, req.requested_by):
            notifications.notify(
                staff,
                "clarification_answered",
                _staff_context(app),
                dedupe_key=f"clarification_answered:{req.pk}:{staff.pk}",
                organisation=app.organisation_id,
            )
    return req


def _staff_context(app: Application) -> dict[str, Any]:
    return {
        "candidate_name": _candidate_name(app),
        "job_title": app.job.title,
        "reference": app.reference,
        "application_url": f"{_site()}/hr/applications/{app.pk}",
    }


def cancel_clarification(
    membership: Membership, actor: Any, application_id: Any, clarification_id: Any
) -> ClarificationRequest:
    app = _visible_application(membership, application_id)
    with transaction.atomic():
        req = (
            ClarificationRequest.objects.for_org(app.organisation_id)
            .select_for_update()
            .filter(pk=clarification_id, application=app)
            .first()
        )
        if req is None:
            raise NotFoundError()
        if req.status not in (ClarificationStatus.OPEN, ClarificationStatus.EXPIRED):
            raise ConflictError("conflict.clarification_closed", "This request is already closed.")
        req.status = ClarificationStatus.CANCELLED
        req.save(update_fields=["status", "updated_at"])
        app.refresh_from_db()
        if app.status == Status.NEEDS_INFORMATION:
            transition(app, Status.UNDER_REVIEW, actor=actor, reason_code="clarification_cancelled")
        audit.record(
            actor=actor,
            action="clarification.cancelled",
            target=req,
            organisation=app.organisation_id,
        )
    return req


def process_due(moment: datetime | None = None) -> dict[str, int]:
    """Beat task body: remind candidates a day before the due date and expire overdue requests
    (EC-NOT-07: status ``expired``, the recruiter decides, the candidate can still message)."""
    moment = moment or now()
    reminded = expired = 0
    open_requests = ClarificationRequest.objects.unscoped().filter(status=ClarificationStatus.OPEN)
    for req in open_requests.filter(due_at__lte=moment).select_related(
        "application__job", "application__organisation", "requested_by"
    ):
        with transaction.atomic():
            updated = (
                ClarificationRequest.objects.unscoped()
                .filter(pk=req.pk, status=ClarificationStatus.OPEN)
                .update(status=ClarificationStatus.EXPIRED)
            )
            if not updated:
                continue
            app = req.application
            for staff in staff_recipients(app, req.requested_by):
                notifications.notify(
                    staff,
                    "clarification_expired",
                    _staff_context(app),
                    dedupe_key=f"clarification_expired:{req.pk}:{staff.pk}",
                    organisation=app.organisation_id,
                )
            expired += 1
    for req in open_requests.filter(
        due_at__gt=moment, due_at__lte=moment + REMIND_BEFORE, reminded_at__isnull=True
    ).select_related(
        "application__job", "application__organisation", "application__candidate_user"
    ):
        with transaction.atomic():
            app = req.application
            notifications.notify(
                app.candidate_user,
                "clarification_reminder",
                {
                    "organisation_name": app.organisation.name,
                    "job_title": app.job.title,
                    "due_date": req.due_at.strftime("%d %B %Y"),
                    "clarification_url": _clarification_url(app),
                    "application_id": app.pk,
                },
                dedupe_key=f"clarification_reminder:{req.pk}",
                organisation=app.organisation_id,
            )
            ClarificationRequest.objects.unscoped().filter(pk=req.pk).update(reminded_at=moment)
            reminded += 1
    return {"reminded": reminded, "expired": expired}


def resume_review(application_id: Any) -> bool:
    """Until the screening engine (Phases 06-07) re-evaluates answered clarifications, an
    answered application goes straight back to human review instead of waiting in processing."""
    app = Application.objects.unscoped().filter(pk=application_id).first()
    if app is None or app.status != Status.PROCESSING:
        return False
    transition(app, Status.UNDER_REVIEW, actor_type="system", reason_code="clarification_answered")
    return True


# ------------------------------------------------------------------------------ messages
def _thread(app: Application, create: bool) -> MessageThread | None:
    thread = MessageThread.objects.for_org(app.organisation_id).filter(application=app).first()
    if thread is None and create:
        try:
            with transaction.atomic():
                thread = MessageThread.objects.create(
                    organisation_id=app.organisation_id,
                    application=app,
                    subject=f"{app.job.title} ({app.reference})"[:200],
                )
        except IntegrityError:
            thread = MessageThread.objects.for_org(app.organisation_id).get(application=app)
    return thread


def _messages(app: Application, reader_role: str) -> list[Message]:
    thread = _thread(app, create=False)
    if thread is None:
        return []
    qs = Message.objects.for_org(app.organisation_id).filter(thread=thread)
    qs.exclude(sender_role=reader_role).filter(read_at__isnull=True).update(read_at=now())
    return list(qs.select_related("sender_user").order_by("created_at"))


def _post(
    app: Application, sender: Any, role: str, body: str, attachment_ids: list[Any]
) -> Message:
    text = plain(body)
    if not text:
        raise DomainError(
            "validation_error", "Write a message first.", details={"body": ["Required."]}
        )
    if len(attachment_ids) > MAX_ATTACHMENTS:
        raise DomainError(
            "validation_error",
            f"Attach at most {MAX_ATTACHMENTS} files.",
            details={"attachment_ids": [f"At most {MAX_ATTACHMENTS}."]},
        )
    docs = [_owned_document(sender, d, {Purpose.MESSAGE_ATTACHMENT}) for d in attachment_ids]
    with transaction.atomic():
        thread = _thread(app, create=True)
        if thread is None:  # pragma: no cover - create=True always returns one
            raise RuntimeError("message thread could not be created")
        message = Message.objects.create(
            organisation_id=app.organisation_id,
            thread=thread,
            sender_user=sender,
            sender_role=role,
            body=text,
            attachment_document_ids=[d.pk for d in docs],
        )
        audit.record(
            actor=sender,
            action="message.sent",
            target=message,
            organisation=app.organisation_id,
            after={"application_id": str(app.pk), "attachments": len(docs)},  # never the body
        )
        if role == SenderRole.CANDIDATE:
            recipients = staff_recipients(app)
            sender_name = _candidate_name(app)
            url = f"{_site()}/hr/applications/{app.pk}#messages"
        else:
            recipients = [app.candidate_user]
            sender_name = app.organisation.name
            url = f"{_site()}/candidate/applications/{app.pk}#messages"
        for user in recipients:
            notifications.notify(
                user,
                "new_message",
                {
                    "sender_name": sender_name,
                    "job_title": app.job.title,
                    "message_url": url,
                    "application_id": app.pk,
                },
                dedupe_key=f"new_message:{message.pk}:{user.pk}",
                organisation=app.organisation_id,
            )
    return message


def candidate_messages(user: Any, application_id: Any) -> list[Message]:
    return _messages(get_own(user, application_id), SenderRole.CANDIDATE)


def candidate_post(user: Any, application_id: Any, body: str, attachment_ids: list[Any]) -> Message:
    app = get_own(user, application_id)
    if app.status in PRIVATE_STATUSES:
        raise ConflictError(
            "conflict.not_submitted", "You can message the employer after you submit."
        )
    return _post(app, user, SenderRole.CANDIDATE, body, attachment_ids)


def staff_messages(membership: Membership, application_id: Any) -> list[Message]:
    return _messages(_visible_application(membership, application_id), SenderRole.STAFF)


def staff_post(
    membership: Membership, actor: Any, application_id: Any, body: str, attachment_ids: list[Any]
) -> Message:
    app = _visible_application(membership, application_id)
    if app.status == Status.WITHDRAWN:
        raise ConflictError(
            "conflict.application_withdrawn", "This candidate has withdrawn their application."
        )
    return _post(app, actor, SenderRole.STAFF, body, attachment_ids)


def participant_can_access_document(user: Any, document: Any) -> bool:
    """Registered with ``apps.documents``: the other side of a conversation or clarification may
    open a file attached to it - the candidate, or staff who can see the application."""
    if not getattr(user, "is_authenticated", False):
        return False
    app_ids = set(
        Message.objects.unscoped()
        .filter(attachment_document_ids__contains=[document.pk])
        .values_list("thread__application_id", flat=True)
    )
    for req in ClarificationRequest.objects.unscoped().filter(
        status=ClarificationStatus.ANSWERED, application__candidate_user_id=document.owner_user_id
    ):
        if any(a.get("document_id") == str(document.pk) for a in req.answers):
            app_ids.add(req.application_id)
    for app in Application.objects.unscoped().filter(pk__in=app_ids):
        if app.candidate_user_id == user.pk:
            return True
        membership = active_membership(user, app.organisation_id)
        if membership and applications_visible_to(membership).filter(pk=app.pk).exists():
            return True
    return False


# ----------------------------------------------------------------------- candidate actions
ACTIVE_FOR_CANDIDATE = (
    Status.SUBMITTED,
    Status.PROCESSING,
    Status.PROCESSING_ERROR,
    Status.NEEDS_INFORMATION,
    Status.UNDER_REVIEW,
    Status.ON_HOLD,
    Status.SHORTLISTED,
    Status.INTERVIEW,
    Status.OFFER,
)


def candidate_actions(user: Any) -> list[dict[str, Any]]:
    """What the candidate should do next (P05-T09): answer open clarifications, re-upload files
    that could not be accepted, read new messages from employers. Newest/most urgent first."""
    from apps.applications.models import ApplicationDocument

    items: list[dict[str, Any]] = []
    apps = {
        a.pk: a
        for a in Application.objects.unscoped()
        .filter(candidate_user=user, status__in=ACTIVE_FOR_CANDIDATE)
        .select_related("job", "organisation")
    }
    if not apps:
        return items

    def base(app: Application) -> dict[str, Any]:
        return {
            "application_id": str(app.pk),
            "job_title": app.job.title,
            "organisation_name": app.organisation.name,
        }

    for req in (
        ClarificationRequest.objects.unscoped()
        .filter(application_id__in=apps, status=ClarificationStatus.OPEN)
        .order_by("due_at")
    ):
        items.append(
            {"kind": "clarification", "due_at": req.due_at, **base(apps[req.application_id])}
        )
    for link in (
        ApplicationDocument.objects.unscoped()
        .filter(application_id__in=apps, document__scan_status__in=BAD_SCANS)
        .select_related("document")
    ):
        items.append(
            {
                "kind": "reupload",
                "document_name": link.document.original_filename,
                **base(apps[link.application_id]),
            }
        )
    unread: dict[Any, int] = {}
    for app_id in (
        Message.objects.unscoped()
        .filter(thread__application_id__in=apps, sender_role=SenderRole.STAFF, read_at__isnull=True)
        .values_list("thread__application_id", flat=True)
    ):
        unread[app_id] = unread.get(app_id, 0) + 1
    for app_id, count in unread.items():
        items.append({"kind": "message", "count": count, **base(apps[app_id])})
    return items
