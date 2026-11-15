"""Screening answers and CV/answer conflicts (P07-T04): EC-AI-03, EC-AI-05."""

from __future__ import annotations

from typing import Any

import pytest

from ai_engine.contracts import (
    CandidateEvidence,
    ClaimSource,
    CriterionResult,
    CriterionSpec,
    CriterionType,
    EducationData,
    EvidenceRef,
    EvidenceStatus,
    ExtractedClaim,
    ExtractionMethod,
    SkillData,
)
from ai_engine.matching.answers import AnswerInput, QuestionSpec, score_answer, score_answers, snap
from ai_engine.matching.conflicts import find_conflicts

RANKS = {"ZW_OLEVEL": 20, "ZW_HND": 60, "BACHELOR": 70, "MASTERS": 90}


def q(key: str = "q1", type_: str = "yes_no", mode: str = "none", **kw: Any) -> QuestionSpec:
    scoring = {"mode": mode, **kw.pop("scoring", {})}
    return QuestionSpec(key=key, type=type_, prompt=f"Question {key}?", scoring=scoring, **kw)


def a(value: Any, key: str = "q1") -> AnswerInput:
    return AnswerInput(key=key, value=value, response_id=f"r-{key}")


def test_snap_to_bands() -> None:
    assert [snap(v) for v in (0, 12, 13, 40, 62.5, 88, 100, 140)] == [
        0,
        0,
        25,
        50,
        75,
        100,
        100,
        100,
    ]


def test_unanswered_is_missing_never_zero() -> None:
    result = score_answer(q(mode="exact", scoring={"expected": "yes"}), None)
    assert result.status == EvidenceStatus.MISSING and result.score is None
    assert score_answer(q(mode="exact", scoring={"expected": "yes"}), a("")).score is None


def test_exact_options_range_text_and_human() -> None:
    exact = q(mode="exact", scoring={"expected": "yes"})
    assert score_answer(exact, a(True)).score == 100
    assert score_answer(exact, a("No")).score == 0  # an explicit answer is evidence
    options = q(
        type_="single_choice", mode="options", options=(("junior", 1), ("mid", 2), ("senior", 4))
    )
    assert score_answer(options, a("mid")).score == 50
    assert score_answer(options, a("senior")).score == 100
    multi = q(type_="multiple_choice", mode="options", options=(("a", 1), ("b", 1), ("c", 2)))
    assert score_answer(multi, a(["a", "c"])).score == 75
    rng = q(type_="number", mode="range", scoring={"min": 2, "max": 10})
    assert score_answer(rng, a(4)).score == 100
    assert score_answer(rng, a("1 year")).score == 25
    assert score_answer(rng, a("lots")).status == EvidenceStatus.NEEDS_VERIFICATION
    bands = q(
        type_="number",
        mode="range",
        scoring={"bands": [{"min": 0, "max": 1, "score": 25}, {"min": 2, "score": 100}]},
    )
    assert score_answer(bands, a(3)).score == 100
    text = q(
        type_="long_text",
        mode="rubric_text",
        scoring={"keywords": ["unit tests", "code review", "CI"]},
    )
    result = score_answer(text, a("I write unit tests and do code review every day"))
    assert result.score == 75 and result.confidence == 0.5
    human = score_answer(q(type_="long_text", mode="human"), a("A long story"))
    assert human.status == EvidenceStatus.NEEDS_VERIFICATION and human.score is None
    plain = score_answer(q(mode="none"), a("yes"))
    assert plain.status == EvidenceStatus.CANDIDATE_REPORTED and plain.score is None
    assert plain.evidence[0].question_key == "q1"
    assert plain.evidence[0].source.question_response_id == "r-q1"


def test_knockout_flags_for_a_human_never_decides() -> None:
    ko = q(is_knockout=True, knockout_expected="yes")
    assert score_answer(ko, a("no")).eligibility_unmet is True
    assert score_answer(ko, a("Yes")).eligibility_unmet is False
    assert score_answer(ko, None).eligibility_unmet is False  # unknown, not unmet
    choice = q(type_="single_choice", is_knockout=True, knockout_expected=["class_4", "class_2"])
    assert score_answer(choice, a("class_4")).eligibility_unmet is False
    assert score_answer(choice, a("none")).eligibility_unmet is True
    results = score_answers([ko, q("q2")], [a("no")])
    assert [r.key for r in results] == ["q1", "q2"] and results[1].status == EvidenceStatus.MISSING


# ------------------------------------------------------------------------------- conflicts
def claim(data: Any) -> ExtractedClaim:
    return ExtractedClaim(
        data=data,
        source=ClaimSource(snippet="cv text", document_id="d", page=1, char_start=0, char_end=7),
        method=ExtractionMethod.RULE,
        confidence=0.9,
    )


def cv_result(criterion_id: str, months: int) -> CriterionResult:
    return CriterionResult(
        criterion_id=criterion_id,
        status=EvidenceStatus.EXPLICIT,
        score=50,
        evidence=(
            EvidenceRef(claim_index=0, source=ClaimSource(snippet="role", document_id="d", page=1)),
        ),
        reason=f"months={months}/24",
    )


SPECS = [
    CriterionSpec(id="exp", type=CriterionType.EXPERIENCE, title="2+ years", min_months=24),
    CriterionSpec(id="django", type=CriterionType.SKILL, title="Django", skill_id="Django"),
    CriterionSpec(
        id="degree",
        type=CriterionType.QUALIFICATION,
        title="Degree",
        qualification_level="BACHELOR",
    ),
]
QUESTIONS = [
    q("years", "number", criterion_id="exp"),
    q("django_years", "number", criterion_id="django"),
    q("level", "single_choice", criterion_id="degree"),
]


@pytest.mark.parametrize(
    ("answer_years", "cv_months", "conflict"),
    [(5, 12, True), (2, 24, False), (3, 24, False), (1, 60, True), (0.5, 0, False)],
)
def test_experience_years_conflict(answer_years: float, cv_months: int, conflict: bool) -> None:
    found = find_conflicts(
        SPECS,
        QUESTIONS,
        [a(answer_years, "years")],
        CandidateEvidence(application_id="x"),
        {"exp": cv_result("exp", cv_months)},
        RANKS,
    )
    assert bool(found) is conflict
    if found:
        assert found[0].kind == "experience_years" and found[0].evidence


def test_skill_years_and_qualification_conflicts() -> None:
    evidence = CandidateEvidence(
        application_id="x",
        claims=(
            claim(SkillData(raw="Django", skill_id="Django", canonical="Django", years=1)),
            claim(EducationData(qualification_text="HND IT", level="ZW_HND")),
        ),
    )
    found = find_conflicts(
        SPECS, QUESTIONS, [a(5, "django_years"), a("MASTERS", "level")], evidence, {}, RANKS
    )
    assert {c.kind for c in found} == {"skill_years", "qualification_level"}
    assert all(c.evidence for c in found)
    # no CV evidence means no conflict (missing is not a contradiction)
    assert (
        find_conflicts(
            SPECS,
            QUESTIONS,
            [a(5, "django_years")],
            CandidateEvidence(application_id="x"),
            {},
            RANKS,
        )
        == []
    )
    # an answer at or below the CV level is consistent
    assert (
        find_conflicts(
            SPECS,
            QUESTIONS,
            [a("BACHELOR", "level")],
            CandidateEvidence(
                application_id="x",
                claims=(claim(EducationData(qualification_text="BSc", level="MASTERS")),),
            ),
            {},
            RANKS,
        )
        == []
    )
