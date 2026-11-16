"""Read side of screening for HR (P07-T10/T11/T13). Everything is labelled AI-assisted and
scoped to the applications the member can see."""

from __future__ import annotations

import json
from typing import Any

from apps.applications.models import Application
from apps.core.exceptions import NotFoundError

from .models import CriterionResult, Evaluation, EvaluationEvidence

MANUAL = "manual_review_requested"


def visible_application(membership: Any, application_id: Any) -> Application:
    from apps.applications.ats import _visible

    return _visible(membership, application_id)


def evaluation_detail(evaluation: Evaluation) -> dict[str, Any]:
    base = {
        "id": evaluation.pk,
        "version": evaluation.version,
        "status": evaluation.status,
        "trigger": evaluation.trigger,
        "band": evaluation.band,
        "band_reasons": evaluation.band_reasons,
        "created_at": evaluation.created_at,
        "engine_version": evaluation.engine_version,
        "config_version": evaluation.config_version,
        "llm_used": evaluation.llm_used,
        "ai_notice": "AI-assisted suggestion — requires human review",
    }
    if evaluation.band == MANUAL:  # EC-AI-12: the candidate asked for a person only
        return {
            **base,
            "total_score": None,
            "coverage": None,
            "confidence": None,
            "flags": [],
            "categories": [],
            "essentials": {},
            "conflicts": [],
            "criteria": [],
            "explanation": [],
            "summary": [],
            "clarification_suggestions": [],
        }
    rows = list(
        CriterionResult.objects.for_org(evaluation.organisation_id)
        .filter(evaluation=evaluation)
        .select_related("criterion")
        .order_by("criterion__order")
    )
    evidence: dict[Any, list[dict[str, Any]]] = {}
    for ev in EvaluationEvidence.objects.for_org(evaluation.organisation_id).filter(
        criterion_result__in=rows
    ):
        evidence.setdefault(ev.criterion_result_id, []).append(
            {
                "claim_id": ev.claim_id,
                "question_response_id": ev.question_response_id,
                "document_id": ev.document_id,
                "page": ev.page,
                "snippet": ev.snippet,
            }
        )
    return {
        **base,
        "total_score": float(evaluation.total_score)
        if evaluation.total_score is not None
        else None,
        "coverage": float(evaluation.coverage),
        "confidence": evaluation.confidence,
        "flags": list(evaluation.flags),
        "categories": evaluation.categories,
        "essentials": evaluation.essentials,
        "conflicts": evaluation.conflicts,
        "criteria": [
            {
                "id": r.pk,
                "criterion_id": r.criterion_id,
                "title": r.criterion.title,
                "type": r.criterion.type,
                "importance": r.criterion.importance,
                "category": r.category,
                "score": float(r.score) if r.score is not None else None,
                "assessable": r.assessable,
                "evidence_status": r.evidence_status,
                "match_method": r.match_method,
                "confidence": round(r.confidence, 3),
                "rationale": r.rationale,
                "flags": r.flags,
                "evidence": evidence.get(r.pk, []),
            }
            for r in rows
        ],
        "explanation": json.loads(evaluation.explanation or "[]"),
        "summary": json.loads(evaluation.summary or "[]"),
        "clarification_suggestions": evaluation.clarification_suggestions,
    }


def current_evaluation(membership: Any, application_id: Any) -> dict[str, Any] | None:
    app = visible_application(membership, application_id)
    evaluation = (
        Evaluation.objects.for_org(app.organisation_id)
        .filter(application=app)
        .order_by("-version")
        .first()
    )
    return evaluation_detail(evaluation) if evaluation else None


def versions(membership: Any, application_id: Any) -> list[Evaluation]:
    app = visible_application(membership, application_id)
    return list(
        Evaluation.objects.for_org(app.organisation_id).filter(application=app).order_by("-version")
    )


def evaluation_version(membership: Any, application_id: Any, version: int) -> dict[str, Any]:
    app = visible_application(membership, application_id)
    evaluation = (
        Evaluation.objects.for_org(app.organisation_id)
        .filter(application=app, version=version)
        .first()
    )
    if evaluation is None:
        raise NotFoundError()
    return evaluation_detail(evaluation)
