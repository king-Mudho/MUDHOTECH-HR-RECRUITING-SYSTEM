"""Extraction entry point: bytes in, :class:`ExtractionResult` out; never raises for bad input."""

from __future__ import annotations

import hashlib
import time

from ai_engine.contracts import DocumentText, ExtractionResult, ExtractionStatus, Flag, Page
from ai_engine.extraction.guards import (
    DOCX_MIME,
    PDF_MIME,
    ExtractionError,
    Limits,
    check_size,
    sniff,
)
from ai_engine.extraction.ocr import needs_ocr, ocr_pdf, tesseract_path
from ai_engine.extraction.quality import assess
from ai_engine.extraction.sections import detect_sections


def failed(code: str, flag: Flag, started: float | None = None) -> ExtractionResult:
    timings = {"extract": round((time.perf_counter() - started) * 1000, 1)} if started else {}
    return ExtractionResult(
        status=ExtractionStatus.FAILED, error_code=code, flags=frozenset({flag}), timings_ms=timings
    )


def _with_ocr(data: bytes, pages: list[Page], flags: set[Flag]) -> tuple[list[Page], bool]:
    """Run OCR over every page; keep the original page when OCR finds nothing on it."""
    binary = tesseract_path()
    if binary is None:
        flags.add(Flag.OCR_UNAVAILABLE)
        return pages, False
    ocr_pages = ocr_pdf(data, pages, binary)
    merged = [
        new
        if any(not b.hidden for b in new.blocks) or not any(not b.hidden for b in old.blocks)
        else old
        for old, new in zip(pages, ocr_pages, strict=True)
    ]
    used = any(p.ocr for p in merged)
    if used:
        flags.add(Flag.OCR_USED)
    return merged, used


def extract_document(
    data: bytes, *, document_id: str, limits: Limits | None = None, ocr: bool = True
) -> ExtractionResult:
    """Extract page text from a PDF or DOCX, with OCR and quality checks.

    Failures come back as ``status=failed`` results; nothing here raises for bad input.
    """
    from ai_engine.extraction.docx import extract_docx
    from ai_engine.extraction.pdf import extract_pdf

    limits = limits or Limits()
    started = time.perf_counter()
    timings: dict[str, float] = {}
    try:
        check_size(data, limits)
        mime = sniff(data)
        degraded = False
        if mime == PDF_MIME:
            pages, parser, degraded = extract_pdf(data, limits)
        else:
            pages, parser = extract_docx(data, limits), "python-docx"
    except ExtractionError as exc:
        return failed(exc.code, exc.flag, started)
    timings["extract"] = round((time.perf_counter() - started) * 1000, 1)

    flags: set[Flag] = set()
    if any(b.hidden for p in pages for b in p.blocks):
        flags.add(Flag.HIDDEN_TEXT)
    quality = assess(pages)
    if ocr and mime == PDF_MIME and needs_ocr(pages, garbled=quality.garbled):
        ocr_started = time.perf_counter()
        pages, used = _with_ocr(data, pages, flags)
        timings["ocr"] = round((time.perf_counter() - ocr_started) * 1000, 1)
        if used:
            parser = f"{parser}+tesseract"
            if quality.garbled:
                flags.add(Flag.GARBLED_TEXT)  # keep the reason OCR ran
            quality = assess(pages)
        else:
            degraded = True
    flags |= quality.flags
    document = DocumentText(
        document_id=document_id,
        sha256=hashlib.sha256(data).hexdigest(),
        mime=mime if mime in (PDF_MIME, DOCX_MIME) else "application/octet-stream",
        parser_used=parser,
        pages=tuple(pages),
        language=quality.language,
        quality_score=quality.score,
        flags=frozenset(flags),
    )
    timings["total"] = round((time.perf_counter() - started) * 1000, 1)
    return ExtractionResult(
        status=ExtractionStatus.PARTIAL if degraded else ExtractionStatus.SUCCEEDED,
        document=document,
        sections=tuple(detect_sections(pages)),
        flags=frozenset(flags),
        timings_ms=timings,
    )
