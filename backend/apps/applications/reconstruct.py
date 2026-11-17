"""Decision reconstruction bundle (P08-T11, FR-M22; EC-PRV-06).

Everything needed to explain how an application was assessed and decided, in one read:
the job version and rubric it was assessed against, every evaluation version with its engine,
thresholds and models, the evidence each criterion cited, every human decision with its reason
and actor, shortlist decisions (with the AI band at the time and overrides), claim verifications,
identity reveals, conflict declarations and the notifications sent (kinds and times - no message
content). Auditors see personal details redacted unless they revealed the identity with a reason
(EC-PRV-06); HR managers follow the blind-review setting.
"""

from __future__ import annotations

import json
from typing import Any

from apps.core.exceptions import NotFoundError
from apps.organisations import rbac
from apps.organisations.models import Membership, Role

from .blind import BlindView, alias, revealed_ids
from .models import (
    Application,
    ApplicationStatusEvent,
    ConflictDeclaration,
    IdentityReveal,
)

ACTION = "applications.reconstruct"


def application_for(membership: Membership, application_id: Any) -> Application:
    """Auditors read any application of their organisation; HR managers what they can see."""
    if membership.role == Role.AUDITOR:
        app = (
            Application.objects.for_org(membership.organisation_id)
            .exclude(status__in=["draft", "abandoned"])
            .filter(pk=application_id)
            .first()
        )
    else:
        from .hr import applications_visible_to

        app = applications_visible_to(membership).filter(pk=application_id).first()
    if app is None or not rbac.can(membership.role, ACTION):
        raise NotFoundError()
    return app


def _person(user: Any) -> str | None:
    return None if user is None else str(user.full_name or user.email)


def bundle(membership: Membership, application_id: Any) -> dict[str, Any]:
    from apps.jobs.models import JobCriterion, Rubric
    from apps.notifications.models import Notification
    from apps.screening.models import (
        CriterionResult,
        Evaluation,
        EvaluationEvidence,
        HumanVerification,
        ScreeningRun,
    )
    from apps.shortlisting.models import ShortlistEntry

    app = application_for(membership, application_id)
    org = app.organisation_id
    view = BlindView(membership.user, org, [app.pk])
    if membership.role == Role.AUDITOR:  # redacted by default whatever the blind setting
        view.enabled = True
        view.revealed = revealed_ids(membership.user, org, [app.pk])
    hidden = view.hidden(app.pk)
    version = app.job_version
    rubric = Rubric.objects.for_org(org).filter(job_version=version).first()
    criteria = JobCriterion.objects.for_org(org).filter(job_version=version).order_by("order")

    evaluations = []
    for ev in Evaluation.objects.for_org(org).filter(application=app).order_by("version"):
        run = (
            ScreeningRun.objects.for_org(org).filter(pk=ev.screening_run_id).first()
            if ev.screening_run_id
            else None
        )
        results = []
        for r in (
            CriterionResult.objects.for_org(org)
            .filter(evaluation=ev)
            .select_related("criterion")
            .order_by("criterion__order")
        ):
            refs = [
                {
                    "claim_id": e.claim_id,
                    "question_response_id": e.question_response_id,
                    "document_id": e.document_id,
                    "page": e.page,
                    "snippet": None if hidden else e.snippet,
                }
                for e in EvaluationEvidence.objects.for_org(org).filter(criterion_result=r)
            ]
            results.append(
                {
                    "criterion_id": r.criterion_id,
                    "title": r.criterion.title,
                    "score": float(r.score) if r.score is not None else None,
                    "evidence_status": r.evidence_status,
                    "match_method": r.match_method,
                    "confidence": r.confidence,
                    "evidence": refs,
                }
            )
        evaluations.append(
            {
                "version": ev.version,
                "status": ev.status,
                "trigger": ev.trigger,
                "reason": ev.reason,
                "created_at": ev.created_at,
                "band": ev.band,
                "band_reasons": ev.band_reasons,
                "total_score": float(ev.total_score) if ev.total_score is not None else None,
                "coverage": float(ev.coverage),
                "engine_version": ev.engine_version,
                "config_version": ev.config_version,
                "input_hash": ev.input_hash,
                "prompt_hash": ev.prompt_hash,
                "llm_used": ev.llm_used,
                "model_ids": run.model_ids if run else {},
                "taxonomy_version": run.taxonomy_version if run else "",
                "criteria": results,
                "explanation": [] if hidden else json.loads(ev.explanation or "[]"),
            }
        )

    events = [
        {
            "from_status": e.from_status,
            "to_status": e.to_status,
            "actor_type": e.actor_type,
            "actor": _person(e.actor),
            "reason_code": e.reason_code,
            "reason_text": e.reason_text,
            "at": e.at,
        }
        for e in ApplicationStatusEvent.objects.for_org(org)
        .filter(application=app)
        .select_related("actor")
        .order_by("at")
    ]
    shortlist = [
        {
            "shortlist_id": e.shortlist_id,
            "shortlist_status": e.shortlist.status,
            "decision": e.decision,
            "reason_code": e.reason_code,
            "reason_text": e.reason_text,
            "ai_band_at_decision": e.ai_band_at_decision,
            "score_at_decision": (
                float(e.score_at_decision) if e.score_at_decision is not None else None
            ),
            "override": e.override,
            "decided_by": _person(e.decided_by),
            "decided_at": e.decided_at,
            "approved_by": [str(u) for u in e.shortlist.approved_by],
            "approved_at": e.shortlist.approved_at,
            "applied_at": e.applied_at,
            "apply_note": e.apply_note,
        }
        for e in ShortlistEntry.objects.for_org(org)
        .filter(application=app)
        .select_related("shortlist", "decided_by")
        .order_by("created_at")
    ]
    verifications = [
        {
            "claim_id": v.claim_id,
            "decision": v.decision,
            "verifier": _person(v.verifier),
            "at": v.at,
        }
        for v in HumanVerification.objects.for_org(org)
        .filter(application=app)
        .select_related("verifier")
    ]
    access = [
        {"kind": "identity_revealed", "by": _person(r.user), "reason": r.reason, "at": r.at}
        for r in IdentityReveal.objects.for_org(org).filter(application=app).select_related("user")
    ] + [
        {
            "kind": "conflict_declared",
            "by": _person(c.user),
            "reason": c.reason,
            "at": c.declared_at,
        }
        for c in ConflictDeclaration.objects.for_org(org)
        .filter(application=app)
        .select_related("user")
    ]
    notifications = [
        {
            "key": n.key,
            "channel": n.channel,
            "status": n.status,
            "scheduled_for": n.scheduled_for,
            "sent_at": n.sent_at,
        }
        for n in Notification.objects.filter(
            organisation_id=org, payload__application_id=str(app.pk)
        ).order_by("created_at")
    ]
    snapshot = app.candidate_profile_snapshot or {}
    return {
        "generated_for": _person(membership.user),
        "identity_hidden": hidden,
        "application": {
            "id": app.pk,
            "reference": app.reference,
            "candidate": alias(app.pk)
            if hidden
            else " ".join(p for p in (snapshot.get("first_name"), snapshot.get("last_name")) if p),
            "status": app.status,
            "submitted_at": app.submitted_at,
            "objects_to_automated_processing": app.objects_to_automated_processing,
        },
        "job": {
            "id": app.job_id,
            "title": app.job.title,
            "version_id": version.pk,
            "version": version.number,
        },
        "rubric": {
            "version": rubric.version if rubric else None,
            "status": rubric.status if rubric else "",
            "categories": rubric.categories if rubric else [],
            "criteria": [
                {
                    "id": c.pk,
                    "title": c.title,
                    "type": c.type,
                    "importance": c.importance,
                    "category": c.rubric_category,
                }
                for c in criteria
            ],
        },
        "evaluations": evaluations,
        "status_events": events,
        "shortlist_decisions": shortlist,
        "verifications": verifications,
        "access": sorted(access, key=lambda a: a["at"]),
        "notifications": notifications,
    }
