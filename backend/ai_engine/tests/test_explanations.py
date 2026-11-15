"""Explanations, grounding and clarifications (P07-T06)."""

from __future__ import annotations

import pytest

from ai_engine.contracts import (
    CandidateEvidence,
    CertificationData,
    ClaimSource,
    CriterionSpec,
    CriterionType,
    EvidenceRef,
    ExtractedClaim,
    ExtractionMethod,
    Importance,
    PartialDate,
    SkillData,
)
from ai_engine.evaluation.engine import EvaluationInput, evaluate
from ai_engine.evaluation.scoring import CategorySpec
from ai_engine.explanations.clarifications import suggest
from ai_engine.explanations.grounding import explain, grounding_rate, validate
from ai_engine.explanations.templates import Sentence, build
from ai_engine.matching.answers import AnswerInput, QuestionSpec

from .benchmark.corpus import CORPUS, evaluate_cv, readable_cvs


def claim(data: object, snippet: str) -> ExtractedClaim:
    return ExtractedClaim(
        data=data,  # type: ignore[arg-type]
        source=ClaimSource(snippet=snippet, document_id="d", page=2, char_start=0, char_end=5),
        method=ExtractionMethod.TAXONOMY,
        confidence=0.9,
        section=None,
    )


EVIDENCE = CandidateEvidence(
    application_id="a",
    claims=(
        claim(
            SkillData(raw="Python", skill_id="Python", canonical="Python"), "Built Python services"
        ),
        claim(
            CertificationData(name="Basic Life Support", expires=PartialDate(year=2024, month=1)),
            "Basic Life Support (2022)",
        ),
    ),
)
SPECS = (
    CriterionSpec(
        id="py",
        type=CriterionType.SKILL,
        title="Python",
        skill_id="Python",
        importance=Importance.ESSENTIAL,
        category="technical",
    ),
    CriterionSpec(
        id="rust",
        type=CriterionType.SKILL,
        title="Rust",
        skill_id="Rust",
        importance=Importance.ESSENTIAL,
        category="technical",
    ),
    CriterionSpec(
        id="bls", type=CriterionType.CERTIFICATION, title="Basic Life Support", category="technical"
    ),
    CriterionSpec(
        id="exp",
        type=CriterionType.EXPERIENCE,
        title="2+ years software development",
        min_months=24,
        importance=Importance.ESSENTIAL,
        category="experience",
    ),
)


def run() -> tuple[EvaluationInput, object]:
    data = EvaluationInput(
        application_id="a",
        evidence=EVIDENCE,
        criteria=SPECS,
        categories=(
            CategorySpec(key="technical", weight=60),
            CategorySpec(key="experience", weight=40),
        ),
        questions=(
            QuestionSpec(
                key="years",
                type="number",
                criterion_id="exp",
                prompt="Years?",
                scoring={"mode": "range", "min": 2},
            ),
        ),
        answers=(AnswerInput(key="years", value=4),),
        today=(2026, 10),
    )
    return data, evaluate(data)


def test_sentences_cite_and_quote_evidence() -> None:
    _, result = run()
    explanation = explain(result, SPECS, EVIDENCE)  # type: ignore[arg-type]
    assert explanation.dropped == 0 and grounding_rate(explanation) == 1.0
    texts = {s.criterion_id: s for s in explanation.sentences}
    assert texts["py"].kind == "partial"  # listed-only skill (50)
    assert "“Built Python services” (CV p.2)" in texts["py"].text
    assert texts["rust"].kind == "gap"
    assert (
        texts["rust"].text == "No evidence found for Rust — this is unknown, not a confirmed gap."
    )
    assert texts["bls"].kind == "verify"  # expired licence needs a person
    assert texts["exp"].kind in ("partial", "strength")  # from the screening answer
    assert all("reject" not in s.text.lower() for s in explanation.sentences)


def test_grounding_drops_unsupported_sentences() -> None:
    _, result = run()
    good = build(result, SPECS)  # type: ignore[arg-type]
    fake_ref = EvidenceRef(
        claim_index=0, source=ClaimSource(snippet="10 years of Rust", document_id="d", page=1)
    )
    bad = [
        Sentence(
            kind="strength",
            criterion_id="rust",
            text="Evidence of Rust: “10 years of Rust”.",
            citations=(fake_ref,),
        ),
        Sentence(
            kind="strength",
            criterion_id="py",
            text="Evidence of Python: “Rust guru”.",
            citations=good[0].citations,
        ),
        Sentence(kind="strength", criterion_id="py", text="Great Python developer."),  # no citation
        Sentence(
            kind="gap", criterion_id="py", text="No evidence found for Python."
        ),  # but there is
        Sentence(
            kind="strength",
            criterion_id="py",
            text="Python.",
            citations=(
                EvidenceRef(
                    claim_index=99, source=ClaimSource(snippet="x", document_id="d", page=1)
                ),
            ),
        ),
    ]
    checked = validate([*good, *bad], EVIDENCE, result.criteria, result.answers)  # type: ignore[attr-defined]
    assert checked.dropped == len(bad) and len(checked.sentences) == len(good)
    assert grounding_rate(checked) < 1.0


def test_clarification_suggestions() -> None:
    _, result = run()
    asks = {c.criterion_id: c for c in suggest(result, SPECS)}  # type: ignore[arg-type]
    assert asks["rust"].reason == "missing_essential" and "Rust" in asks["rust"].question
    assert asks["bls"].reason == "needs_verification" and "renewed" in asks["bls"].question
    assert "py" not in asks  # evidence found, nothing to ask


@pytest.mark.skipif(not CORPUS.exists(), reason="synthetic corpus missing")
def test_corpus_explanations_are_fully_grounded() -> None:
    """Exit criterion: grounding 100 % on the synthetic set."""
    sentences = dropped = 0
    for cv in list(readable_cvs())[::3]:
        inp, result, _ = evaluate_cv(cv)
        explanation = explain(result, inp.criteria, inp.evidence)
        sentences += len(explanation.sentences)
        dropped += explanation.dropped
    assert sentences > 100 and dropped == 0
