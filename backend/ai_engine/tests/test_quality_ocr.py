"""OCR trigger/parsing and text quality (P06-T04): EC-DOC-01, -11, -12, -28."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pymupdf
import pytest

from ai_engine.contracts import Block, ExtractionStatus, Flag, Page
from ai_engine.extraction import extract as extract_module
from ai_engine.extraction import ocr
from ai_engine.extraction.extract import extract_document
from ai_engine.extraction.quality import (
    assess,
    detect_language,
    heading_language,
    is_garbled,
    possibly_not_cv,
)

CORPUS = Path(__file__).resolve().parents[2] / "fixtures" / "synthetic_cvs"
HAS_TESSERACT = ocr.tesseract_path() is not None

CV_TEXT = """Profile
Accountant with five years of experience in financial reporting and audit for mining firms.

Experience
Finance Officer | Great Dyke Mining, Mutare | 2021 - 2024
- Prepared month-end reconciliations and management accounts for the finance manager
- Supported the external audit with schedules, explanations and fixed asset registers

Education
Bachelor of Accountancy Honours, University of Zimbabwe, 2020

Skills
Pastel, Sage, Excel, IFRS, payroll, budgeting, tax returns and statutory reporting

References
Available on request"""


def page(text: str, **kw: Any) -> Page:
    return Page(number=1, text=text, blocks=(Block(text=text),) if text else (), **kw)


# ---------------------------------------------------------------------- OCR trigger
def test_ocr_trigger_rules() -> None:
    assert ocr.needs_ocr([page("short")])  # < 200 chars per page
    assert not ocr.needs_ocr([page(CV_TEXT)])
    half_scanned = [page(CV_TEXT * 2), Page(number=2, image_only=True)]
    assert ocr.needs_ocr(half_scanned)  # >= 50% image-only pages
    assert ocr.needs_ocr([page(CV_TEXT)], garbled=True)
    assert not ocr.needs_ocr([])
    hidden_only = Page(number=1, text="x" * 500, blocks=(Block(text="x" * 500, hidden=True),))
    assert ocr.needs_ocr([hidden_only])  # hidden text does not count as content


def test_parse_tesseract_tsv() -> None:
    columns = [
        "level",
        "page_num",
        "block_num",
        "par_num",
        "line_num",
        "word_num",
        "left",
        "top",
        "width",
        "height",
        "conf",
        "text",
    ]
    header = chr(9).join(columns)
    rows = [
        "1\t1\t0\t0\t0\t0\t0\t0\t100\t100\t-1\t",
        "5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t96.5\tSkills",
        "5\t1\t1\t1\t2\t1\t0\t0\t10\t10\t90\tPython,",
        "5\t1\t1\t1\t2\t2\t0\t0\t10\t10\t80\tSQL",
        "5\t1\t2\t1\t1\t1\t0\t0\t10\t10\t40\tHarare",
        "5\t1\t2\t1\t1\t2\t0\t0\t10\t10\t-1\t ",
    ]
    result = ocr.parse_tsv("\n".join([header, *rows]))
    assert result.text == "Skills\nPython, SQL\n\nHarare"
    assert result.confidence == pytest.approx((96.5 + 90 + 80 + 40) / 4, abs=0.1)
    assert ocr.parse_tsv(header).confidence == 0.0


def _scanned_pdf(text: str) -> bytes:
    """Render text, rasterise it, and build an image-only PDF (like a phone scan)."""
    src = pymupdf.open()
    p = src.new_page(width=595, height=842)
    p.insert_textbox(pymupdf.Rect(50, 50, 545, 800), text, fontsize=12)
    pix = p.get_pixmap(dpi=150)
    out = pymupdf.open()
    out.new_page(width=595, height=842).insert_image(pymupdf.Rect(0, 0, 595, 842), pixmap=pix)
    return out.tobytes()


def test_ocr_unavailable_keeps_the_document_and_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extract_module, "tesseract_path", lambda: None)
    result = extract_document(_scanned_pdf(CV_TEXT), document_id="d")
    assert result.status == ExtractionStatus.PARTIAL
    assert {Flag.OCR_UNAVAILABLE, Flag.POSSIBLY_NOT_CV} <= result.flags
    assert result.document.pages[0].image_only


def test_ocr_replaces_image_pages_and_records_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_ocr(png: bytes, binary: str, language: str = "eng") -> ocr.OcrPage:
        calls.append(len(png))
        return ocr.OcrPage(text=CV_TEXT, confidence=62.0)

    monkeypatch.setattr(extract_module, "tesseract_path", lambda: "/usr/bin/tesseract")
    monkeypatch.setattr(ocr, "ocr_png", fake_ocr)
    result = extract_document(_scanned_pdf(CV_TEXT), document_id="d")
    assert calls and result.status == ExtractionStatus.SUCCEEDED
    doc = result.document
    assert doc.parser_used == "pymupdf+tesseract"
    page1 = doc.pages[0]
    assert page1.ocr and page1.ocr_confidence == 62.0 and "Great Dyke Mining" in page1.text
    assert page1.blocks[0].kind == "ocr"
    assert {Flag.OCR_USED, Flag.LOW_OCR_CONFIDENCE} <= result.flags
    assert Flag.POSSIBLY_NOT_CV not in result.flags
    assert "ocr" in result.timings_ms


def test_ocr_is_skipped_for_good_text_and_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: Any, **k: Any) -> Any:
        raise AssertionError("OCR must not run")

    monkeypatch.setattr(ocr, "ocr_png", boom)
    good = pymupdf.open()
    good.new_page().insert_textbox(pymupdf.Rect(50, 50, 545, 800), CV_TEXT, fontsize=10)
    assert extract_document(good.tobytes(), document_id="d").status == ExtractionStatus.SUCCEEDED
    assert extract_document(_scanned_pdf(CV_TEXT), document_id="d", ocr=False).status == "succeeded"


@pytest.mark.skipif(not HAS_TESSERACT, reason="tesseract not installed")
def test_real_tesseract_reads_a_scan() -> None:
    result = extract_document(_scanned_pdf(CV_TEXT), document_id="d")
    page1 = result.document.pages[0]
    assert page1.ocr and (page1.ocr_confidence or 0) > 70
    assert "Great Dyke" in page1.text and "Accountancy" in page1.text
    assert Flag.OCR_USED in result.flags and Flag.POSSIBLY_NOT_CV not in result.flags


# --------------------------------------------------------------------------- quality
def test_garbled_text_detection() -> None:
    assert not is_garbled(CV_TEXT)
    assert is_garbled("(cid:12)(cid:44)(cid:3) " * 20 + CV_TEXT[:100])
    assert is_garbled("�� text " * 40)
    assert is_garbled(" ".join(["xq7#Lp", "Zt%9k", "pQ@r2"] * 20))
    assert not is_garbled("")


def test_language_detection() -> None:
    assert detect_language(CV_TEXT) == "en"
    assert detect_language("short") is None
    french = (
        "Développeur logiciel motivé avec cinq ans d'expérience dans la conception d'applications "
        "web pour des entreprises de télécommunications. J'ai dirigé une équipe de quatre "
        "personnes et amélioré les temps de réponse des services grâce à la mise en cache."
    )
    assert detect_language(french) == "fr"
    assert heading_language("Profil\nx\nExpérience professionnelle\ny\nFormation\nz") == "fr"
    assert heading_language(CV_TEXT) is None


def test_not_a_cv_rules() -> None:
    certificate = (
        "This is to certify that Tendai Moyo has successfully completed the course in Project "
        "Management at the Institute.\nSkills\nDate of issue: 12 March 2024"
    )
    assert possibly_not_cv(certificate, words=25, headings=1)
    assert possibly_not_cv("National Registration\nIdentity card", words=4, headings=0)
    assert not possibly_not_cv(CV_TEXT, words=90, headings=5)
    assert not possibly_not_cv("Experience\nDriver\nEducation\nZIMSEC O Level", words=6, headings=2)


def test_assess_scores_and_flags() -> None:
    good = assess([page(CV_TEXT)])
    assert good.language == "en" and good.flags == frozenset() and good.score >= 0.6
    blank = assess([Page(number=1, image_only=True)])
    assert Flag.POSSIBLY_NOT_CV in blank.flags and blank.score < 0.2
    garbled = assess([page("(cid:3)(cid:4) " * 200)])
    assert Flag.GARBLED_TEXT in garbled.flags and garbled.score <= 0.3
    low = assess([page(CV_TEXT, ocr=True, ocr_confidence=55)])
    assert Flag.LOW_OCR_CONFIDENCE in low.flags and low.score < good.score


@pytest.mark.skipif(not CORPUS.exists(), reason="synthetic corpus missing")
def test_corpus_quality_flags_match_labels() -> None:
    labels = json.loads((CORPUS / "labels.json").read_text(encoding="utf-8"))["cvs"]
    problems = []
    for cv in labels:
        if cv["parse_expected"] != "ok":
            continue
        result = extract_document((CORPUS / cv["file"]).read_bytes(), document_id=cv["id"])
        flags = result.flags
        if cv["needs_ocr"]:
            if HAS_TESSERACT and Flag.OCR_USED not in flags:
                problems.append((cv["file"], "no OCR"))
            continue
        if (cv["language"] != "en") != (Flag.LANGUAGE_UNSUPPORTED in flags):
            problems.append((cv["file"], "language", result.document.language))
        if {Flag.POSSIBLY_NOT_CV, Flag.GARBLED_TEXT} & flags:
            problems.append((cv["file"], sorted(flags)))
        if (result.document.quality_score or 0) < 0.5:
            problems.append((cv["file"], "quality", result.document.quality_score))
    assert problems == []
