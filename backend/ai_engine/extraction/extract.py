"""Extraction entry point: bytes in, :class:`ExtractionResult` out; never raises for bad input."""

from __future__ import annotations

import hashlib
import time

from ai_engine.contracts import DocumentText, ExtractionResult, ExtractionStatus, Flag
from ai_engine.extraction.guards import (
    DOCX_MIME,
    PDF_MIME,
    ExtractionError,
    Limits,
    check_size,
    sniff,
)


def failed(code: str, flag: Flag, started: float | None = None) -> ExtractionResult:
    timings = {"extract": round((time.perf_counter() - started) * 1000, 1)} if started else {}
    return ExtractionResult(
        status=ExtractionStatus.FAILED, error_code=code, flags=frozenset({flag}), timings_ms=timings
    )


def extract_document(
    data: bytes, *, document_id: str, limits: Limits | None = None
) -> ExtractionResult:
    """Extract page text from a PDF or DOCX. Failures come back as ``status=failed`` results."""
    from ai_engine.extraction.docx import extract_docx
    from ai_engine.extraction.pdf import extract_pdf

    limits = limits or Limits()
    started = time.perf_counter()
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
    flags: set[Flag] = set()
    if any(b.hidden for p in pages for b in p.blocks):
        flags.add(Flag.HIDDEN_TEXT)
    document = DocumentText(
        document_id=document_id,
        sha256=hashlib.sha256(data).hexdigest(),
        mime=mime if mime in (PDF_MIME, DOCX_MIME) else "application/octet-stream",
        parser_used=parser,
        pages=tuple(pages),
        flags=frozenset(flags),
    )
    return ExtractionResult(
        status=ExtractionStatus.PARTIAL if degraded else ExtractionStatus.SUCCEEDED,
        document=document,
        flags=frozenset(flags),
        timings_ms={"extract": round((time.perf_counter() - started) * 1000, 1)},
    )
