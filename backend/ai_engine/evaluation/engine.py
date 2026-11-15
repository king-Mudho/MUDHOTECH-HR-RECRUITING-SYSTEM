"""One evaluation of one application against one rubric (docs/05 §1 steps 8-10).

Pure and deterministic: the same ``EvaluationInput`` always yields the same ``EvaluationResult``
(the ``input_hash`` identifies it; re-evaluation creates a new version - principle 5).
Explanations are added by ``ai_engine.explanations`` (P07-T06).
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import Field

from ai_engine import ENGINE_VERSION
from ai_engine.contracts import (
    CandidateEvidence,
    Contract,
    CriterionResult,
    CriterionSpec,
    CriterionType,
    EmploymentKind,
    EvidenceStatus,
    ExperienceData,
    ProjectData,
    SummaryData,
)
from ai_engine.evaluation.bands import BandPolicy, band_for
from ai_engine.evaluation.scoring import CategoryScore, CategorySpec, Essentials, combine, score
from ai_engine.matching.answers import AnswerInput, AnswerResult, QuestionSpec, score_answers
from ai_engine.matching.config import DEFAULT_CONFIG, EngineConfig
from ai_engine.matching.conflicts import Conflict, find_conflicts
from ai_engine.matching.experience_match import JobContext, keywords, match_experience
from ai_engine.matching.rules import Context, evaluate_rule, missing, ref
from ai_engine.matching.semantic import EmbeddingService
from ai_engine.matching.skills_match import SkillGraph, match_skill
from ai_engine.versioning import input_hash


class EvaluationInput(Contract):
    application_id: str
    evidence: CandidateEvidence
    criteria: tuple[CriterionSpec, ...]
    categories: tuple[CategorySpec, ...]
    questions: tuple[QuestionSpec, ...] = ()
    answers: tuple[AnswerInput, ...] = ()
    job_title: str = ""
    job_responsibilities: str = ""
    today: tuple[int, int]
    level_ranks: dict[str, int] = Field(default_factory=dict)
    include_kinds: tuple[EmploymentKind, ...] = ()
    objected: bool = False
    quality: float | None = None
    config: EngineConfig = DEFAULT_CONFIG
    policy: BandPolicy = BandPolicy()

    def hash(self) -> str:
        return input_hash({"engine": ENGINE_VERSION, **self.model_dump(mode="json")})


class EvaluationResult(Contract):
    application_id: str
    engine_version: str = ENGINE_VERSION
    config_version: str
    input_hash: str
    total: float | None
    coverage: float
    confidence: str
    band: str
    band_reasons: tuple[str, ...]
    categories: tuple[CategoryScore, ...]
    criteria: tuple[CriterionResult, ...]
    answers: tuple[AnswerResult, ...]
    conflicts: tuple[Conflict, ...]
    essentials: Essentials
    eligibility_unmet: bool
    flags: tuple[str, ...]


def _competency(spec: CriterionSpec, evidence: CandidateEvidence) -> CriterionResult:
    """Lexical overlap of the competency description with duties, projects and the profile.
    Low confidence by design: competencies usually need the questionnaire or an interview."""
    wanted = keywords(f"{spec.title} {spec.description} {' '.join(spec.equivalents)}")
    if not wanted:
        return missing(spec)
    hits = []
    for claim in evidence.claims:
        data = claim.data
        if isinstance(data, ExperienceData):
            text = " ".join(data.responsibilities)
        elif isinstance(data, ProjectData):
            text = f"{data.title} {data.description}"
        elif isinstance(data, SummaryData):
            text = data.text
        else:
            continue
        overlap = len(keywords(text) & wanted)
        if overlap:
            hits.append((overlap, claim))
    if not hits:
        return missing(spec)
    hits.sort(key=lambda h: h[0], reverse=True)
    best = hits[0][0] / len(wanted)
    return CriterionResult(
        criterion_id=spec.id,
        status=EvidenceStatus.INFERRED,
        score=50 if best >= 0.5 else 25,
        method="keywords",
        confidence=0.35,
        evidence=tuple(ref(evidence, c) for _, c in hits[:3]),
        reason=f"overlap={best:.2f}",
    )


def _eligibility(spec: CriterionSpec, answers: list[AnswerResult]) -> CriterionResult:
    """From knock-out answers only - never inferred from the CV (docs/05 §8.1)."""
    linked = [
        a for a in answers if a.criterion_id == spec.id and a.status != EvidenceStatus.MISSING
    ]
    if not linked:
        return missing(spec)
    unmet = any(a.eligibility_unmet for a in linked)
    return CriterionResult(
        criterion_id=spec.id,
        status=EvidenceStatus.CANDIDATE_REPORTED,
        score=0 if unmet else 100,
        method="answer:knockout",
        confidence=0.9,
        evidence=tuple(e for a in linked for e in a.evidence),
        flags=("eligibility_unmet",) if unmet else (),
        reason="eligibility_unmet" if unmet else "eligible",
    )


def evaluate(
    data: EvaluationInput,
    *,
    graph: SkillGraph | None = None,
    semantic: EmbeddingService | None = None,
) -> EvaluationResult:
    evidence = data.evidence
    ctx = Context(today=data.today, level_ranks=data.level_ranks)
    job = JobContext(data.job_title, data.job_responsibilities)
    answers = score_answers(list(data.questions), list(data.answers))
    cv_results: dict[str, CriterionResult] = {}
    for spec in data.criteria:
        if spec.type == CriterionType.SKILL:
            result = match_skill(spec, evidence, graph=graph, semantic=semantic, config=data.config)
        elif spec.type == CriterionType.EXPERIENCE:
            result = match_experience(
                spec,
                evidence,
                ctx,
                job,
                semantic=semantic,
                config=data.config,
                include_kinds=data.include_kinds,
            )
        elif spec.type == CriterionType.COMPETENCY:
            result = _competency(spec, evidence)
        elif spec.type == CriterionType.ELIGIBILITY:
            result = _eligibility(spec, answers)
        else:
            result = evaluate_rule(spec, evidence, ctx) or missing(spec)
        cv_results[spec.id] = result
    conflicts = find_conflicts(
        list(data.criteria),
        list(data.questions),
        list(data.answers),
        evidence,
        cv_results,
        data.level_ranks,
    )
    by_criterion: Mapping[str, list[AnswerResult]] = {
        spec.id: [a for a in answers if a.criterion_id == spec.id] for spec in data.criteria
    }
    final = {
        spec.id: (
            cv_results[spec.id]
            if spec.type == CriterionType.ELIGIBILITY
            else combine(spec, cv_results[spec.id], by_criterion[spec.id], conflicts)
        )
        for spec in data.criteria
    }
    known = {s.id for s in data.criteria}
    unlinked = [a for a in answers if not a.criterion_id or a.criterion_id not in known]
    scores = score(
        data.categories,
        data.criteria,
        final,
        unlinked,
        conflicts=len(conflicts),
        quality=data.quality,
        flags=evidence.flags,
    )
    eligibility_unmet = any(a.eligibility_unmet for a in answers)
    band, reasons = band_for(
        scores,
        policy=data.policy,
        objected=data.objected,
        eligibility_unmet=eligibility_unmet,
        conflicts=len(conflicts),
        flags=evidence.flags,
    )
    return EvaluationResult(
        application_id=data.application_id,
        config_version=data.config.version,
        input_hash=data.hash(),
        total=scores.total,
        coverage=scores.coverage,
        confidence=scores.confidence,
        band=band,
        band_reasons=reasons,
        categories=scores.categories,
        criteria=tuple(final[s.id] for s in data.criteria),
        answers=tuple(answers),
        conflicts=tuple(conflicts),
        essentials=scores.essentials,
        eligibility_unmet=eligibility_unmet,
        flags=tuple(sorted(f.value for f in evidence.flags)),
    )
