"""Builds the pure ``EvaluationInput`` for an application from the database (docs/05 §1).

Inputs are: the job version's criteria + approved rubric + questionnaire, the candidate's
answers, and the evaluable claims of the application's latest extraction runs (with candidate
corrections and human verifications applied). Claim order is stable, so
``CandidateEvidence.claims[i]`` maps back to ``claim_rows[i]`` for evidence links.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from typing import Any

from django.db.models import Max

from ai_engine import ENGINE_VERSION
from ai_engine.contracts import (
    CandidateEvidence,
    CriterionSpec,
    CriterionType,
    ExtractedClaim,
    ExtractionMethod,
    Flag,
    Importance,
)
from ai_engine.evaluation.engine import EvaluationInput
from ai_engine.evaluation.scoring import CategorySpec
from ai_engine.matching.answers import AnswerInput, QuestionSpec
from ai_engine.matching.config import DEFAULT_CONFIG
from ai_engine.matching.skills_match import SkillGraph
from apps.applications.models import Application
from apps.core.time import now
from apps.jobs.models import JobCriterion, JobVersion
from apps.questionnaires.models import QuestionResponse
from apps.resumes.models import ClaimCorrection, ExtractionRun, RunStatus
from apps.resumes.models import ExtractedClaim as ClaimRow
from apps.taxonomy.models import QualificationLevel, SkillRelation

_cache: dict[tuple[Any, ...], Any] = {}
_lock = threading.Lock()
_TAGS = re.compile(r"<[^>]+>")


def skill_graph() -> SkillGraph:
    marker = SkillRelation.objects.aggregate(m=Max("updated_at"))["m"]
    key = ("graph", marker, SkillRelation.objects.count())
    with _lock:
        if key in _cache:
            cached: SkillGraph = _cache[key]
            return cached
    graph = SkillGraph.build(
        (str(a), str(b), rel)
        for a, b, rel in SkillRelation.objects.values_list(
            "from_skill_id", "to_skill_id", "relation"
        )
    )
    with _lock:
        _cache[key] = graph
    return graph


def level_ranks() -> dict[str, int]:
    return dict(QualificationLevel.objects.values_list("code", "rank"))


def plain(html: str) -> str:
    return " ".join(_TAGS.sub(" ", html or "").split())


@dataclass
class Built:
    input: EvaluationInput
    claim_rows: list[ClaimRow]  # index-aligned with input.evidence.claims
    criteria: dict[str, JobCriterion]  # spec id -> row
    responses: dict[str, QuestionResponse]  # question key -> row
    job_version: JobVersion
    runs: list[ExtractionRun]


def criterion_spec(c: JobCriterion) -> CriterionSpec:
    level = c.qualification_level
    return CriterionSpec(
        id=str(c.pk),
        type=CriterionType(c.type),
        importance=Importance(c.importance),
        title=c.title,
        description=c.description,
        category=c.rubric_category,
        weight=float(c.weight_within_category or 1) or 1.0,
        skill_id=str(c.skill_id) if c.skill_id else None,
        qualification_level=level.code if level else None,
        qualification_rank=level.rank if level else None,
        min_months=c.min_months,
        equivalents=tuple(str(e) for e in (c.equivalents or []) if str(e).strip()),
    )


def _apply_corrections(row: ClaimRow, claim: ExtractedClaim) -> ExtractedClaim | None:
    """Human verification > candidate correction > extracted. A rejected claim is dropped."""
    from .models import HumanVerification

    verdict = (
        HumanVerification.objects.for_org(row.organisation_id)
        .filter(claim=row)
        .order_by("-at")
        .first()
    )
    if verdict is not None:
        if verdict.decision == HumanVerification.Decision.REJECTED:
            return None
        data = claim.data.model_dump(mode="json")
        if verdict.decision == HumanVerification.Decision.CORRECTED and verdict.corrected_payload:
            data |= json.loads(verdict.corrected_payload)
        return claim.model_copy(
            update={
                "data": type(claim.data).model_validate(data),
                "confidence": 1.0,
                "method": ExtractionMethod.HUMAN,
            }
        )
    correction = (
        ClaimCorrection.objects.for_org(row.organisation_id)
        .filter(claim=row)
        .order_by("-created_at")
        .first()
    )
    if correction is None:
        return claim
    payload = json.loads(correction.payload)
    if payload.get("remove"):
        return None
    fields = {k: v for k, v in (payload.get("fields") or {}).items() if v}
    data = claim.data.model_dump(mode="json")
    mapping = {"name": "raw" if data.get("type") == "skill" else "name"}
    for key, value in fields.items():
        target = mapping.get(key, key)
        if target in data and isinstance(data[target], str | int | float | type(None)):
            data[target] = value
    try:
        return claim.model_copy(update={"data": type(claim.data).model_validate(data)})
    except ValueError:
        return claim  # an unusable correction never breaks evaluation; HR sees it on the panel


def build(app: Application, version: JobVersion | None = None) -> Built:
    from apps.resumes.services import objected

    version = version or app.job_version
    criteria = list(
        JobCriterion.objects.for_org(app.organisation_id)
        .filter(job_version=version)
        .select_related("qualification_level")
        .order_by("order")
    )
    specs = [criterion_spec(c) for c in criteria]
    rubric = getattr(version, "rubric", None)
    categories = tuple(
        CategorySpec(key=str(c["key"]), label=str(c.get("label", "")), weight=float(c["weight"]))
        for c in (rubric.categories if rubric else [])
        if float(c.get("weight") or 0) > 0
    ) or (CategorySpec(key="technical", weight=100),)

    runs = list(
        ExtractionRun.objects.for_org(app.organisation_id)
        .filter(
            application=app,
            engine_version=ENGINE_VERSION,
            status__in=[RunStatus.SUCCEEDED, RunStatus.PARTIAL],
        )
        .order_by("created_at")
    )
    rows: list[ClaimRow] = []
    claims: list[ExtractedClaim] = []
    flags: set[Flag] = set()
    for run in runs:
        flags |= {Flag(f) for f in run.flags if f in Flag._value2member_map_}
        for row in (
            ClaimRow.objects.for_org(app.organisation_id).filter(run=run).order_by("ordinal")
        ):
            if not row.evaluable:
                continue
            claim = _apply_corrections(row, ExtractedClaim.model_validate_json(row.payload))
            if claim is None or not claim.evaluable:
                continue
            rows.append(row)
            claims.append(claim)
    evidence = CandidateEvidence(
        application_id=str(app.pk),
        document_ids=tuple(str(r.document_id) for r in runs),
        claims=tuple(claims),
        flags=frozenset(flags),
    )

    questions: list[QuestionSpec] = []
    answers: list[AnswerInput] = []
    responses: dict[str, QuestionResponse] = {}
    questionnaire = getattr(version, "questionnaire", None)
    if questionnaire is not None:
        for q in questionnaire.questions.all().prefetch_related("options").order_by("order"):
            questions.append(
                QuestionSpec(
                    key=q.key,
                    type=q.type,
                    prompt=q.prompt,
                    required=q.required,
                    scoring=dict(q.scoring or {}),
                    options=tuple(
                        (o.value, float(o.points) if o.points is not None else None)
                        for o in q.options.all()
                    ),
                    is_knockout=q.is_knockout,
                    knockout_expected=(q.config or {}).get("knockout_expected"),
                    criterion_id=str(q.criterion_id) if q.criterion_id else None,
                )
            )
        for r in (
            QuestionResponse.objects.for_org(app.organisation_id)
            .filter(application=app)
            .select_related("question")
        ):
            responses[r.question.key] = r
            answers.append(AnswerInput(key=r.question.key, value=r.value, response_id=str(r.pk)))

    quality = min((r.quality_score for r in runs if r.quality_score is not None), default=None)
    today = now().date()
    data = EvaluationInput(
        application_id=str(app.pk),
        evidence=evidence,
        criteria=tuple(specs),
        categories=categories,
        questions=tuple(questions),
        answers=tuple(answers),
        job_title=app.job.title,
        job_responsibilities=plain(version.responsibilities_html),
        today=(today.year, today.month),
        level_ranks=level_ranks(),
        objected=objected(app),
        quality=quality,
        config=DEFAULT_CONFIG,
    )
    return Built(
        input=data,
        claim_rows=rows,
        criteria={str(c.pk): c for c in criteria},
        responses=responses,
        job_version=version,
        runs=runs,
    )
