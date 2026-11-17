"""Deterministic criterion rules (P07-T01): qualification, certification/licence, experience,
language. Missing evidence is never a score of 0 (principle 3)."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from ai_engine.contracts import (
    CandidateEvidence,
    CertificationData,
    ClaimSource,
    CriterionResult,
    CriterionSpec,
    CriterionType,
    DateRange,
    EducationData,
    EvidenceStatus,
    ExperienceData,
    ExtractedClaim,
    ExtractionMethod,
    Importance,
    LanguageData,
    PartialDate,
)
from ai_engine.extraction.extract import extract_document
from ai_engine.extraction.parser import extract_claims
from ai_engine.extraction.pii import protect
from ai_engine.extraction.skills import SkillIndex
from ai_engine.matching.rules import Context, evaluate_rule, months_score
from ai_engine.normalisation.qualifications import QualificationIndex, normalise_education

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "fixtures" / "synthetic_cvs"
TODAY = (2026, 10)


@cache
def taxonomy() -> tuple[SkillIndex, QualificationIndex, dict[str, int]]:
    skills = json.loads((ROOT / "fixtures/taxonomy/skills.json").read_text(encoding="utf-8"))
    quals = json.loads((ROOT / "fixtures/taxonomy/qualifications.json").read_text(encoding="utf-8"))
    ranks = {lvl["code"]: lvl["rank"] for lvl in quals["levels"]}
    return (
        SkillIndex.from_taxonomy([dict(s, id=s["name"]) for s in skills["skills"]]),
        QualificationIndex.from_taxonomy(quals["levels"], quals["professional_bodies"]),
        ranks,
    )


def ctx() -> Context:
    return Context(today=TODAY, level_ranks=taxonomy()[2])


def claim(data: Any, snippet: str = "text") -> ExtractedClaim:
    return ExtractedClaim(
        data=data,
        source=ClaimSource(snippet=snippet, document_id="d", page=1, char_start=0, char_end=4),
        method=ExtractionMethod.RULE,
        confidence=0.9,
    )


def evidence(*claims: ExtractedClaim) -> CandidateEvidence:
    return CandidateEvidence(application_id="a", claims=claims)


def spec(type_: CriterionType, title: str, **kw: Any) -> CriterionSpec:
    return CriterionSpec(id="c1", type=type_, title=title, importance=Importance.ESSENTIAL, **kw)


def job(start: tuple[int, int], end: tuple[int, int] | None, **kw: Any) -> ExtractedClaim:
    dates = DateRange(
        start=PartialDate(year=start[0], month=start[1]),
        end=None if end is None else PartialDate(year=end[0], month=end[1]),
        is_current=end is None,
    )
    return claim(ExperienceData(title="Developer", employer="Econet", dates=dates, **kw))


def edu(level: str | None, text: str = "BSc Computer Science", **kw: Any) -> ExtractedClaim:
    return claim(EducationData(qualification_text=text, level=level, **kw))


# ------------------------------------------------------------------------------ contracts
def test_result_contract_enforces_missing_is_not_zero() -> None:
    with pytest.raises(ValidationError):
        CriterionResult(criterion_id="x", status=EvidenceStatus.MISSING, score=0)
    with pytest.raises(ValidationError):
        CriterionResult(criterion_id="x", status=EvidenceStatus.EXPLICIT, score=60)  # not a band
    with pytest.raises(ValidationError):  # a score needs evidence
        CriterionResult(criterion_id="x", status=EvidenceStatus.EXPLICIT, score=100)
    assert not CriterionResult(criterion_id="x", status=EvidenceStatus.MISSING).assessable


@pytest.mark.parametrize(
    ("ctype", "title"),
    [
        (CriterionType.QUALIFICATION, "Degree in computing"),
        (CriterionType.CERTIFICATION, "AWS Certified Cloud Practitioner"),
        (CriterionType.LICENCE, "Driver's licence class 4"),
        (CriterionType.EXPERIENCE, "2+ years software development"),
        (CriterionType.LANGUAGE, "Fluent English"),
    ],
)
def test_no_evidence_is_missing_never_zero(ctype: CriterionType, title: str) -> None:
    result = evaluate_rule(
        spec(ctype, title, min_months=24, qualification_level="BACHELOR"), evidence(), ctx()
    )
    assert result is not None
    assert (
        result.status == EvidenceStatus.MISSING and result.score is None and not result.assessable
    )


def test_types_handled_elsewhere_return_none() -> None:
    assert evaluate_rule(spec(CriterionType.SKILL, "Python"), evidence(), ctx()) is None


# --------------------------------------------------------------------------- qualification
@pytest.mark.parametrize(
    ("level", "required", "score", "reason"),
    [
        ("HONOURS", "BACHELOR", 100, "meets_level"),
        ("BACHELOR", "BACHELOR", 100, "meets_level"),
        ("ZW_HND", "BACHELOR", 50, "rank_below_required"),  # one level below
        ("ZW_ALEVEL", "BACHELOR", 25, "rank_below_required"),
        ("MASTERS", "ZW_ND", 100, "meets_level"),
    ],
)
def test_qualification_rank(level: str, required: str, score: int, reason: str) -> None:
    result = evaluate_rule(
        spec(CriterionType.QUALIFICATION, "Degree", qualification_level=required),
        evidence(edu(level)),
        ctx(),
    )
    assert result is not None and (result.score, result.reason) == (score, reason)
    assert result.evidence[0].claim_index == 0


def test_qualification_field_foreign_unknown_and_best_claim() -> None:
    computing = spec(
        CriterionType.QUALIFICATION,
        "Degree in computing",
        qualification_level="BACHELOR",
        equivalents=("Computer Science", "Information Technology"),
    )
    other_field = evaluate_rule(computing, evidence(edu("BACHELOR", "BCom Accounting")), ctx())
    assert other_field is not None and (other_field.score, other_field.reason) == (
        50,
        "field_differs",
    )
    foreign = evaluate_rule(
        computing, evidence(edu("BACHELOR", foreign=True, needs_verification=True)), ctx()
    )
    assert foreign is not None and foreign.status == EvidenceStatus.NEEDS_VERIFICATION
    assert foreign.score == 75 and "foreign_qualification" in foreign.flags
    # P10-T04: once a person verified it, a foreign qualification counts like a local one
    checked = edu("BACHELOR", foreign=True, needs_verification=True).model_copy(
        update={"method": ExtractionMethod.HUMAN, "confidence": 1.0}
    )
    verified = evaluate_rule(computing, evidence(checked), ctx())
    assert verified is not None and verified.score == 100
    assert verified.status == EvidenceStatus.EXPLICIT
    unknown = evaluate_rule(computing, evidence(edu(None, "Kitchen Wizard Diploma")), ctx())
    assert unknown is not None and unknown.status == EvidenceStatus.NEEDS_VERIFICATION
    best = evaluate_rule(
        computing,
        evidence(edu("ZW_OLEVEL", "ZIMSEC O Level"), edu("HONOURS", "BSc Hons Computer Science")),
        ctx(),
    )
    assert best is not None and best.score == 100 and best.evidence[0].claim_index == 1


def test_or_equivalent_experience() -> None:
    criterion = spec(
        CriterionType.QUALIFICATION,
        "Degree or equivalent",
        qualification_level="BACHELOR",
        min_months=60,
    )
    seasoned = evaluate_rule(criterion, evidence(job((2015, 1), None)), ctx())
    assert seasoned is not None and seasoned.method == "equivalent_experience"
    assert seasoned.status == EvidenceStatus.INFERRED and seasoned.score == 75
    junior = evaluate_rule(criterion, evidence(job((2025, 1), None)), ctx())
    assert junior is not None and junior.status == EvidenceStatus.MISSING
    both = evaluate_rule(criterion, evidence(edu("ZW_ALEVEL"), job((2015, 1), None)), ctx())
    assert both is not None and both.score == 75  # the better of the two routes


# -------------------------------------------------------------------- certification/licence
# EC-AI-16: expired certification -> flagged for review, not a fail
def test_certifications_licences_and_expiry() -> None:
    cert = claim(CertificationData(name="Nurses Council of Zimbabwe - practising certificate"))
    found = evaluate_rule(
        spec(CriterionType.CERTIFICATION, "Nurses Council registration"), evidence(cert), ctx()
    )
    assert found is not None and found.score == 100 and found.status == EvidenceStatus.EXPLICIT
    expired = claim(
        CertificationData(name="Basic Life Support (BLS)", expires=PartialDate(year=2025, month=6))
    )
    old = evaluate_rule(
        spec(CriterionType.CERTIFICATION, "Basic Life Support"), evidence(expired), ctx()
    )
    assert old is not None and old.status == EvidenceStatus.NEEDS_VERIFICATION
    assert old.score == 50 and old.flags == ("expired",)  # needs a look, not a fail
    renewed = claim(
        CertificationData(name="Basic Life Support", expires=PartialDate(year=2027, month=1))
    )
    both = evaluate_rule(
        spec(CriterionType.CERTIFICATION, "Basic Life Support"), evidence(expired, renewed), ctx()
    )
    assert both is not None and both.score == 100 and both.evidence[0].claim_index == 1
    licence = claim(CertificationData(name="Driver's licence class 2", licence_class="2"))
    lower = evaluate_rule(
        spec(CriterionType.LICENCE, "Driver's licence class 4"), evidence(licence), ctx()
    )
    assert (
        lower is not None and lower.score == 50 and lower.reason == "licence_class_below_required"
    )
    other = evaluate_rule(spec(CriterionType.CERTIFICATION, "PMP"), evidence(cert), ctx())
    assert other is not None and other.status == EvidenceStatus.MISSING


# ------------------------------------------------------------------------------ experience
def test_months_score_bands() -> None:
    assert [months_score(m, 24) for m in (24, 30, 18, 12, 3)] == [100, 100, 75, 50, 25]
    assert months_score(0, 0) == 100


def test_min_experience_overlap_and_undated() -> None:
    criterion = spec(CriterionType.EXPERIENCE, "2+ years", min_months=24)
    overlap = evaluate_rule(
        criterion, evidence(job((2023, 1), (2024, 1)), job((2023, 6), (2024, 6))), ctx()
    )
    assert overlap is not None and overlap.score == 50  # 17 months once (71 %), not 24 twice
    assert overlap.reason == "months=17/24"
    undated = evaluate_rule(criterion, evidence(claim(ExperienceData(title="Clerk"))), ctx())
    assert undated is not None and undated.status == EvidenceStatus.NEEDS_VERIFICATION
    assert undated.reason == "roles_without_dates" and undated.score == 50
    mixed = evaluate_rule(
        criterion, evidence(job((2020, 1), None), claim(ExperienceData(title="Clerk"))), ctx()
    )
    assert mixed is not None and mixed.score == 100 and "some_roles_undated" in mixed.flags


# -------------------------------------------------------------------------------- language
def test_language_with_and_without_level() -> None:
    english = claim(LanguageData(language="English", level="conversational"))
    fluent = evaluate_rule(spec(CriterionType.LANGUAGE, "Fluent English"), evidence(english), ctx())
    assert fluent is not None and fluent.score == 75 and fluent.reason == "level_below_required"
    any_level = evaluate_rule(spec(CriterionType.LANGUAGE, "English"), evidence(english), ctx())
    assert any_level is not None and any_level.score == 100
    shona = evaluate_rule(
        spec(CriterionType.LANGUAGE, "Shona or Ndebele", equivalents=("Ndebele",)),
        evidence(claim(LanguageData(language="Ndebele"))),
        ctx(),
    )
    assert shona is not None and shona.score == 100


# ---------------------------------------------------------------------------------- corpus
CORPUS_SPECS: dict[str, CriterionSpec] = {
    "qualification": spec(
        CriterionType.QUALIFICATION, "Qualification", qualification_level="ZW_ND"
    ),
    "council_registration": spec(CriterionType.CERTIFICATION, "Nurses Council registration"),
    "bls": spec(CriterionType.CERTIFICATION, "Basic Life Support"),
}
AGREES = {
    "met": {100},
    "partial": {50, 75},
    "missing": {None, 25},
    "needs_verification": {75, 50},
}


@pytest.mark.skipif(not CORPUS.exists(), reason="synthetic corpus missing")
def test_corpus_agreement_with_gold_labels() -> None:
    skills, quals, _ = taxonomy()
    labels = json.loads((CORPUS / "labels.json").read_text(encoding="utf-8"))["cvs"]
    agree = total = 0
    disagreements = []
    for cv in labels:
        if cv["parse_expected"] != "ok" or cv["needs_ocr"]:
            continue
        result = extract_document((CORPUS / cv["file"]).read_bytes(), document_id=cv["id"])
        result = protect(
            normalise_education(extract_claims(result, today=TODAY, skills=skills), quals)
        )
        ev = CandidateEvidence.from_results(cv["id"], [result])
        for criterion in cv["criteria"]:
            if criterion["kind"] == "skill":
                continue  # P07-T02
            if criterion["kind"] == "qualification":
                criterion_spec = CORPUS_SPECS["qualification"]
            elif criterion["kind"] == "certification":
                criterion_spec = CORPUS_SPECS[criterion["id"]]
            else:
                years = int("".join(ch for ch in criterion["id"] if ch.isdigit()))
                criterion_spec = spec(
                    CriterionType.EXPERIENCE, criterion["label"], min_months=years * 12
                )
            got = evaluate_rule(criterion_spec, ev, ctx())
            assert got is not None
            want = cv["expected_evidence"][criterion["id"]]
            total += 1
            if got.score in AGREES[want]:
                agree += 1
            else:
                disagreements.append((cv["file"], criterion["id"], want, got.score, got.reason))
    assert total > 300
    assert agree / total >= 0.95, disagreements[:10]
