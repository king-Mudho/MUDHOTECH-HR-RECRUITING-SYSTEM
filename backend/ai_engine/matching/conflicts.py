"""CV versus answers (P07-T04, docs/05 §8.2, EC-AI-03).

A conflict is raised only when both sides say something and they disagree clearly - a missing CV
item never contradicts an answer (principle 3). Conflicts never lower a score by themselves: the
criterion becomes ``conflicting`` and a clarification is suggested to HR.

Checked: years of experience (answer vs relevant CV months), a skill's stated years (answer vs
the CV's "N years of X"), and qualification level (answer naming a level vs the CV's best level).
"""

from __future__ import annotations

from collections.abc import Mapping

from ai_engine.contracts import (
    CandidateEvidence,
    Contract,
    CriterionResult,
    CriterionSpec,
    CriterionType,
    EducationData,
    EvidenceRef,
    SkillData,
)
from ai_engine.matching.answers import AnswerInput, QuestionSpec, _norm, _number
from ai_engine.matching.rules import ref

YEARS_TOLERANCE = 1.0  # one year either way is normal rounding
YEARS_RATIO = 1.5


class Conflict(Contract):
    criterion_id: str
    question_key: str
    kind: str  # experience_years | skill_years | qualification_level
    cv_value: str
    answer_value: str
    evidence: tuple[EvidenceRef, ...] = ()


def _years_disagree(cv_years: float, answer_years: float) -> bool:
    if abs(cv_years - answer_years) <= YEARS_TOLERANCE:
        return False
    low, high = sorted((cv_years, answer_years))
    return high >= max(low, 0.5) * YEARS_RATIO


def find_conflicts(
    specs: list[CriterionSpec],
    questions: list[QuestionSpec],
    answers: list[AnswerInput],
    evidence: CandidateEvidence,
    cv_results: Mapping[str, CriterionResult],
    level_ranks: Mapping[str, int],
) -> list[Conflict]:
    by_key = {a.key: a for a in answers}
    by_id = {s.id: s for s in specs}
    out: list[Conflict] = []
    for question in questions:
        answer = by_key.get(question.key)
        spec = by_id.get(question.criterion_id or "")
        if answer is None or spec is None or answer.value in (None, "", []):
            continue
        cv = cv_results.get(spec.id)
        if spec.type == CriterionType.EXPERIENCE:
            years = _number(answer.value)
            months = _months(cv)
            if years is not None and months is not None and _years_disagree(months / 12, years):
                out.append(
                    Conflict(
                        criterion_id=spec.id,
                        question_key=question.key,
                        kind="experience_years",
                        cv_value=f"{months / 12:.1f} years",
                        answer_value=f"{years:g} years",
                        evidence=cv.evidence if cv else (),
                    )
                )
        elif spec.type == CriterionType.SKILL:
            years = _number(answer.value)
            stated = _skill_years(spec, evidence)
            if years is not None and stated is not None and _years_disagree(stated[0], years):
                out.append(
                    Conflict(
                        criterion_id=spec.id,
                        question_key=question.key,
                        kind="skill_years",
                        cv_value=f"{stated[0]:g} years",
                        answer_value=f"{years:g} years",
                        evidence=(stated[1],),
                    )
                )
        elif spec.type == CriterionType.QUALIFICATION:
            answered = level_ranks.get(str(answer.value)) or level_ranks.get(
                _norm(answer.value).upper()
            )
            best = _best_level(evidence, level_ranks)
            if answered is not None and best is not None and answered > best[0]:
                out.append(
                    Conflict(
                        criterion_id=spec.id,
                        question_key=question.key,
                        kind="qualification_level",
                        cv_value=best[2],
                        answer_value=str(answer.value),
                        evidence=(best[1],),
                    )
                )
    return out


def _months(result: CriterionResult | None) -> int | None:
    if result is None or not result.reason.startswith("months="):
        return None
    return int(result.reason.split("=", 1)[1].split("/", 1)[0])


def _skill_years(
    spec: CriterionSpec, evidence: CandidateEvidence
) -> tuple[float, EvidenceRef] | None:
    for claim in evidence.of_type("skill"):
        data = claim.data
        if (
            isinstance(data, SkillData)
            and data.years
            and spec.skill_id
            and data.skill_id == spec.skill_id
        ):
            return data.years, ref(evidence, claim)
    return None


def _best_level(
    evidence: CandidateEvidence, level_ranks: Mapping[str, int]
) -> tuple[int, EvidenceRef, str] | None:
    best: tuple[int, EvidenceRef, str] | None = None
    for claim in evidence.of_type("education"):
        data = claim.data
        if isinstance(data, EducationData) and data.level and data.level in level_ranks:
            rank = level_ranks[data.level]
            if best is None or rank > best[0]:
                best = (rank, ref(evidence, claim), data.level)
    return best
