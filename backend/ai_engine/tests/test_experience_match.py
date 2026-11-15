"""Experience criteria with role relevance (P07-T03): EC-AI-02, EC-DOC-18/21."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_engine.contracts import (
    CandidateEvidence,
    ClaimSource,
    CriterionSpec,
    CriterionType,
    DateRange,
    EmploymentKind,
    EvidenceStatus,
    ExperienceData,
    ExtractedClaim,
    ExtractionMethod,
    PartialDate,
)
from ai_engine.extraction.extract import extract_document
from ai_engine.extraction.parser import extract_claims
from ai_engine.matching.config import EngineConfig
from ai_engine.matching.experience_match import JobContext, match_experience, role_relevance, stem
from ai_engine.matching.rules import Context
from ai_engine.matching.semantic import EmbeddingService, HashingEncoder
from ai_engine.normalisation.titles import normalise_experience

CORPUS = Path(__file__).resolve().parents[2] / "fixtures" / "synthetic_cvs"
CTX = Context(today=(2026, 10), level_ranks={})
DEV = JobContext("Software Developer", "Build and maintain web services in Python and Django.")


def role(
    title: str,
    start: tuple[int, int],
    end: tuple[int, int] | None,
    kind: EmploymentKind = EmploymentKind.FULL_TIME,
    duties: tuple[str, ...] = (),
) -> ExtractedClaim:
    dates = DateRange(
        start=PartialDate(year=start[0], month=start[1]),
        end=None if end is None else PartialDate(year=end[0], month=end[1]),
        is_current=end is None,
    )
    return ExtractedClaim(
        data=ExperienceData(
            title=title, employer="Acme", dates=dates, employment_kind=kind, responsibilities=duties
        ),
        source=ClaimSource(snippet=title, document_id="d", page=1, char_start=0, char_end=5),
        method=ExtractionMethod.RULE,
        confidence=0.85,
    )


def ev(*claims: ExtractedClaim) -> CandidateEvidence:
    return CandidateEvidence(application_id="a", claims=claims)


def spec(
    title: str = "2+ years software development", months: int = 24, **kw: Any
) -> CriterionSpec:
    return CriterionSpec(
        id="exp", type=CriterionType.EXPERIENCE, title=title, min_months=months, **kw
    )


def test_stemming() -> None:
    assert stem("developer") == stem("development") == "develop"
    assert stem("accountant") == stem("accounting") == "account"


def test_relevance_methods() -> None:
    c = spec()
    assert (
        role_relevance(role("Senior Software Engineer", (2020, 1), None), c, DEV).method == "title"
    )
    keyword = role_relevance(role("Backend Programmer Lead", (2020, 1), None), c, DEV)
    assert keyword.relevant  # "programmer" normalises to software developer
    duties = role_relevance(
        role(
            "Technical Officer",
            (2020, 1),
            None,
            duties=("Maintained Python web services", "Built Django APIs for the web team"),
        ),
        c,
        DEV,
    )
    assert duties.relevant and duties.method == "keywords"
    assert not role_relevance(role("Waiter", (2020, 1), None), c, DEV).relevant
    hr_listed = role_relevance(
        role("Systems Analyst", (2020, 1), None), spec(equivalents=("Systems Analyst",)), DEV
    )
    assert hr_listed.method == "title"


def test_only_relevant_months_count_with_overlap_once() -> None:
    result = match_experience(
        spec(),
        ev(
            role("Software Developer", (2022, 1), (2024, 1)),
            role("Backend Developer", (2023, 1), (2024, 6)),  # overlaps
            role("Waiter", (2015, 1), (2021, 1)),  # six years, not relevant
        ),
        CTX,
        DEV,
    )
    assert result.score == 100 and result.reason == "months=29/24"
    assert "some_roles_not_relevant" in result.flags
    assert {e.claim_index for e in result.evidence} == {0, 1}


def test_no_relevant_role_is_weak_evidence_not_a_fail() -> None:
    result = match_experience(spec(), ev(role("Waiter", (2015, 1), (2021, 1))), CTX, DEV)
    assert result.score == 25 and result.reason == "no_relevant_roles"
    assert "relevance_uncertain" in result.flags and result.confidence <= 0.3
    assert match_experience(spec(), ev(), CTX, DEV).status == EvidenceStatus.MISSING


def test_attachments_count_only_when_the_rubric_says_so() -> None:
    attachment = role(
        "Software Developer Attachment Student", (2024, 1), (2025, 1), EmploymentKind.ATTACHMENT
    )
    plain = match_experience(spec(months=12), ev(attachment), CTX, DEV)
    assert plain.score == 25 and plain.reason == "not_counted_by_rubric"
    assert "only_attachment_internship_or_volunteer" in plain.flags
    counted = match_experience(
        spec(months=12), ev(attachment), CTX, DEV, include_kinds=[EmploymentKind.ATTACHMENT]
    )
    assert counted.score == 100


def test_semantic_relevance_when_keywords_miss() -> None:
    svc = EmbeddingService(HashingEncoder())
    c = spec("2+ years software development")
    similar = role("Software Develop Specialist", (2020, 1), None)
    loose = EngineConfig(role_relevance_threshold=0.2)
    judged = role_relevance(
        role("Applications Programmer Analyst", (2020, 1), None),
        c,
        JobContext("Web Programmer"),
        semantic=svc,
        config=loose,
    )
    assert judged.method in ("keywords", "semantic", "title")
    strict = EngineConfig(role_relevance_threshold=0.99)
    waiter = role_relevance(role("Waiter", (2020, 1), None), c, DEV, semantic=svc, config=strict)
    assert not waiter.relevant and waiter.method == "semantic"
    assert role_relevance(similar, c, DEV).relevant


@pytest.mark.skipif(not CORPUS.exists(), reason="synthetic corpus missing")
def test_corpus_experience_agreement() -> None:
    titles = {
        "software_developer": "Software Developer",
        "accountant": "Accountant",
        "registered_nurse": "Registered Nurse",
        "data_analyst": "Data Analyst",
        "hr_officer": "Human Resources Officer",
    }
    agrees = {"met": {100}, "partial": {50, 75}, "missing": {None, 25}}
    labels = json.loads((CORPUS / "labels.json").read_text(encoding="utf-8"))["cvs"]
    agree = total = 0
    for cv in labels:
        if cv["parse_expected"] != "ok" or cv["needs_ocr"]:
            continue
        result = extract_claims(
            extract_document((CORPUS / cv["file"]).read_bytes(), document_id=cv["id"]),
            today=(2026, 10),
        )
        evidence = CandidateEvidence.from_results(cv["id"], [normalise_experience(result)])
        for item in cv["criteria"]:
            if item["kind"] != "experience":
                continue
            years = int("".join(ch for ch in item["id"] if ch.isdigit()))
            got = match_experience(
                spec(item["label"], years * 12), evidence, CTX, JobContext(titles[cv["role"]])
            )
            total += 1
            agree += got.score in agrees[cv["expected_evidence"][item["id"]]]
    assert total > 120 and agree / total >= 0.95, (agree, total)
