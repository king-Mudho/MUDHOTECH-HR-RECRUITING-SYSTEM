"""Screening services (P07-T09).

``evaluate_application`` is idempotent per evaluation input: when the latest evaluation already
has the same ``input_hash`` (same evidence, rubric, answers, engine and config) nothing new is
written. Otherwise version n+1 is stored, the previous one is marked ``superseded`` (kept), the
application gets the denormalised band/score/coverage and - when it was waiting in
``processing`` - moves to ``under_review`` (a system transition; no consequential status is ever
set here). ``screening.completed`` is emitted through the outbox.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction

from ai_engine.evaluation.engine import EvaluationResult, evaluate
from ai_engine.explanations.clarifications import suggest
from ai_engine.explanations.grounding import explain
from ai_engine.explanations.templates import Explanation
from apps.applications.models import Application, Status
from apps.applications.services import transition
from apps.audit import services as audit
from apps.core import outbox
from apps.core.exceptions import DomainError

from . import engine, killswitch
from .models import CriterionResult, Evaluation, EvaluationEvidence, ScreeningRun, Trigger

MANUAL_BAND = "manual_review_requested"
logger = logging.getLogger(__name__)
EVALUABLE_STATUSES = frozenset(
    {Status.PROCESSING, Status.UNDER_REVIEW, Status.NEEDS_INFORMATION, Status.ON_HOLD}
)


def _semantic() -> Any:
    if not getattr(settings, "SEMANTIC_SKILL_MATCHING", True):
        return None
    try:
        from apps.taxonomy.embeddings import service

        svc = service()
        svc.encoder.encode(["warm-up"])
        return svc
    except (ImportError, OSError, RuntimeError):
        return None


def llm_service(app: Application) -> Any:
    """Enabled only when the platform flag AND the organisation's policy allow it (D-06)."""
    from ai_engine.llm.service import LLMService
    from apps.core.flags import is_enabled

    provider_name = getattr(settings, "LLM_PROVIDER", "none")
    policy = getattr(app.organisation, "policy", None)
    enabled = (
        provider_name != "none"
        and is_enabled("llm", app.organisation)
        and bool(getattr(policy, "llm_enabled", False))
        and killswitch.ai_allowed(app.organisation)
    )
    if not enabled:
        return LLMService()
    from django.core.cache import cache

    if provider_name == "anthropic":
        from ai_engine.llm.anthropic_adapter import DEFAULT_MODEL, AnthropicProvider

        provider: Any = AnthropicProvider(
            getattr(settings, "LLM_API_KEY", None) or None,
            model=getattr(settings, "LLM_MODEL", "") or DEFAULT_MODEL,
        )
    elif provider_name == "openai":
        from ai_engine.llm.openai_adapter import OpenAIProvider

        provider = OpenAIProvider(
            getattr(settings, "LLM_API_KEY", None) or None, model=settings.LLM_MODEL
        )
    else:
        return LLMService()
    return LLMService(provider, enabled=True, cache=cache)


def _decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(round(value, 2)))


def _explanation_json(explanation: Explanation, built: engine.Built) -> str:
    out = []
    for sentence in explanation.sentences:
        cites = []
        for ref in sentence.citations:
            row = (
                built.claim_rows[ref.claim_index]
                if ref.claim_index is not None and ref.claim_index < len(built.claim_rows)
                else None
            )
            response = built.responses.get(ref.question_key or "")
            cites.append(
                {
                    "claim_id": str(row.pk) if row else None,
                    "question_response_id": str(response.pk) if response else None,
                    "page": ref.source.page,
                    "snippet": ref.source.snippet,
                }
            )
        out.append(
            {
                "kind": sentence.kind,
                "criterion_id": sentence.criterion_id,
                "text": sentence.text,
                "citations": cites,
            }
        )
    return json.dumps(out)


@transaction.atomic
def _store(
    app: Application,
    built: engine.Built,
    result: EvaluationResult,
    explanation: Explanation,
    summary: Explanation | None,
    prompt_hash: str,
    *,
    trigger: str,
    run: ScreeningRun | None,
    reason: str,
) -> Evaluation:
    previous = (
        Evaluation.objects.for_org(app.organisation_id)
        .select_for_update()
        .filter(application=app)
        .order_by("-version")
        .first()
    )
    if previous is not None:
        Evaluation.objects.for_org(app.organisation_id).filter(
            application=app, status__in=[Evaluation.Status.SUCCEEDED, Evaluation.Status.PARTIAL]
        ).update(status=Evaluation.Status.SUPERSEDED)
    clarifications = [c.model_dump() for c in suggest(result, built.input.criteria)]
    evaluation = Evaluation.objects.create(
        organisation_id=app.organisation_id,
        application=app,
        screening_run=run,
        job_version=built.job_version,
        version=(previous.version + 1) if previous else 1,
        trigger=trigger,
        status=Evaluation.Status.SUCCEEDED,
        total_score=_decimal(result.total),
        coverage=_decimal(result.coverage) or Decimal("0"),
        confidence=result.confidence,
        band=result.band,
        band_reasons=list(result.band_reasons),
        flags=list(result.flags),
        categories=[{**c.model_dump(), "points": c.points} for c in result.categories],
        essentials=result.essentials.model_dump(mode="json"),
        conflicts=[
            {"criterion_id": c.criterion_id, "kind": c.kind, "question_key": c.question_key}
            for c in result.conflicts
        ],
        explanation=_explanation_json(explanation, built),
        summary=_explanation_json(summary, built) if summary else "",
        clarification_suggestions=clarifications,
        input_hash=result.input_hash,
        engine_version=result.engine_version,
        config_version=result.config_version,
        prompt_hash=prompt_hash if summary else "",
        llm_used=summary is not None,
        grounding_dropped=explanation.dropped,
        reason=reason[:2000],
    )
    for spec, cr in zip(built.input.criteria, result.criteria, strict=True):
        row = CriterionResult.objects.create(
            organisation_id=app.organisation_id,
            evaluation=evaluation,
            criterion=built.criteria[spec.id],
            category=spec.category,
            score=_decimal(cr.score),
            assessable=cr.assessable,
            evidence_status=cr.status.value,
            match_method=cr.method[:30],
            confidence=cr.confidence,
            rationale=cr.reason[:120],
            flags=list(cr.flags),
        )
        evidence_rows = []
        for ref in cr.evidence:
            claim_row = (
                built.claim_rows[ref.claim_index]
                if ref.claim_index is not None and ref.claim_index < len(built.claim_rows)
                else None
            )
            response = built.responses.get(ref.question_key or "")
            evidence_rows.append(
                EvaluationEvidence(
                    organisation_id=app.organisation_id,
                    criterion_result=row,
                    claim=claim_row,
                    question_response=response,
                    document_id=claim_row.run.document_id if claim_row else None,
                    page=ref.source.page,
                    snippet=ref.source.snippet,
                )
            )
        EvaluationEvidence.objects.bulk_create(evidence_rows)

    locked = Application.objects.for_org(app.organisation_id).select_for_update().get(pk=app.pk)
    locked.current_evaluation_id = evaluation.pk
    locked.ai_band = result.band
    if result.band == "manual_review_requested":  # EC-AI-12: no AI numbers anywhere
        locked.score = locked.coverage = None
        locked.essentials_met = locked.essentials_unknown = locked.essentials_not_evidenced = None
    else:
        locked.score = evaluation.total_score
        locked.coverage = evaluation.coverage
        ess = result.essentials
        # explicit evidence counts as met (bands rule); weak = not evidenced; missing = unknown
        locked.essentials_met = len(ess.met) + len(ess.partial)
        locked.essentials_unknown = len(ess.unknown)
        locked.essentials_not_evidenced = len(ess.not_evidenced)
    locked.save(
        update_fields=[
            "current_evaluation_id",
            "ai_band",
            "score",
            "coverage",
            "essentials_met",
            "essentials_unknown",
            "essentials_not_evidenced",
            "updated_at",
        ]
    )
    if locked.status == Status.PROCESSING:
        transition(locked, Status.UNDER_REVIEW, actor_type="system", reason_code="screened")
    outbox.emit(
        "screening.completed",
        locked,
        {
            "application_id": str(app.pk),
            "evaluation_id": str(evaluation.pk),
            "version": evaluation.version,
            "band": result.band,
        },
        dedupe_key=f"screening.completed:{evaluation.pk}",
        organisation_id=app.organisation_id,
    )
    audit.record(
        action="screening.evaluated",
        target=evaluation,
        organisation=app.organisation_id,
        actor_type="system",
        after={
            "version": evaluation.version,
            "band": result.band,
            "coverage": float(evaluation.coverage),
            "trigger": trigger,
            "llm_used": evaluation.llm_used,
        },
    )
    from .quality import capture_evaluation

    capture_evaluation(evaluation, sentences=len(explanation.sentences), job_id=app.job_id)
    return evaluation


def evaluate_application(
    application_id: Any,
    *,
    trigger: str = Trigger.AUTO,
    run: ScreeningRun | None = None,
    reason: str = "",
    force: bool = False,
    job_version_id: Any = None,
) -> Evaluation | None:
    """Evaluate one application; None when skipped (withdrawn, nothing changed)."""
    app = (
        Application.objects.unscoped()
        .select_related("job", "job_version", "organisation")
        .filter(pk=application_id)
        .first()
    )
    if app is None:
        return None
    if app.status == Status.PROCESSING_ERROR and trigger in (Trigger.MANUAL, Trigger.REEVALUATION):
        with transaction.atomic():  # HR retried a failed application (scope=failed)
            app = transition(app, Status.PROCESSING, actor_type="system", reason_code="retry")
    if app.status not in EVALUABLE_STATUSES:
        return None
    if not killswitch.ai_allowed(app.organisation):
        route_to_manual_review(app.pk)  # P09-T11: AI is switched off, a human reviews
        return None
    version = None
    if job_version_id is not None:
        from apps.jobs.models import JobVersion

        version = JobVersion.objects.for_org(app.organisation_id).get(pk=job_version_id)
        force = True  # HR chose to re-evaluate against the new version, with a reason
    built = engine.build(app, version)
    if not built.input.criteria:
        raise DomainError(
            "conflict.no_criteria", "This vacancy has no screening criteria.", status_code=409
        )
    latest = (
        Evaluation.objects.for_org(app.organisation_id)
        .filter(application=app)
        .order_by("-version")
        .first()
    )
    input_hash = built.input.hash()
    if latest is not None and latest.input_hash == input_hash and not force:
        return None  # idempotent: same input, same answer (EC-AI-10/11)
    result = evaluate(built.input, graph=engine.skill_graph(), semantic=_semantic())
    explanation = explain(result, built.input.criteria, built.input.evidence)
    summary, prompt_hash = None, ""
    llm = llm_service(app)
    if llm.enabled:
        from ai_engine.llm.service import load_prompt

        names = [app.candidate_user.first_name, app.candidate_user.last_name]
        summary = llm.summarise(
            result,
            explanation,
            built.input.criteria,
            built.input.evidence,
            names=[n for n in names if n],
        )
        prompt_hash = load_prompt("summary_v1")[1]
    return _store(
        app,
        built,
        result,
        explanation,
        summary,
        prompt_hash,
        trigger=trigger,
        run=run,
        reason=reason,
    )


def route_to_manual_review(application_id: Any) -> None:
    """AI kill-switch: no evaluation; the application waits for a human with no AI output."""
    with transaction.atomic():
        app = Application.objects.unscoped().select_for_update().filter(pk=application_id).first()
        if app is None or app.status not in EVALUABLE_STATUSES:
            return
        already = app.ai_band == MANUAL_BAND and app.score is None
        app.ai_band = MANUAL_BAND
        app.score = app.coverage = None
        app.essentials_met = app.essentials_unknown = app.essentials_not_evidenced = None
        app.save(
            update_fields=[
                "ai_band",
                "score",
                "coverage",
                "essentials_met",
                "essentials_unknown",
                "essentials_not_evidenced",
                "updated_at",
            ]
        )
        moved = app.status == Status.PROCESSING
        if moved:
            transition(app, Status.UNDER_REVIEW, actor_type="system", reason_code="ai_disabled")
        if moved or not already:
            audit.record(
                action="screening.ai_disabled",
                target=app,
                organisation=app.organisation_id,
                actor_type="system",
                after={"band": MANUAL_BAND},
            )


def mark_failed(application_id: Any, error: str) -> None:
    """Final failure: the application waits in ``processing_error`` for HR (never lost)."""
    with transaction.atomic():
        app = Application.objects.unscoped().select_for_update().filter(pk=application_id).first()
        if app is not None and app.status == Status.PROCESSING:
            transition(app, Status.PROCESSING_ERROR, actor_type="system", reason_code="screening")
            audit.record(
                action="screening.failed",
                target=app,
                organisation=app.organisation_id,
                actor_type="system",
                after={"error": error[:200]},
            )
