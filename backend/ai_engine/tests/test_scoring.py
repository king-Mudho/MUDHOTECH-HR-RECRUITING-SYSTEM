"""Scoring, coverage, essentials, confidence and bands (P07-T05, docs/05 §10)."""

from __future__ import annotations

import random

from ai_engine.contracts import (
    CandidateEvidence,
    ClaimSource,
    CriterionResult,
    CriterionSpec,
    CriterionType,
    EvidenceRef,
    EvidenceStatus,
    Flag,
    Importance,
)
from ai_engine.evaluation.bands import (
    ELIGIBILITY,
    LOWER,
    MANUAL,
    RECOMMENDED,
    REVIEW,
    BandPolicy,
    band_for,
)
from ai_engine.evaluation.engine import EvaluationInput, evaluate
from ai_engine.evaluation.scoring import CategorySpec, combine, score
from ai_engine.matching.answers import AnswerInput, AnswerResult, QuestionSpec
from ai_engine.matching.conflicts import Conflict

CATS = (
    CategorySpec(key="technical", weight=35),
    CategorySpec(key="experience", weight=25),
    CategorySpec(key="competency", weight=20),
    CategorySpec(key="qualification", weight=10),
    CategorySpec(key="answers", weight=10),
)
REF = EvidenceRef(claim_index=0, source=ClaimSource(snippet="cv line", document_id="d", page=1))


def crit(cid: str, category: str, essential: bool = True, weight: float = 1.0) -> CriterionSpec:
    return CriterionSpec(
        id=cid,
        type=CriterionType.SKILL,
        title=cid,
        category=category,
        weight=weight,
        importance=Importance.ESSENTIAL if essential else Importance.PREFERRED,
    )


def res(
    cid: str, value: int | None, status: EvidenceStatus = EvidenceStatus.EXPLICIT
) -> CriterionResult:
    if value is None:
        return CriterionResult(criterion_id=cid, status=EvidenceStatus.MISSING)
    return CriterionResult(criterion_id=cid, status=status, score=value, evidence=(REF,))


def answer(value: int | None, key: str = "q") -> AnswerResult:
    return AnswerResult(
        key=key,
        status=EvidenceStatus.CANDIDATE_REPORTED if value is not None else EvidenceStatus.MISSING,
        score=value,
        evidence=(REF,) if value is not None else (),
    )


def test_blueprint_example_84() -> None:
    """Exit criterion: technical 30/35, experience 20/25, competencies 17/20, qualifications 8/10,
    answers 9/10 -> 84/100, coverage 1.0, recommended (docs/05 §10), from constructed evidence."""
    specs = [
        # technical: (4*100 + 2*75 + 1*50) / 7 = 85.71 -> 30/35
        crit("t1", "technical", weight=4),
        crit("t2", "technical", weight=2),
        crit("t3", "technical", essential=False),
        # experience: (1*100 + 4*75) / 5 = 80 -> 20/25
        crit("e1", "experience"),
        crit("e2", "experience", weight=4),
        # competencies: (2*100 + 3*75) / 5 = 85 -> 17/20
        crit("c1", "competency", weight=2),
        crit("c2", "competency", weight=3),
        # qualifications: (1*100 + 4*75) / 5 = 80 -> 8/10
        crit("q1", "qualification"),
        crit("q2", "qualification", weight=4),
    ]
    values = {
        "t1": 100,
        "t2": 75,
        "t3": 50,
        "e1": 100,
        "e2": 75,
        "c1": 100,
        "c2": 75,
        "q1": 100,
        "q2": 75,
    }
    results = {k: res(k, v) for k, v in values.items()}
    # answers: (3*100 + 2*75) / 5 = 90 -> 9/10
    answers = [
        answer(100, "a1"),
        answer(100, "a2"),
        answer(100, "a3"),
        answer(75, "a4"),
        answer(75, "a5"),
    ]
    s = score(CATS, specs, results, answers)
    assert {c.key: c.points for c in s.categories} == {
        "technical": 30.0,
        "experience": 20.0,
        "competency": 17.0,
        "qualification": 8.0,
        "answers": 9.0,
    }
    assert s.total == 84.0 and s.coverage == 1.0
    assert band_for(s)[0] == RECOMMENDED
    assert score(CATS, [], {}, []).total is None  # nothing assessable: no score at all


def test_missing_reweights_instead_of_scoring_zero() -> None:
    specs = [crit("t1", "technical"), crit("e1", "experience"), crit("q1", "qualification")]
    s = score(CATS, specs, {"t1": res("t1", 100), "e1": res("e1", None), "q1": res("q1", 50)}, [])
    # experience/competency/answers not assessable -> re-normalised over 35 + 10
    assert s.total == round((35 * 100 + 10 * 50) / 45, 2)
    assert s.coverage == 0.45
    assert (
        s.essentials.unknown == ("e1",)
        and s.essentials.met == ("t1",)
        and s.essentials.partial == ("q1",)
    )


def test_property_missing_never_lowers_a_score_or_counts_as_zero() -> None:
    """Exit criterion: missing evidence never produces a 0 score for a criterion."""
    rng = random.Random(7)
    specs = [crit(f"c{i}", CATS[i % 5].key, weight=rng.choice([1, 2, 3])) for i in range(12)]
    for _ in range(300):
        values = {s.id: rng.choice([None, 0, 25, 50, 75, 100]) for s in specs}
        results = {k: res(k, v) for k, v in values.items()}
        base = score(CATS, specs, results, [])
        for cid, value in values.items():
            if value is None:
                assert not results[cid].assessable and results[cid].score is None
        # turning an assessable criterion into "missing" never behaves like a 0
        known = [k for k, v in values.items() if v not in (None, 0)]
        if not known or base.total is None:
            continue
        victim = rng.choice(known)
        as_missing = score(CATS, specs, {**results, victim: res(victim, None)}, [])
        as_zero = score(CATS, specs, {**results, victim: res(victim, 0)}, [])
        if as_missing.total is not None and as_zero.total is not None:
            assert as_missing.total >= as_zero.total


def test_combine_conflicts_and_answers() -> None:
    spec = crit("exp", "experience")
    cv = res("exp", 50)
    conflict = Conflict(
        criterion_id="exp",
        question_key="years",
        kind="experience_years",
        cv_value="1.0 years",
        answer_value="5 years",
        evidence=(REF,),
    )
    merged = combine(spec, cv, [answer(100, "years")], [conflict])
    assert merged.status == EvidenceStatus.CONFLICTING and merged.score == 50  # never lowered
    assert "conflict" in merged.flags and merged.confidence <= 0.4
    from_answer = combine(spec, res("exp", None), [answer(75, "years")], [])
    assert from_answer.status == EvidenceStatus.CANDIDATE_REPORTED and from_answer.score == 75
    assert combine(spec, res("exp", 100), [answer(50)], []).score == 100  # CV evidence first


def test_band_precedence() -> None:
    specs = [
        crit("t1", "technical"),
        crit("e1", "experience"),
        crit("q1", "qualification"),
        crit("c1", "competency"),
        crit("a1", "answers"),
    ]
    good = score(CATS, specs, {s.id: res(s.id, 100) for s in specs}, [])
    assert good.confidence == "high"
    assert band_for(good) == (RECOMMENDED, ("score_and_essentials",))
    assert band_for(good, objected=True)[0] == MANUAL
    assert band_for(good, eligibility_unmet=True)[0] == ELIGIBILITY
    assert band_for(good, conflicts=1) == (REVIEW, ("conflicts",))
    assert band_for(good, flags=[Flag.INJECTION_SUSPECTED])[0] == REVIEW
    listed = score(CATS, specs, {**{s.id: res(s.id, 100) for s in specs}, "t1": res("t1", 50)}, [])
    assert band_for(listed)[0] == RECOMMENDED  # explicit (listed) evidence of the essential
    weak = score(CATS, specs, {**{s.id: res(s.id, 100) for s in specs}, "t1": res("t1", 25)}, [])
    assert band_for(weak)[0] == LOWER  # an essential only weakly evidenced
    low = score(CATS, specs, {"t1": res("t1", 100)}, [])
    band, reasons = band_for(low)
    assert band == REVIEW and "low_coverage" in reasons and "essentials_unknown" in reasons
    nearly = score(CATS, specs, {**{s.id: res(s.id, 100) for s in specs}, "t1": res("t1", 75)}, [])
    assert band_for(nearly)[0] == RECOMMENDED
    assert band_for(nearly, policy=BandPolicy(recommended_min_score=100))[0] == LOWER


def test_evaluate_end_to_end_with_knockout() -> None:
    data = EvaluationInput(
        application_id="app",
        evidence=CandidateEvidence(application_id="app"),
        criteria=(
            CriterionSpec(
                id="py",
                type=CriterionType.SKILL,
                title="Python",
                skill_id="Python",
                category="technical",
            ),
            CriterionSpec(
                id="elig", type=CriterionType.ELIGIBILITY, title="Right to work", category="answers"
            ),
        ),
        categories=CATS,
        questions=(
            QuestionSpec(
                key="work",
                type="yes_no",
                is_knockout=True,
                knockout_expected="yes",
                criterion_id="elig",
            ),
        ),
        answers=(AnswerInput(key="work", value="no"),),
        today=(2026, 10),
    )
    result = evaluate(data)
    assert result.band == ELIGIBILITY and result.eligibility_unmet
    py = next(c for c in result.criteria if c.criterion_id == "py")
    assert py.status == EvidenceStatus.MISSING and py.score is None
    assert result.input_hash == evaluate(data).input_hash
    assert result.input_hash != evaluate(data.model_copy(update={"answers": ()})).input_hash
    objected = evaluate(data.model_copy(update={"objected": True}))
    assert objected.band == MANUAL
