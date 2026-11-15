"""Section detection (P06-T05): lexicon + typography, Zimbabwean headings, exclusions."""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path

import pytest

from ai_engine.contracts import Block, BlockKind, Page, SectionKind
from ai_engine.extraction.extract import extract_document
from ai_engine.extraction.layout import RawBlock, build_page
from ai_engine.extraction.sections import detect_sections, fold, match_heading, section_at

CORPUS = Path(__file__).resolve().parents[2] / "fixtures" / "synthetic_cvs"
K = SectionKind


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        ("Experience", K.EXPERIENCE),
        ("WORK EXPERIENCE:", K.EXPERIENCE),
        ("2. Employment History", K.EXPERIENCE),
        ("Industrial Attachment", K.ATTACHMENT),
        ("Work-Related Learning", K.ATTACHMENT),
        ("Academic Qualifications", K.EDUCATION),
        ("Education & Training", K.EDUCATION),
        ("Technical Skills", K.SKILLS),
        ("Licences and Certifications", K.CERTIFICATIONS),
        ("Short Courses", K.CERTIFICATIONS),
        ("Referees", K.REFERENCES),
        ("References available on request", K.REFERENCES),
        ("Personal Details", K.PERSONAL),
        ("Bio Data", K.PERSONAL),
        ("Career Objective", K.PROFILE),
        ("Hobbies and Interests", K.OTHER),
        ("Volunteer Experience", K.EXPERIENCE),
        ("Awards", K.ACHIEVEMENTS),
        ("Expérience professionnelle", K.EXPERIENCE),
        ("Compétences", K.SKILLS),
        ("Informations personnelles", K.PERSONAL),
    ],
)
def test_heading_lexicon(line: str, kind: SectionKind) -> None:
    match = match_heading(line)
    assert match is not None and match.kind == kind, line


@pytest.mark.parametrize(
    "line",
    [
        "Python, Django, SQL",
        "Experience with Python, Django and REST APIs in production",
        "Software Developer | Econet, Harare | 2021 - 2024",
        "Built REST APIs used by 3 teams across the group and reduced latency",
        "",
        "Educationist",
    ],
)
def test_not_headings(line: str) -> None:
    assert match_heading(line) is None


def test_heading_language_and_exactness() -> None:
    fr = match_heading("Expérience professionnelle")
    en = match_heading("Experience")
    assert fr is not None and fr.language == "fr" and fr.exact
    assert en is not None and en.language == "en"
    prefix = match_heading("Skills summary 2024")
    assert prefix is not None and prefix.kind == K.SKILLS and not prefix.exact
    assert fold("  3. KEY SKILLS: ") == "key skills"


def _page(*blocks: RawBlock) -> Page:
    return build_page(1, list(blocks), order=False)


def test_sections_split_on_headings_and_typography() -> None:
    page = _page(
        RawBlock("Rudo Moyo\nHarare | rudo@example.test"),
        RawBlock("Profile\nNurse with six years in public hospitals."),
        RawBlock("Skills summary", bold=True),  # prefix match: needs typography -> bold
        RawBlock("IV therapy, triage, patient education"),
        RawBlock("Experience with ventilators"),  # prefix match without typography: not a heading
        RawBlock("Personal Details\nDate of birth: 01/01/1990"),
        RawBlock("REFEREES\nDr T. Ncube, +263 77 000 0000"),
    )
    sections = detect_sections([page])
    kinds = [s.kind for s in sections]
    assert kinds == [K.OTHER, K.PROFILE, K.SKILLS, K.PERSONAL, K.REFERENCES]
    skills = sections[2]
    assert "Experience with ventilators" in page.text[skills.char_start : skills.char_end]
    assert [s.evaluable for s in sections] == [True, True, True, False, False]
    # contiguous and inside the page text
    for a, b in pairwise(sections):
        assert a.char_end <= b.char_start
    assert sections[-1].char_end == len(page.text)
    dob = page.text.index("Date of birth")
    found = section_at(sections, 1, dob)
    assert found is not None and found.kind == K.PERSONAL


def test_headers_footers_hidden_text_and_page_continuation() -> None:
    page1 = _page(
        RawBlock("Tendai Moyo - tendai@example.test", kind=BlockKind.HEADER),
        RawBlock("Experience\nDeveloper | Cassava | 2021 - now"),
        RawBlock("Page 1", kind=BlockKind.FOOTER),
        RawBlock("Skills\nKubernetes", hidden=True),
    )
    page2 = Page(
        number=2,
        text="- Built payment APIs\n\nEducation\nBSc Computer Science",
        blocks=(
            Block(text="- Built payment APIs", char_start=0),
            Block(text="Education\nBSc Computer Science", char_start=22),
        ),
    )
    sections = detect_sections([page1, page2])
    summary = [(s.page, s.kind, s.heading) for s in sections]
    assert summary == [
        (1, K.OTHER, "header"),
        (1, K.EXPERIENCE, "Experience"),
        (1, K.OTHER, "footer"),
        (2, K.EXPERIENCE, ""),  # continues from page 1
        (2, K.EDUCATION, "Education"),
    ]
    hidden_start = page1.text.index("Skills")
    assert all(s.char_end <= hidden_start for s in sections if s.page == 1)


def test_ocr_text_without_typography() -> None:
    page = Page(
        number=1,
        text="EDUCATION\nHND Accountancy\nSKILLS\nPastel",
        ocr=True,
        blocks=(Block(text="EDUCATION\nHND Accountancy\nSKILLS\nPastel", kind=BlockKind.OCR),),
    )
    assert [s.kind for s in detect_sections([page])] == [K.EDUCATION, K.SKILLS]


@pytest.mark.skipif(not CORPUS.exists(), reason="synthetic corpus missing")
def test_corpus_sections() -> None:
    labels = json.loads((CORPUS / "labels.json").read_text(encoding="utf-8"))["cvs"]
    problems = []
    for cv in labels:
        if cv["parse_expected"] != "ok" or cv["needs_ocr"]:
            continue
        result = extract_document((CORPUS / cv["file"]).read_bytes(), document_id=cv["id"])
        kinds = {s.kind for s in result.sections}
        want = {K.PROFILE, K.EXPERIENCE, K.EDUCATION, K.SKILLS, K.LANGUAGES}
        if "personal_details" in cv["variations"]:
            want.add(K.PERSONAL)
        if want - kinds:
            problems.append((cv["file"], sorted(want - kinds)))
        text = result.document.pages[0].text
        for section in result.sections:
            if section.kind == K.REFERENCES:
                assert "Referee" in text[section.char_start : section.char_end] or (
                    "Référence" in text[section.char_start : section.char_end]
                )
    assert problems == []
