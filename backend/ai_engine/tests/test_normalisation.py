"""Qualification levels and job titles (P06-T08): EC-DOC-22/23."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

import pytest

from ai_engine.extraction.extract import extract_document
from ai_engine.extraction.parser import extract_claims
from ai_engine.normalisation.qualifications import QualificationIndex, normalise_education
from ai_engine.normalisation.titles import normalise_experience, normalise_title

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "fixtures" / "synthetic_cvs"
LABEL_LEVELS = {
    "o_level": "ZW_OLEVEL",
    "a_level": "ZW_ALEVEL",
    "national_certificate": "ZW_NC",
    "national_diploma": "ZW_ND",
    "diploma": "ZW_ND",
    "hnd": "ZW_HND",
    "bachelor": "BACHELOR",
    "honours": "HONOURS",
}


@cache
def index() -> QualificationIndex:
    doc = json.loads((ROOT / "fixtures/taxonomy/qualifications.json").read_text(encoding="utf-8"))
    return QualificationIndex.from_taxonomy(doc["levels"], doc["professional_bodies"])


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("ZIMSEC Ordinary Level (6 subjects)", "ZW_OLEVEL"),
        ("5 O Levels including Maths and English", "ZW_OLEVEL"),
        ("ZIMSEC Advanced Level", "ZW_ALEVEL"),
        ("Cambridge A Level", "INTL_AS_A"),
        ("National Certificate in Business Studies", "ZW_NC"),
        ("NC in Electrical Power Engineering", "ZW_NC"),
        ("ND Accountancy", "ZW_ND"),
        ("National Diploma in Computer Science", "ZW_ND"),
        ("Higher National Diploma in Accountancy", "ZW_HND"),
        ("HND Information Technology", "ZW_HND"),
        ("Diploma in General Nursing (RGN)", "ZW_ND"),
        ("BSc in Nursing Science", "BACHELOR"),
        ("B.Com Accounting", "BACHELOR"),
        ("BSc Honours in Computer Science", "HONOURS"),
        ("Bachelor of Accountancy Honours", "HONOURS"),
        ("BCom (Hons) Finance", "HONOURS"),
        ("Postgraduate Diploma in Education", "PGDIP"),
        ("MBA", "MASTERS"),
        ("Master of Science in Data Science", "MASTERS"),
        ("PhD in Public Health", "PHD"),
    ],
)
def test_levels(text: str, code: str) -> None:
    found = index().match(text)
    assert found.level is not None and found.level.code == code, (text, found)
    assert not found.foreign and not found.needs_verification


def test_short_aliases_need_capitals_and_unknowns_need_verification() -> None:
    assert index().match("trained as a ma and pa shop owner").level is None
    unknown = index().match("Certified Kitchen Wizard")
    assert unknown.level is None and unknown.needs_verification  # unknown, never "fail"


def test_foreign_qualifications_keep_level_and_need_verification() -> None:
    found = index().match(
        "BSc in Statistics (Bachelor)",
        institution="University of Pretoria",
        context="BSc in Statistics (Bachelor), University of Pretoria, South Africa, 2019",
    )
    assert found.level is not None and found.level.code == "BACHELOR"
    assert found.foreign and found.needs_verification


def test_field_and_professional_body() -> None:
    found = index().match("Diploma in Personnel Management (IPMZ)")
    assert found.field == "Personnel Management" and found.body == "IPMZ"
    assert index().match("ACCA finalist").body == "ACCA"


@pytest.mark.parametrize(
    ("raw", "title", "seniority"),
    [
        ("Senior Software Engineer", "software developer", "senior"),
        ("Sr. Backend Dev", "software developer", "senior"),
        ("Junior Data Analyst", "data analyst", "junior"),
        ("Business Intelligence Analyst", "data analyst", None),
        ("HR Officer", "human resources officer", None),
        ("Personnel Officer", "human resources officer", None),
        ("Senior Nursing Sister", "registered nurse", "senior"),
        ("RGN", "registered nurse", None),
        ("Part-time Registered Nurse (weekends)", "registered nurse", None),
        ("Assistant Accountant", "assistant accountant", "junior"),
        ("Industrial Attachment Student", "industrial attachment student", "intern"),
        ("Head of Finance", "head of finance", "head"),
        ("Software Developer II", "software developer", None),
        ("Développeur", "developpeur", None),
    ],
)
def test_titles(raw: str, title: str, seniority: str | None) -> None:
    norm = normalise_title(raw)
    assert (norm.title, norm.seniority) == (title, seniority)


@pytest.mark.skipif(not CORPUS.exists(), reason="synthetic corpus missing")
def test_corpus_education_levels() -> None:
    """docs/09 §5: education level mapping accuracy >= 0.90 (here: every labelled entry)."""
    labels = json.loads((CORPUS / "labels.json").read_text(encoding="utf-8"))["cvs"]
    total = correct = 0
    for cv in labels:
        if cv["parse_expected"] != "ok" or cv["needs_ocr"]:
            continue
        result = extract_claims(
            extract_document((CORPUS / cv["file"]).read_bytes(), document_id=cv["id"]),
            today=(2026, 10),
        )
        result = normalise_experience(normalise_education(result, index()))
        education = {
            c.data.qualification_text: c.data for c in result.claims if c.claim_type == "education"
        }
        for entry in cv["education"]:
            got = education.get(entry["qualification"])
            assert got is not None, entry
            total += 1
            if entry["foreign"]:
                correct += got.foreign and got.needs_verification
            else:
                correct += got.level == LABEL_LEVELS[entry["level"]] and not got.needs_verification
        for claim in result.claims:
            if claim.claim_type == "experience" and claim.data.title:
                assert claim.data.title_normalised
    assert correct == total
