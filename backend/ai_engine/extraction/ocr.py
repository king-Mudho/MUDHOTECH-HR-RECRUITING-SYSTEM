"""OCR fallback (docs/05 §3.3, EC-DOC-01, EC-DOC-28).

Triggered when a PDF has too little text (< 200 chars/page), when at least half its pages are
image-only, or when the text layer is garbled (CID fonts). Pages are rendered at 300 DPI and read
by the Tesseract CLI (``--psm 3``, TSV output) so each page gets a mean word confidence; pages
under 70 raise ``low_ocr_confidence``. If Tesseract is not installed the pages are left as they
are and the caller sees ``ocr_unavailable``.
"""

from __future__ import annotations

import csv
import io
import shutil
import subprocess  # nosec B404 - fixed argv, no shell
from dataclasses import dataclass

import pymupdf

from ai_engine.contracts import BlockKind, Page
from ai_engine.extraction.layout import RawBlock, build_page

MIN_CHARS_PER_PAGE = 200
IMAGE_ONLY_SHARE = 0.5
LOW_CONFIDENCE = 70.0
DPI = 300
PAGE_TIMEOUT_SECONDS = 45


def tesseract_path() -> str | None:
    return shutil.which("tesseract")


def needs_ocr(pages: list[Page], *, garbled: bool = False) -> bool:
    if not pages:
        return False
    if garbled:
        return True
    visible = sum(len(b.text) for p in pages for b in p.blocks if not b.hidden)
    image_only = sum(1 for p in pages if p.image_only)
    return visible / len(pages) < MIN_CHARS_PER_PAGE or image_only / len(pages) >= IMAGE_ONLY_SHARE


@dataclass(frozen=True)
class OcrPage:
    text: str
    confidence: float  # mean word confidence 0-100 (0 when nothing was recognised)


def parse_tsv(tsv: str) -> OcrPage:
    """Rebuild lines from Tesseract TSV (level 5 = word) and average the word confidences."""
    lines: dict[tuple[int, int, int], list[str]] = {}
    confidences: list[float] = []
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        if row.get("level") != "5":
            continue
        word = (row.get("text") or "").strip()
        try:
            conf = float(row.get("conf") or -1)
        except ValueError:
            conf = -1
        if not word or conf < 0:
            continue
        key = (int(row["block_num"]), int(row["par_num"]), int(row["line_num"]))
        lines.setdefault(key, []).append(word)
        confidences.append(conf)
    text_lines: list[str] = []
    previous_block: tuple[int, int] | None = None
    for key in sorted(lines):
        if previous_block is not None and key[:2] != previous_block:
            text_lines.append("")
        text_lines.append(" ".join(lines[key]))
        previous_block = key[:2]
    mean = sum(confidences) / len(confidences) if confidences else 0.0
    return OcrPage(text="\n".join(text_lines), confidence=round(mean, 1))


def ocr_png(png: bytes, binary: str, language: str = "eng") -> OcrPage:
    proc = subprocess.run(  # noqa: S603  # nosec B603 - fixed argv
        [binary, "stdin", "stdout", "-l", language, "--psm", "3", "--dpi", str(DPI), "tsv"],
        input=png,
        capture_output=True,
        timeout=PAGE_TIMEOUT_SECONDS,
        check=False,
    )
    if proc.returncode != 0:
        return OcrPage(text="", confidence=0.0)
    return parse_tsv(proc.stdout.decode("utf-8", errors="replace"))


def ocr_pdf(data: bytes, pages: list[Page], binary: str) -> list[Page]:
    """Replace each page's text with OCR output, keeping any hidden blocks for the audit trail."""
    out: list[Page] = []
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        for page in pages:
            pix = doc[page.number - 1].get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY, alpha=False)
            result = ocr_png(pix.tobytes("png"), binary)
            raw = [RawBlock(text=result.text, kind=BlockKind.OCR)] if result.text.strip() else []
            raw += [
                RawBlock(text=b.text, kind=b.kind, font_size=b.font_size, hidden=True)
                for b in page.blocks
                if b.hidden
            ]
            rebuilt = build_page(
                page.number, raw, width=page.width, height=page.height, order=False
            )
            out.append(
                rebuilt.model_copy(
                    update={
                        "ocr": True,
                        "ocr_confidence": result.confidence,
                        "image_only": page.image_only,
                    }
                )
            )
    finally:
        doc.close()
    return out
