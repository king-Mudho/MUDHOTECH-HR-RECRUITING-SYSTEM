"""Read models for interviews (P12-T03; the API in P12-T06 serialises these).

``panel_view`` is what a panelist gets for an interview they sit on: the interview, the
application's reference, vacancy and documents, and - only when the organisation allows it - the AI
band and coverage. ADR-019: AI output is hidden from panelists by default
(``OrganisationPolicy.hide_ai_from_panelists``) so the interview is assessed on its own and not
anchored on the screening suggestion.
"""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet

from apps.audit import services as audit
from apps.core.exceptions import NotFoundError
from apps.organisations import rbac
from apps.organisations.models import Membership, OrganisationPolicy

from .models import Interview, InterviewPanelist


def interviews_for_panelist(membership: Membership) -> QuerySet[Interview]:
    """Panelists see only the interviews they sit on (docs/01 M16 AC)."""
    return Interview.objects.for_org(membership.organisation_id).filter(
        pk__in=InterviewPanelist.objects.for_org(membership.organisation_id)
        .filter(membership=membership)
        .values("interview_id")
    )


def ai_visible_to_panel(organisation_id: Any) -> bool:
    policy = OrganisationPolicy.objects.filter(organisation_id=organisation_id).first()
    return not (policy.hide_ai_from_panelists if policy else True)


def panel_view(user: Any, membership: Membership, interview_id: Any) -> dict[str, Any]:
    iv = (
        interviews_for_panelist(membership)
        .select_related("application__job", "scorecard_template")
        .filter(pk=interview_id)
        .first()
    )
    if iv is None and rbac.can(membership.role, "interviews.view_all"):
        iv = (
            Interview.objects.for_org(membership.organisation_id)
            .select_related("application__job", "scorecard_template")
            .filter(pk=interview_id)
            .first()
        )
    if iv is None:
        raise NotFoundError()
    app = iv.application
    audit.log_access(user=user, target=app, organisation=app.organisation_id, action="view")
    documents = [
        {
            "id": a.document_id,
            "role": a.role,
            "filename": a.document.original_filename,
            "available": a.document.is_available,
        }
        for a in app.documents.select_related("document").order_by("created_at")
    ]
    ai = None
    if ai_visible_to_panel(app.organisation_id):
        ai = {
            "band": app.ai_band,
            "coverage": app.coverage,
            "essentials_met": app.essentials_met,
            "essentials_unknown": app.essentials_unknown,
            "label": "AI-assisted suggestion - requires human review",
        }
    return {
        "interview": iv,
        "application": {
            "id": app.pk,
            "reference": app.reference,
            "job_title": app.job.title,
            "status": app.status,
        },
        "documents": documents,
        "scorecard_criteria": iv.scorecard_template.criteria if iv.scorecard_template else [],
        "ai": ai,
    }
