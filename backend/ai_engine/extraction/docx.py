"""DOCX text extraction (docs/05 §3.2).

Walks the document XML in body order: paragraphs, tables (row-wise, cells joined by `` | ``) and
text boxes (``w:txbxContent``; the VML fallback copy is skipped), plus headers and footers where
contact details often live (EC-DOC-10). Runs that are vanished, near-white or smaller than 4 pt
become hidden blocks (EC-DOC-13). DOCX has no fixed pagination, so everything is page 1.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from typing import Any

import docx
from docx.oxml.ns import qn

from ai_engine.contracts import BlockKind, Page
from ai_engine.extraction.guards import ExtractionError, Flag, Limits, check_docx
from ai_engine.extraction.layout import RawBlock, build_page

MIN_VISIBLE_HALF_POINTS = 8  # 4 pt
WHITE_LUMINANCE = 0.92

W_P, W_TBL, W_R, W_T = qn("w:p"), qn("w:tbl"), qn("w:r"), qn("w:t")
W_TAB, W_BR, W_CR = qn("w:tab"), qn("w:br"), qn("w:cr")
W_HYPERLINK, W_SDT, W_SDT_CONTENT, W_INS = (
    qn("w:hyperlink"),
    qn("w:sdt"),
    qn("w:sdtContent"),
    qn("w:ins"),
)
W_TXBX = qn("w:txbxContent")
W_VAL = qn("w:val")
MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"


def _on(el: Any) -> bool:
    return el is not None and el.get(W_VAL) not in ("0", "false", "off")


def _run_hidden(run: Any) -> bool:
    rpr = run.find(qn("w:rPr"))
    if rpr is None:
        return False
    if _on(rpr.find(qn("w:vanish"))) or _on(rpr.find(qn("w:specVanish"))):
        return True
    size = rpr.find(qn("w:sz"))
    size_val = size.get(W_VAL) or "" if size is not None else ""
    if size_val.isdigit() and int(size_val) < MIN_VISIBLE_HALF_POINTS:
        return True
    color = rpr.find(qn("w:color"))
    value = (color.get(W_VAL) or "") if color is not None else ""
    if len(value) == 6:
        try:
            r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
        except ValueError:
            return False
        return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 >= WHITE_LUMINANCE
    return False


def _run_text(run: Any) -> str:
    out = []
    for child in run:
        if child.tag == W_T:
            out.append(child.text or "")
        elif child.tag == W_TAB:
            out.append(" ")
        elif child.tag in (W_BR, W_CR):
            out.append("\n")
    return "".join(out)


def _runs(p: Any) -> Iterator[Any]:
    """Direct runs of a paragraph, incl. those in hyperlinks, content controls and insertions."""
    for child in p:
        if child.tag == W_R:
            yield child
        elif child.tag in (W_HYPERLINK, W_INS):
            yield from (r for r in child if r.tag == W_R)
        elif child.tag == W_SDT:
            content = child.find(W_SDT_CONTENT)
            if content is not None:
                yield from (r for r in content.iter(W_R))


def _paragraph(p: Any) -> tuple[str, str, int | None]:
    visible: list[str] = []
    hidden: list[str] = []
    size: int | None = None
    for run in _runs(p):
        text = _run_text(run)
        if not text:
            continue
        (hidden if _run_hidden(run) else visible).append(text)
        sz = run.find(f"{qn('w:rPr')}/{qn('w:sz')}")
        if sz is not None and (sz.get(W_VAL) or "").isdigit():
            size = max(size or 0, int(sz.get(W_VAL)))
    return "".join(visible), "".join(hidden), size


def _style_is_heading(p: Any) -> bool:
    style = p.find(f"{qn('w:pPr')}/{qn('w:pStyle')}")
    name = (style.get(W_VAL) or "").lower() if style is not None else ""
    return name.startswith(("heading", "title"))


def _textboxes(p: Any) -> Iterator[Any]:
    for box in p.iter(W_TXBX):
        if any(a.tag == MC_FALLBACK for a in box.iterancestors()):
            continue  # VML duplicate of the DrawingML text box
        yield box


def _walk(container: Any, kind: BlockKind) -> Iterator[RawBlock]:
    for el in container:
        if el.tag == W_P:
            visible, hidden, size = _paragraph(el)
            heading = _style_is_heading(el)
            if visible.strip():
                yield RawBlock(
                    text=visible,
                    kind=kind,
                    bold=heading,
                    font_size=size / 2 if size else None,
                )
            if hidden.strip():
                yield RawBlock(text=hidden, kind=kind, hidden=True)
            for box in _textboxes(el):
                yield from _walk(box, BlockKind.TEXTBOX)
        elif el.tag == W_TBL:
            yield from _table(el, kind)
        elif el.tag == W_SDT:
            content = el.find(W_SDT_CONTENT)
            if content is not None:
                yield from _walk(content, kind)


def _table(tbl: Any, kind: BlockKind) -> Iterator[RawBlock]:
    rows: list[str] = []
    hidden_rows: list[str] = []
    for tr in tbl.iter(qn("w:tr")):
        cells: list[str] = []
        hidden_cells: list[str] = []
        for tc in tr.findall(qn("w:tc")):
            texts, hiddens = [], []
            for p in tc.iter(W_P):
                visible, hidden, _ = _paragraph(p)
                if visible.strip():
                    texts.append(visible.strip())
                if hidden.strip():
                    hiddens.append(hidden.strip())
            cell = " ".join(texts)
            if cell and (not cells or cells[-1] != cell):  # merged cells repeat their text
                cells.append(cell)
            if hiddens:
                hidden_cells.append(" ".join(hiddens))
        if cells:
            rows.append(" | ".join(cells))
        if hidden_cells:
            hidden_rows.append(" ".join(hidden_cells))
    if rows:
        yield RawBlock(
            text="\n".join(rows), kind=BlockKind.TABLE if kind == BlockKind.TEXT else kind
        )
    if hidden_rows:
        yield RawBlock(text="\n".join(hidden_rows), kind=kind, hidden=True)


def _header_footer_blocks(document: Any) -> tuple[list[RawBlock], list[RawBlock]]:
    headers: list[RawBlock] = []
    footers: list[RawBlock] = []
    seen: set[tuple[BlockKind, str]] = set()
    for section in document.sections:
        parts = [
            (section.header, BlockKind.HEADER, headers),
            (section.first_page_header, BlockKind.HEADER, headers),
            (section.even_page_header, BlockKind.HEADER, headers),
            (section.footer, BlockKind.FOOTER, footers),
            (section.first_page_footer, BlockKind.FOOTER, footers),
            (section.even_page_footer, BlockKind.FOOTER, footers),
        ]
        for part, kind, target in parts:
            if part.is_linked_to_previous:
                continue
            for block in _walk(part._element, kind):
                key = (kind, block.text.strip())
                if key not in seen:
                    seen.add(key)
                    target.append(block)
    return headers, footers


def extract_docx(data: bytes, limits: Limits) -> list[Page]:
    check_docx(data, limits)
    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:  # malformed XML / missing parts
        raise ExtractionError(
            "corrupt", Flag.CORRUPT, "python-docx could not read the file"
        ) from exc
    headers, footers = _header_footer_blocks(document)
    body = list(_walk(document.element.body, BlockKind.TEXT))
    images = bool(document.inline_shapes) or any(
        "image" in rel.reltype for rel in document.part.rels.values()
    )
    page = build_page(1, headers + body + footers, image_only=images, order=False)
    return [page]
