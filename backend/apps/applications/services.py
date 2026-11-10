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


# ------------------------------------------------------------------------------ draft editing
CONTACT_FIELDS = ("first_name", "last_name", "preferred_name", "phone", "city")
# job-level required document key -> application document role
REQUIRED_DOC_ROLES = {
    "cv": "cv",
    "cover_letter": "cover_letter",
    "certificates": "certificate",
    "transcripts": "transcript",
    "portfolio": "portfolio",
}


def own_applications(user: Any) -> Any:
    # Candidates read their own applications across organisations: owner-filtered by design.
    return Application.objects.unscoped().filter(candidate_user=user)


def get_own(user: Any, application_id: Any, *, lock: bool = False) -> Application:
    from apps.core.exceptions import NotFoundError

    qs = own_applications(user).select_related("job", "job_version", "organisation")
    if lock:
        qs = qs.select_for_update(of=("self",))
    app = qs.filter(pk=application_id).first()
    if app is None:
        raise NotFoundError()
    return app


def _require_draft(app: Application) -> None:
    if app.status != Status.DRAFT:
        raise DomainError(
            "conflict.not_draft",
            "This application has been submitted and can no longer be edited.",
            status_code=409,
        )


def _check_lock(app: Application, lock_version: int | None) -> None:
    from apps.core.exceptions import StaleVersionError

    if lock_version is not None and int(lock_version) != app.lock_version:
        raise StaleVersionError(details={"current_lock_version": app.lock_version})


@transaction.atomic
def update_draft(
    user: Any, application_id: Any, data: dict[str, Any], *, lock_version: int | None
) -> Application:
    app = get_own(user, application_id, lock=True)
    _require_draft(app)
    _check_lock(app, lock_version)
    if "contact" in data:
        contact = dict(app.contact)
        for k in CONTACT_FIELDS:
            if k in data["contact"]:
                contact[k] = str(data["contact"][k] or "").strip()[:150]
        if contact.get("phone"):
            from apps.candidates.services import normalise_phone

            contact["phone"] = normalise_phone(contact["phone"])
        app.contact = contact
    if "last_step" in data:
        app.last_step = max(1, min(6, int(data["last_step"])))
    app.lock_version += 1
    app.save(update_fields=["contact", "last_step", "lock_version", "updated_at"])
    return app


@transaction.atomic
def set_documents(user: Any, application_id: Any, items: list[dict[str, Any]]) -> Application:
    """Replace the attached documents. Pending scans are fine; rejected/infected are not."""
    from apps.documents.models import Document, ScanStatus
    from apps.documents.services import APPLICATION_TOTAL_BYTES, MB

    from .models import ApplicationDocument, DocumentRole

    app = get_own(user, application_id, lock=True)
    _require_draft(app)
    errors: dict[str, dict[str, list[str]]] = {}
    ids = [str(i.get("document_id")) for i in items]
    docs = {
        str(d.pk): d
        for d in Document.objects.filter(pk__in=ids, owner_user=user, deleted_at__isnull=True)
    }
    for i, item in enumerate(items):
        doc = docs.get(str(item.get("document_id")))
        if doc is None:
            errors[str(i)] = {"document_id": ["File not found."]}
        elif doc.scan_status in (ScanStatus.INFECTED, ScanStatus.REJECTED, ScanStatus.ERROR):
            errors[str(i)] = {"document_id": ["This file was not accepted. Upload another one."]}
        elif item.get("role") not in DocumentRole.values:
            errors[str(i)] = {"role": ["Unknown document role."]}
    if len(set(ids)) != len(ids):
        errors["non_field_errors"] = {"document_id": ["Each file can be attached once."]}
    if errors:
        raise DomainError("validation_error", "Check the attached files.", details=errors)
    total = sum(docs[d].size_bytes for d in set(ids))
    if total > APPLICATION_TOTAL_BYTES:
        raise DomainError(
            "payload_too_large",
            f"Attachments may total at most {APPLICATION_TOTAL_BYTES // MB} MB.",
            status_code=413,
        )
    ApplicationDocument.objects.for_org(app.organisation_id).filter(application=app).delete()
    for item in items:
        ApplicationDocument.objects.create(
            organisation_id=app.organisation_id,
            application=app,
            document=docs[str(item["document_id"])],
            role=item["role"],
            required_doc_key=str(item.get("required_doc_key") or "")[:40],
        )
    app.lock_version += 1
    app.save(update_fields=["lock_version", "updated_at"])
    return app


def question_defs(app: Application) -> list[dict[str, Any]]:
    """The application's frozen questions (its job version) as plain dicts, in order."""
    from apps.questionnaires.models import Question

    qs = (
        Question.objects.for_org(app.organisation_id)
        .filter(questionnaire__job_version_id=app.job_version_id)
        .order_by("order")
        .prefetch_related("options")
    )
    return [
        {
            "id": q.pk,
            "key": q.key,
            "type": q.type,
            "required": q.required,
            "config": q.config,
            "branching": q.branching,
            "options": [o.value for o in q.options.all()],
        }
        for q in qs
    ]


def current_answers(app: Application) -> dict[str, Any]:
    from apps.questionnaires.models import QuestionResponse

    return {
        r.question.key: r.value
        for r in QuestionResponse.objects.for_org(app.organisation_id)
        .filter(application=app)
        .select_related("question")
    }


@transaction.atomic
def upsert_answers(user: Any, application_id: Any, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Bulk upsert (partial allowed in draft). Answers to questions hidden by branching are
    discarded (also previously saved ones), so they are never stored or scored."""
    from apps.documents.models import Document
    from apps.questionnaires.models import QuestionResponse

    from . import answers as ans

    app = get_own(user, application_id, lock=True)
    _require_draft(app)
    defs = question_defs(app)
    by_key = {q["key"]: q for q in defs}
    merged = current_answers(app)
    errors: dict[str, list[str]] = {}
    for item in items:
        key = str(item.get("key", ""))
        q = by_key.get(key)
        if q is None:
            errors[key or "?"] = ["Unknown question."]
            continue
        value, err = ans.validate_answer(q, item.get("value"))
        if err:
            errors[key] = [err]
            continue
        if q["type"] == "file_upload" and value is not None:
            ok = Document.objects.filter(
                pk=value, owner_user=user, deleted_at__isnull=True
            ).exists()
            if not ok:
                errors[key] = ["File not found."]
                continue
        merged[key] = value
    if errors:
        raise DomainError("validation_error", "Check the highlighted answers.", details=errors)
    shown = set(ans.visible_keys(defs, merged))
    stamp = now()
    for key, q in by_key.items():
        value = merged.get(key) if key in shown else None
        if value is None:
            QuestionResponse.objects.for_org(app.organisation_id).filter(
                application=app, question_id=q["id"]
            ).delete()
            continue
        QuestionResponse.objects.for_org(app.organisation_id).update_or_create(
            application=app,
            question_id=q["id"],
            defaults={
                "organisation_id": app.organisation_id,
                "value": value,
                "document_id": value if q["type"] == "file_upload" else None,
                "answered_at": stamp,
            },
        )
    app.lock_version += 1
    app.save(update_fields=["lock_version", "updated_at"])
    return {k: v for k, v in merged.items() if k in shown}


def review(user: Any, application_id: Any) -> dict[str, Any]:
    """Pre-submit checklist: everything still missing, so the wizard can link to each step."""
    from apps.documents.models import ScanStatus

    from . import answers as ans
    from .models import ApplicationDocument

    app = get_own(user, application_id)
    defs = question_defs(app)
    given = current_answers(app)
    attached = list(
        ApplicationDocument.objects.for_org(app.organisation_id)
        .filter(application=app)
        .select_related("document")
    )
    missing: list[dict[str, str]] = []
    if user.email_verified_at is None:
        missing.append({"step": "contact", "code": "email_unverified", "key": ""})
    for key in app.job_version.required_documents or []:
        role = REQUIRED_DOC_ROLES.get(key)
        if not any(a.required_doc_key == key or (role and a.role == role) for a in attached):
            missing.append({"step": "documents", "code": "document_required", "key": key})
    for a in attached:
        if a.document.scan_status in (ScanStatus.INFECTED, ScanStatus.REJECTED):
            missing.append(
                {"step": "documents", "code": "document_rejected", "key": str(a.document_id)}
            )
    for key in ans.missing_required(defs, given):
        missing.append({"step": "questions", "code": "answer_required", "key": key})
    return {
        "application": app,
        "ready": not missing,
        "missing": missing,
        "visible_questions": ans.visible_keys(defs, given),
        "documents": attached,
        "answers": given,
    }


# ------------------------------------------------------------------------------------ submit
class SubmitBlockedError(DomainError):
    code = "submit_blocked"
    status_code = 422
    default_message = "Your application isn't complete yet."


def _submit_checks(app: Application, user: Any) -> None:
    from django.conf import settings

    org = Organisation.objects.get(pk=app.organisation_id)
    if org.is_read_only:  # EC-APP-19
        raise DomainError(
            "org_suspended",
            "This employer isn't accepting applications at the moment.",
            status_code=423,
        )
    job = Job.objects.unscoped().get(pk=app.job_id)
    if job.status == JobStatus.PAUSED:  # EC-JOB-08: drafts are kept, submit waits
        raise DomainError(
            "job_paused",
            "Applications for this vacancy are paused. Your draft is saved.",
            status_code=422,
        )
    if job.status != JobStatus.PUBLISHED:
        raise DomainError("job_not_accepting", "This vacancy is closed.", status_code=422)
    grace = int(getattr(settings, "APPLICATION_DEADLINE_GRACE_SECONDS", 0))
    from datetime import timedelta

    if job.closes_at is not None and now() > job.closes_at + timedelta(seconds=grace):
        # EC-APP-05: server time is authoritative; <= closes_at is accepted.
        raise DomainError(
            "deadline_passed", "The closing date for this vacancy has passed.", status_code=422
        )
    if app.status != Status.DRAFT:
        raise DomainError(
            "conflict.not_draft", "This application has already been submitted.", status_code=409
        )
    summary = review(user, app.pk)
    if summary["missing"]:
        unverified = any(m["code"] == "email_unverified" for m in summary["missing"])
        raise SubmitBlockedError(
            code="email_unverified" if unverified else "submit_blocked",
            message=(
                "Please verify your email address before submitting."  # EC-ACC-03
                if unverified
                else "Your application isn't complete yet."
            ),
            details={"missing": summary["missing"]},
        )


def submit(
    user: Any,
    application_id: Any,
    *,
    accept_privacy: bool,
    objects_to_automated_processing: bool = False,
    actor: Any = None,
) -> Application:
    """Submit exactly once (FR-M07-03). The request does no heavy work: screening starts from the
    ``application.submitted`` outbox event, so later failures never lose the application."""
    from apps.candidates.services import profile_snapshot
    from apps.core import outbox
    from apps.core.email import queue_email

    if not accept_privacy:
        raise DomainError(
            "validation_error",
            "Please confirm you have read the privacy notice.",
            details={"accept_privacy": ["Required."]},
        )
    with transaction.atomic():
        app = get_own(user, application_id, lock=True)
        _submit_checks(app, user)
        policy = duplicate_policy(app.organisation_id)
        previous = None
        if policy == DuplicatePolicy.ALLOW_RESUBMIT_REPLACE:
            previous = (
                Application.objects.for_org(app.organisation_id)
                .filter(job_id=app.job_id, candidate_user=user)
                .exclude(pk=app.pk)
                .exclude(status__in=[*INACTIVE_STATUSES, Status.DRAFT])
                .order_by("-submitted_at")
                .first()
            )
        app.candidate_profile_snapshot = profile_snapshot(user, app.contact)
        app.reference = next_reference(app.organisation)
        app.submitted_at = now()
        app.save(
            update_fields=["candidate_profile_snapshot", "reference", "submitted_at", "updated_at"]
        )
        if previous is not None:  # allow_resubmit_replace: the new one replaces the old one
            transition(
                previous, Status.WITHDRAWN, actor=user, reason="Replaced by a new application"
            )
            app.duplicate_of = previous
            app.save(update_fields=["duplicate_of"])
        app = transition(
            app,
            Status.SUBMITTED,
            actor=actor or user,
            reason="Assisted application" if actor is not None and actor != user else "",
            metadata={"objects_to_automated_processing": objects_to_automated_processing},
        )
        job = app.job
        outbox.emit(
            "application.submitted",
            app,
            {
                "application_id": str(app.pk),
                "job_id": str(app.job_id),
                "job_version_id": str(app.job_version_id),
                "reference": app.reference,
                "objects_to_automated_processing": objects_to_automated_processing,
            },
            dedupe_key=f"application.submitted:{app.pk}",
            organisation_id=app.organisation_id,
        )
        queue_email(
            user.email,
            f"Application received: {job.title} ({app.reference})",
            (
                f"Hello {app.candidate_profile_snapshot.get('first_name') or ''},\n\n"
                f"Thank you for applying for {job.title} at {app.organisation.name}.\n"
                f"Your reference number is {app.reference}.\n\n"
                "Every application is reviewed by people at the employer. You can follow its "
                "status, or withdraw it, from your applications page at any time.\n\n"
                "MUDHOTECH HR RECRUITING SYSTEM"
            ),
            dedupe_key=f"email.application_receipt:{app.pk}",
            organisation_id=app.organisation_id,
        )
    return app
