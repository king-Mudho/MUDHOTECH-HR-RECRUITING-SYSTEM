"""Staff-side reads of applications (P04-T15; the full review workspace arrives in Phase 08).

Visibility follows vacancy visibility: org_admin/hr_manager see every application of the
organisation, recruiters and hiring managers only those of vacancies they are assigned to. Drafts
and abandoned drafts are the candidate's private work and are never shown to staff.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Q, QuerySet

from apps.audit import services as audit
from apps.core.exceptions import NotFoundError
from apps.jobs.assignments import jobs_visible_to
from apps.organisations import rbac
from apps.organisations.models import Membership
from apps.organisations.selectors import active_membership
from apps.questionnaires.models import QuestionResponse

from .models import Application, ApplicationDocument, Status

PRIVATE_STATUSES = (Status.DRAFT, Status.ABANDONED)


def applications_visible_to(membership: Membership) -> QuerySet[Application]:
    if not rbac.can(membership.role, "applications.view"):
        return Application.objects.for_org(membership.organisation_id).none()
    return (
        Application.objects.for_org(membership.organisation_id)
        .exclude(status__in=PRIVATE_STATUSES)
        .filter(job__in=jobs_visible_to(membership).values("pk"))
    )


def job_applications(
    membership: Membership, job_id: Any, params: dict[str, Any] | None = None
) -> QuerySet[Application]:
    if not jobs_visible_to(membership).filter(pk=job_id).exists():
        raise NotFoundError()
    qs = applications_visible_to(membership).filter(job_id=job_id)
    params = params or {}
    statuses = [s for s in str(params.get("status") or "").split(",") if s]
    if statuses:
        qs = qs.filter(status__in=statuses)
    search = str(params.get("search") or "").strip()[:100]
    if search:
        snap = "candidate_profile_snapshot__"
        qs = qs.filter(
            Q(reference__icontains=search)
            | Q(**{f"{snap}first_name__icontains": search})
            | Q(**{f"{snap}last_name__icontains": search})
            | Q(**{f"{snap}email__icontains": search})
        )
    ordering = params.get("ordering") or "-submitted_at"
    if ordering not in {"submitted_at", "-submitted_at"}:
        ordering = "-submitted_at"
    return qs.order_by(ordering, "-created_at")


def application_detail(user: Any, membership: Membership, application_id: Any) -> dict[str, Any]:
    app = (
        applications_visible_to(membership)
        .select_related("job", "job_version")
        .filter(pk=application_id)
        .first()
    )
    if app is None:
        raise NotFoundError()
    audit.log_access(user=user, target=app, organisation=app.organisation_id, action="view")
    documents = [
        {
            "id": a.document_id,
            "role": a.role,
            "required_doc_key": a.required_doc_key,
            "filename": a.document.original_filename,
            "scan_status": a.document.scan_status,
            "size_bytes": a.document.size_bytes,
            "available": a.document.is_available,
        }
        for a in app.documents.select_related("document").order_by("created_at")
    ]
    responses = app.responses.select_related("question").order_by(
        "question__order", "question__key"
    )
    answers = [
        {
            "key": r.question.key,
            "prompt": r.question.prompt,
            "type": r.question.type,
            "value": r.value,
            "document_id": r.document_id,
        }
        for r in responses
    ]
    timeline = [
        {
            "from_status": e.from_status,
            "to_status": e.to_status,
            "actor_type": e.actor_type,
            "reason_code": e.reason_code,
            "reason_text": e.reason_text,
            "at": e.at,
        }
        for e in app.status_events.order_by("at")
    ]
    return {"application": app, "documents": documents, "answers": answers, "timeline": timeline}


def staff_can_access_document(user: Any, document: Any) -> bool:
    """Registered with ``apps.documents``: staff may open a candidate's file when it is linked to
    a submitted application they can see (as an attachment or a file-upload answer)."""
    if not getattr(user, "is_authenticated", False):
        return False
    app_ids = set(
        ApplicationDocument.objects.unscoped()
        .filter(document_id=document.pk)
        .values_list("application_id", flat=True)
    ) | set(
        QuestionResponse.objects.unscoped()
        .filter(document_id=document.pk)
        .values_list("application_id", flat=True)
    )
    if not app_ids:
        return False
    apps = (
        Application.objects.unscoped()
        .filter(pk__in=app_ids)
        .exclude(status__in=PRIVATE_STATUSES)
        .values_list("pk", "organisation_id")
    )
    for app_id, org_id in apps:
        membership = active_membership(user, org_id)
        if membership and applications_visible_to(membership).filter(pk=app_id).exists():
            return True
    return False
