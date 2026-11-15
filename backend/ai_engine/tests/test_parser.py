"""Claim extraction (P06-T07): every claim located, snippet-backed and correctly classified."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from ai_engine.contracts import (
    SNIPPET_MAX,
    CandidateEvidence,
    ClaimEvidence,
    EmploymentKind,
    ExcludedReason,
    ExtractedClaim,
    ExtractionMethod,
    ExtractionResult,
    SectionKind,
)
from ai_engine.extraction.extract import extract_document
from ai_engine.extraction.layout import RawBlock, build_page
from ai_engine.extraction.parser import extract_claims, split_title_employer
from ai_engine.extraction.sections import detect_sections
from ai_engine.extraction.skills import SkillIndex

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "fixtures" / "synthetic_cvs"
TODAY = (2026, 10)
K = SectionKind


@cache
def taxonomy() -> SkillIndex:
    doc = json.loads((ROOT / "fixtures" / "taxonomy" / "skills.json").read_text(encoding="utf-8"))
    return SkillIndex.from_taxonomy([dict(s, id=s["name"]) for s in doc["skills"]])


def from_text(*blocks: str | RawBlock) -> ExtractionResult:
    raw = [b if isinstance(b, RawBlock) else RawBlock(b) for b in blocks]
    page = build_page(1, raw, order=False)
    from ai_engine.contracts import DocumentText, ExtractionStatus

    doc = DocumentText(
        document_id="doc-1", sha256="0" * 64, mime="application/pdf", parser_used="t", pages=(page,)
    )
    result = ExtractionResult(
        status=ExtractionStatus.SUCCEEDED, document=doc, sections=tuple(detect_sections([page]))
    )
    return extract_claims(result, today=TODAY, skills=taxonomy())


def of(result: ExtractionResult, kind: str) -> list[Any]:
    return [c.data for c in result.claims if c.claim_type == kind and c.evaluable]


def located(result: ExtractionResult, claim: ExtractedClaim) -> str:
    page = result.document.pages[0]  # type: ignore[union-attr]
    return page.text[claim.source.char_start : claim.source.char_end]


# ------------------------------------------------------------------------ skill index
def test_skill_index_matching_rules() -> None:
    idx = taxonomy()
    found = [m.canonical for m in idx.find("Python, Django REST Framework, Go, C++ and C#")]
    assert found == ["Python", "Django REST Framework", "Go", "C++", "C#"]
    assert [m.canonical for m in idx.find("We will go live in spring")] == []
    assert [m.canonical for m in idx.find("Built Node.js and ASP.NET services")] == [
        "Node.js",
        "ASP.NET",
    ]
    assert [m.canonical for m in idx.find("Grade C pass")] == []  # one-letter skill needs a list
    assert [m.canonical for m in idx.find("R, SQL")] == ["R", "SQL"]
    assert idx.lookup("infection control") and idx.lookup("infection control").canonical == (  # type: ignore[union-attr]
        "Infection prevention and control"
    )
    assert idx.lookup("nonsense skill") is None
    mention = idx.find("Advanced Python-based ETL")[0]
    assert (mention.text, mention.start, mention.end) == ("Python", 9, 15)


# ------------------------------------------------------------------------- experience
def test_header_splitting() -> None:
    assert split_title_employer("Software Developer | Econet Wireless, Harare | ") == (
        "Software Developer",
        "Econet Wireless",
        "Harare",
    )
    assert split_title_employer("Delta Beverages - Accountant") == (
        "Accountant",
        "Delta Beverages",
        "",
    )
    assert split_title_employer("Registered Nurse at Parirenyatwa Hospital") == (
        "Registered Nurse",
        "Parirenyatwa Hospital",
        "",
    )
    assert split_title_employer("Clerk, OK Zimbabwe, Mutare") == ("Clerk", "OK Zimbabwe", "Mutare")


def test_experience_layouts_and_kinds() -> None:
    result = from_text(
        "Experience",
        "Software Developer | Cassava Smartech, Harare | Jan 2022 - Present\n"
        "- Built payment APIs in Django\n- Mentored two juniors",
        "Junior Developer | Econet, Harare | 2019 - 2021 | Contract",
        "Zambezi Fintech\nIT Intern\n06/2018 - 12/2018",
        "Volunteer Tutor, Harare Library, Mar 2017 - Jun 2017",
        "Industrial Attachment",
        "Attachment Student | ZESA | Feb 2016 - Nov 2016",
    )
    jobs = of(result, "experience")
    summary = [(j.title, j.employer, j.employment_kind) for j in jobs]
    assert summary == [
        ("Software Developer", "Cassava Smartech", EmploymentKind.FULL_TIME),
        ("Junior Developer", "Econet", EmploymentKind.CONTRACT),
        ("IT Intern", "Zambezi Fintech", EmploymentKind.INTERNSHIP),
        ("Volunteer Tutor", "Harare Library", EmploymentKind.VOLUNTEER),
        ("Attachment Student", "ZESA", EmploymentKind.ATTACHMENT),
    ]
    first = jobs[0]
    assert first.dates.is_current and first.location == "Harare"
    assert first.responsibilities == ("Built payment APIs in Django", "Mentored two juniors")
    claims = [c for c in result.claims if c.claim_type == "experience"]
    assert "Cassava Smartech" in located(result, claims[0])
    assert claims[2].source.snippet.startswith("Zambezi Fintech")
    assert claims[4].section == K.ATTACHMENT


def test_date_anomaly_is_flagged_not_dropped() -> None:
    result = from_text("Experience", "Accountant | Delta | Mar 2022 - Jan 2020")
    (job,) = of(result, "experience")
    assert job.dates.start is None and "date_anomaly" in result.flags
    claim = next(c for c in result.claims if c.claim_type == "experience")
    assert claim.confidence < 0.85


# ------------------------------------------------- education, certs, languages, more
def test_education_certifications_languages_projects_profile() -> None:
    result = from_text(
        "Profile\nRegistered nurse with 6 years of experience in maternity wards.",
        "Education\nBSc Honours in Nursing Science, University of Zimbabwe, 2018 (2.1)\n"
        "ZIMSEC Advanced Level, Chinhoyi High School, 2013\n- Head girl",
        "Certifications\nACCA (Association of Chartered Certified Accountants) - finalist\n"
        "Driver's licence class 4, 2019\nAWS Certified Cloud Practitioner (2024)",
        "Projects\nClinic queue app\n- Built with React and Firebase",
        "Languages\nEnglish (fluent), Shona - native, a little French",
    )
    profile = of(result, "summary")
    assert profile and "maternity" in profile[0].text
    edu = of(result, "education")
    assert [(e.qualification_text, e.institution, e.grade) for e in edu] == [
        ("BSc Honours in Nursing Science", "University of Zimbabwe", "2.1"),
        ("ZIMSEC Advanced Level", "Chinhoyi High School", ""),
    ]
    assert edu[0].dates.end is not None and edu[0].dates.end.year == 2018
    certs = of(result, "certification")
    assert [c.name for c in certs] == [
        "ACCA (Association of Chartered Certified Accountants) - finalist",
        "Driver's licence class 4",
        "AWS Certified Cloud Practitioner",
    ]
    assert certs[0].body == "ACCA" and certs[1].licence_class == "4"
    assert certs[2].issued is not None and certs[2].issued.year == 2024
    projects = of(result, "project")
    assert projects[0].title == "Clinic queue app" and projects[0].technologies == (
        "React",
        "Firebase",
    )
    languages = {(lang.language, lang.level) for lang in of(result, "language")}
    assert languages == {("English", "fluent"), ("Shona", "native"), ("French", "")}


def test_skills_confidence_years_raw_items_and_semantic() -> None:
    result = from_text(
        "Experience\nDeveloper | Econet | 2020 - 2024\n- 4 years of Python and Django development",
        "Skills\nPython, Docker, Kubernetes (2 years), Goat herding, Labour Act",
    )
    skills = {c.data.canonical or c.data.raw: c for c in result.claims if c.claim_type == "skill"}
    assert skills["Python"].section == K.EXPERIENCE and skills["Python"].confidence == 0.85
    assert skills["Python"].data.years == 4  # the stronger, used-in-role mention is kept
    assert skills["Docker"].section == K.SKILLS and skills["Docker"].confidence == 0.6
    assert skills["Kubernetes"].data.years == 2
    assert skills["Labour law"].data.raw == "Labour Act"
    raw = skills["Goat herding"]
    assert raw.data.skill_id is None and raw.method == ExtractionMethod.SECTION
    assert raw.confidence == 0.4

    def semantic(phrase: str) -> tuple[str, str, float] | None:
        return ("Livestock", "Livestock management", 0.82) if "goat" in phrase.lower() else None

    page = result.document.pages[0]  # type: ignore[union-attr]
    again = extract_claims(
        result.model_copy(update={"claims": ()}), today=TODAY, skills=taxonomy(), semantic=semantic
    )
    lead = next(
        c for c in again.claims if c.claim_type == "skill" and c.data.skill_id == "Livestock"
    )
    assert lead.method == ExtractionMethod.EMBEDDING and lead.evidence == ClaimEvidence.INFERRED
    assert lead.confidence == 0.6 and "Goat herding" in page.text[lead.source.char_start :]


def test_hidden_text_and_excluded_sections() -> None:
    result = from_text(
        "Tendai Moyo\ntendai@example.test | +263 77 123 4567",
        "Skills\nExcel",
        "Personal Details\nDate of birth: 01/01/1990\nHobbies: Python coding",
        "Referees\nMr Ncube, Delta, +263 77 000 0000",
        RawBlock("Kubernetes, Rust and Go expert", hidden=True),
    )
    hidden = [c for c in result.claims if c.excluded_reason == ExcludedReason.HIDDEN_TEXT]
    assert {c.data.canonical for c in hidden} == {"Kubernetes", "Rust", "Go"}
    evaluable = {c.data.canonical for c in result.claims if c.claim_type == "skill" and c.evaluable}
    assert evaluable == {"Microsoft Excel"}  # nothing from personal details or referees
    contact = next(c for c in result.claims if c.claim_type == "contact")
    assert contact.data.email == "tendai@example.test" and not contact.evaluable
    evidence = CandidateEvidence.from_results("app-1", [result])
    assert all(c.evaluable for c in evidence.claims)
    assert not any(c.data.type == "contact" for c in evidence.claims)


def test_failed_result_is_untouched() -> None:
    failed = extract_document(b"%PDF-1.4 broken", document_id="d")
    assert extract_claims(failed, today=TODAY, skills=taxonomy()) is failed


# ----------------------------------------------------------------------------- corpus
@pytest.mark.skipif(not CORPUS.exists(), reason="synthetic corpus missing")
def test_corpus_claims_meet_targets() -> None:
    """Every claim is located and snippet-backed; recall/accuracy above docs/09 §5 targets."""
    data = json.loads((CORPUS / "labels.json").read_text(encoding="utf-8"))
    idx = taxonomy()
    n: dict[str, int] = dict.fromkeys(
        [
            "exp",
            "exp_hit",
            "kind_ok",
            "edu",
            "edu_hit",
            "cert",
            "cert_hit",
            "lang",
            "lang_hit",
            "skill",
            "skill_hit",
        ],
        0,
    )
    for cv in data["cvs"]:
        if cv["parse_expected"] != "ok" or cv["needs_ocr"]:
            continue
        base = extract_document((CORPUS / cv["file"]).read_bytes(), document_id=cv["id"])
        result = extract_claims(base, today=TODAY, skills=idx)
        page = result.document.pages[0]  # type: ignore[union-attr]
        for claim in result.claims:  # no claim without a source snippet (exit criterion)
            src = claim.source
            assert src.snippet and len(src.snippet) <= SNIPPET_MAX
            assert src.document_id == cv["id"] and src.page == 1
            assert src.char_start is not None and src.char_end is not None
            located_text = " ".join(page.text[src.char_start : src.char_end].split())
            assert located_text.startswith(src.snippet.rstrip("…")[:40]), (cv["file"], claim)
        ev = [c for c in result.claims if c.evaluable]
        jobs = [c.data for c in ev if c.claim_type == "experience"]
        for j in cv["experience"]:
            n["exp"] += 1
            hit = [x for x in jobs if (x.title, x.employer) == (j["title"], j["employer"])]
            n["exp_hit"] += bool(hit)
            n["kind_ok"] += bool(hit) and hit[0].employment_kind.value == j["kind"]
        quals = {c.data.qualification_text for c in ev if c.claim_type == "education"}
        n["edu"] += len(cv["education"])
        n["edu_hit"] += sum(e["qualification"] in quals for e in cv["education"])
        certs = {c.data.name for c in ev if c.claim_type == "certification"}
        n["cert"] += len(cv["certifications"])
        n["cert_hit"] += sum(c in certs for c in cv["certifications"])
        langs = {c.data.language for c in ev if c.claim_type == "language"}
        n["lang"] += len(cv["languages"])
        n["lang_hit"] += sum(lang in langs for lang in cv["languages"])
        if "equivalent_wording" not in cv["variations"]:  # synonyms need embeddings (P06-T10)
            found = {
                (c.data.canonical or c.data.raw).lower() for c in ev if c.claim_type == "skill"
            }
            for skill in cv["skills"]:
                entry = idx.lookup(skill)
                n["skill"] += 1
                n["skill_hit"] += (entry.canonical if entry else skill).lower() in found
    assert n["exp_hit"] / n["exp"] >= 0.95, n
    assert n["kind_ok"] / n["exp_hit"] >= 0.95, n
    assert n["edu_hit"] == n["edu"], n
    assert n["cert_hit"] / n["cert"] >= 0.95, n
    assert n["lang_hit"] == n["lang"], n
    assert n["skill_hit"] / n["skill"] >= 0.95, n
