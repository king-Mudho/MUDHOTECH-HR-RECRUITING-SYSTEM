"""Scoring (P07-T05, docs/05 §10).

* criterion score s_i in {0, 25, 50, 75, 100}; ``missing`` is not assessable (never 0);
* category score = weighted mean of the category's **assessable** criteria;
* total S = sum W_c * score_c over categories with an assessable criterion, re-normalised by the
  assessable weight; **coverage** = assessable weight / total weight;
* essentials are tracked separately; confidence is high / medium / low.

Questions linked to a criterion feed that criterion; unlinked scored questions form the
``answers`` category. When CV and answers disagree the criterion becomes ``conflicting`` (score
kept from the CV, never lowered) and a clarification is suggested.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from pydantic import Field

from ai_engine.contracts import (
    Contract,
    CriterionResult,
    CriterionSpec,
    EvidenceStatus,
    Flag,
)
from ai_engine.matching.answers import AnswerResult
from ai_engine.matching.conflicts import Conflict

ANSWERS = "answers"
PROCESSING_FLAGS = frozenset(
    {
        Flag.LOW_OCR_CONFIDENCE,
        Flag.LANGUAGE_UNSUPPORTED,
        Flag.POSSIBLY_NOT_CV,
        Flag.INJECTION_SUSPECTED,
        Flag.OCR_UNAVAILABLE,
        Flag.GARBLED_TEXT,
    }
)


class CategorySpec(Contract):
    key: str
    label: str = ""
    weight: float = Field(ge=0)


class CategoryScore(Contract):
    key: str
    label: str = ""
    weight: float
    score: float | None = None  # 0-100, None = nothing assessable in this category
    criteria: int = 0
    assessable: int = 0

    @property
    def points(self) -> float | None:
        """Contribution out of ``weight`` (e.g. 30 of 35)."""
        return None if self.score is None else round(self.score * self.weight / 100, 2)


class Essentials(Contract):
    met: tuple[str, ...] = ()  # score >= 75
    partial: tuple[str, ...] = ()  # score 50
    not_evidenced: tuple[str, ...] = ()  # weak evidence only (<= 25)
    unknown: tuple[str, ...] = ()  # missing / needs verification / conflicting


class Scores(Contract):
    total: float | None
    coverage: float = Field(ge=0, le=1)
    categories: tuple[CategoryScore, ...]
    essentials: Essentials
    confidence: str  # high | medium | low


def combine(
    spec: CriterionSpec,
    cv: CriterionResult,
    answers: Sequence[AnswerResult],
    conflicts: Sequence[Conflict],
) -> CriterionResult:
    """One result per criterion from CV evidence + linked answers (docs/05 §8.2)."""
    mine = [c for c in conflicts if c.criterion_id == spec.id]
    answer_refs = tuple(ref for a in answers for ref in a.evidence)
    if mine:
        return cv.model_copy(
            update={
                "status": EvidenceStatus.CONFLICTING,
                "evidence": (*cv.evidence, *answer_refs, *(e for c in mine for e in c.evidence))[
                    :10
                ]
                or answer_refs,
                "flags": (*cv.flags, "conflict"),
                "reason": ",".join(c.kind for c in mine),
                "confidence": min(cv.confidence, 0.4),
            }
        )
    if cv.assessable and cv.status != EvidenceStatus.NEEDS_VERIFICATION:
        return cv
    scored = [a for a in answers if a.assessable]
    if scored:
        best = max(scored, key=lambda a: a.score or 0)
        if not cv.assessable or (best.score or 0) > (cv.score or 0):
            return CriterionResult(
                criterion_id=spec.id,
                status=EvidenceStatus.CANDIDATE_REPORTED,
                score=best.score,
                method=f"answer:{best.mode}",
                confidence=min(best.confidence, 0.7),
                evidence=best.evidence + cv.evidence,
                reason=best.reason,
            )
    return cv


def category_scores(
    categories: Sequence[CategorySpec],
    specs: Sequence[CriterionSpec],
    results: dict[str, CriterionResult],
    unlinked_answers: Iterable[AnswerResult],
) -> tuple[CategoryScore, ...]:
    answers = [a for a in unlinked_answers if a.assessable]
    out = []
    for category in categories:
        members = [s for s in specs if s.category == category.key]
        weighted = [
            (s.weight, results[s.id].score)
            for s in members
            if s.id in results and results[s.id].score is not None
        ]
        if category.key == ANSWERS:
            weighted += [(1.0, a.score) for a in answers]
        total_weight = sum(w for w, _ in weighted)
        score = (
            round(sum(w * (sc or 0) for w, sc in weighted) / total_weight, 2)
            if total_weight > 0
            else None
        )
        out.append(
            CategoryScore(
                key=category.key,
                label=category.label,
                weight=category.weight,
                score=score,
                criteria=len(members) + (len(answers) if category.key == ANSWERS else 0),
                assessable=len(weighted),
            )
        )
    return tuple(out)


def essentials(specs: Sequence[CriterionSpec], results: dict[str, CriterionResult]) -> Essentials:
    met, partial, weak, unknown = [], [], [], []
    for spec in specs:
        if not spec.essential:
            continue
        result = results.get(spec.id)
        if (
            result is None
            or not result.assessable
            or result.status in (EvidenceStatus.NEEDS_VERIFICATION, EvidenceStatus.CONFLICTING)
        ):
            unknown.append(spec.id)
        elif (result.score or 0) >= 75:
            met.append(spec.id)
        elif result.score == 50:
            partial.append(spec.id)
        else:
            weak.append(spec.id)
    return Essentials(
        met=tuple(met), partial=tuple(partial), not_evidenced=tuple(weak), unknown=tuple(unknown)
    )


def confidence(
    coverage: float, conflicts: int, quality: float | None, flags: Iterable[Flag]
) -> str:
    if coverage < 0.5 or set(flags) & PROCESSING_FLAGS:
        return "low"
    if coverage >= 0.8 and conflicts == 0 and (quality is None or quality >= 0.7):
        return "high"
    return "medium"


def score(
    categories: Sequence[CategorySpec],
    specs: Sequence[CriterionSpec],
    results: dict[str, CriterionResult],
    unlinked_answers: Sequence[AnswerResult],
    *,
    conflicts: int = 0,
    quality: float | None = None,
    flags: Iterable[Flag] = (),
) -> Scores:
    cats = category_scores(categories, specs, results, unlinked_answers)
    total_weight = sum(c.weight for c in categories) or 1.0
    assessed = [c for c in cats if c.score is not None]
    assessed_weight = sum(c.weight for c in assessed)
    total = (
        round(sum(c.weight * (c.score or 0) for c in assessed) / assessed_weight, 2)
        if assessed_weight
        else None
    )
    coverage = round(assessed_weight / total_weight, 4)
    return Scores(
        total=total,
        coverage=min(coverage, 1.0),
        categories=cats,
        essentials=essentials(specs, results),
        confidence=confidence(coverage, conflicts, quality, flags),
    )
