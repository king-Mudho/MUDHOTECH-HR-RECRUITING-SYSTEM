"""PDF text extraction (docs/05 §3.1, §3.4).

PyMuPDF ``get_text("dict")`` gives spans with font size, colour and coordinates. Text is read
without clipping to the media box so off-page text is seen; spans that are near-white, smaller
than 4 pt or outside the page are split into *hidden* blocks (stored, flagged ``hidden_text``,
never evaluated - EC-DOC-13). pdfplumber is the fallback when PyMuPDF cannot parse the file.
Neither engine runs JavaScript or opens embedded files.
"""

from __future__ import annotations

import io
from typing import Any

import pymupdf

from ai_engine.contracts import Page
from ai_engine.extraction.guards import ExtractionError, Flag, Limits
from ai_engine.extraction.layout import RawBlock, build_page

MIN_VISIBLE_PT = 4.0
WHITE_LUMINANCE = 0.92
BOLD_FLAG = 16  # PyMuPDF span flag bit

# Keep ligatures etc. out (we NFKC anyway) and do not clip to the media box (off-page text).
_TEXT_FLAGS = (
    pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES & ~pymupdf.TEXT_MEDIABOX_CLIP
) | pymupdf.TEXT_PRESERVE_WHITESPACE

pymupdf.TOOLS.mupdf_display_errors(False)
pymupdf.TOOLS.mupdf_display_warnings(False)


def _luminance(srgb: int) -> float:
    r, g, b = (srgb >> 16) & 255, (srgb >> 8) & 255, srgb & 255
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def span_hidden(span: dict[str, Any], page_rect: pymupdf.Rect) -> bool:
    if not span["text"].strip():
        return False
    if span["size"] < MIN_VISIBLE_PT:
        return True
    if _luminance(int(span.get("color", 0))) >= WHITE_LUMINANCE:
        return True
    x0, y0, x1, y1 = span["bbox"]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return not (page_rect.x0 <= cx <= page_rect.x1 and page_rect.y0 <= cy <= page_rect.y1)


def _page_blocks(page: pymupdf.Page) -> list[RawBlock]:
    rect = page.rect
    out: list[RawBlock] = []
    data = page.get_text("dict", flags=_TEXT_FLAGS, clip=pymupdf.INFINITE_RECT())
    for block in data["blocks"]:
        if block.get("type") != 0:
            continue
        lines: dict[bool, list[str]] = {False: [], True: []}
        sizes: dict[bool, list[float]] = {False: [], True: []}
        bold: dict[bool, int] = {False: 0, True: 0}
        chars: dict[bool, int] = {False: 0, True: 0}
        for line in block["lines"]:
            parts: dict[bool, list[str]] = {False: [], True: []}
            for span in line["spans"]:
                hidden = span_hidden(span, rect)
                parts[hidden].append(span["text"])
                n = len(span["text"].strip())
                if n:
                    sizes[hidden].append(span["size"])
                    chars[hidden] += n
                    if span["flags"] & BOLD_FLAG:
                        bold[hidden] += n
            for hidden in (False, True):
                if "".join(parts[hidden]).strip():
                    lines[hidden].append("".join(parts[hidden]))
        for hidden in (False, True):
            if not lines[hidden]:
                continue
            out.append(
                RawBlock(
                    text="\n".join(lines[hidden]),
                    bbox=tuple(block["bbox"]),
                    font_size=max(sizes[hidden]) if sizes[hidden] else None,
                    bold=bold[hidden] * 2 > chars[hidden],
                    hidden=hidden,
                )
            )
    return out


def _open(data: bytes, limits: Limits) -> pymupdf.Document:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # any parser failure means "cannot read"
        raise ExtractionError("corrupt", Flag.CORRUPT, "PyMuPDF could not open the file") from exc
    if doc.needs_pass:
        doc.close()
        raise ExtractionError("encrypted_pdf", Flag.ENCRYPTED_PDF, "password-protected PDF")
    if doc.page_count == 0:
        doc.close()
        raise ExtractionError("corrupt", Flag.CORRUPT, "no pages")
    if doc.page_count > limits.max_pages:
        doc.close()
        raise ExtractionError("too_many_pages", Flag.TOO_MANY_PAGES, "too many pages")
    return doc


def extract_pymupdf(data: bytes, limits: Limits) -> tuple[list[Page], bool]:
    """Pages, and whether MuPDF had to repair a damaged file."""
    doc = _open(data, limits)
    try:
        pages: list[Page] = []
        for index in range(1, doc.page_count + 1):
            page = doc[index - 1]
            raw = _page_blocks(page)
            pages.append(
                build_page(
                    index,
                    raw,
                    width=page.rect.width,
                    height=page.rect.height,
                    image_only=bool(page.get_images(full=False)),
                )
            )
        return pages, bool(doc.is_repaired)
    finally:
        doc.close()


def extract_pdfplumber(data: bytes, limits: Limits) -> list[Page]:
    """Fallback: plain text per page (no colour/size based hidden-text detection)."""
    import pdfplumber
    from pdfminer.pdfdocument import PDFPasswordIncorrect

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages) > limits.max_pages:
                raise ExtractionError("too_many_pages", Flag.TOO_MANY_PAGES)
            pages = []
            for index, page in enumerate(pdf.pages, start=1):
                width, height = float(page.width), float(page.height)
                inside = page.within_bbox((0, 0, width, height), strict=False)
                text = inside.extract_text(layout=False) or ""
                raw = [RawBlock(text=text)] if text.strip() else []
                pages.append(
                    build_page(
                        index,
                        raw,
                        width=width,
                        height=height,
                        image_only=bool(page.images),
                        order=False,
                    )
                )
            return pages
    except ExtractionError:
        raise
    except PDFPasswordIncorrect as exc:
        raise ExtractionError("encrypted_pdf", Flag.ENCRYPTED_PDF) from exc
    except Exception as exc:  # parser failure
        raise ExtractionError(
            "corrupt", Flag.CORRUPT, "pdfplumber could not read the file"
        ) from exc


def extract_pdf(data: bytes, limits: Limits) -> tuple[list[Page], str, bool]:
    """(pages, parser, degraded). Encryption/page limits are final; parse errors fall back."""
    try:
        pages, repaired = extract_pymupdf(data, limits)
    except ExtractionError as exc:
        if exc.code != "corrupt":
            raise
        return extract_pdfplumber(data, limits), "pdfplumber", True
    if repaired and not any(p.text.strip() for p in pages):
        raise ExtractionError("corrupt", Flag.CORRUPT, "damaged PDF with no readable text")
    return pages, "pymupdf", repaired
