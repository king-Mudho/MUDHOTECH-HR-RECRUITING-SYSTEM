"""Reading order and page assembly shared by the extractors.

Raw blocks come from a parser with coordinates; :func:`reading_order` handles two-column layouts
(EC-DOC-09) by finding a vertical gutter that no narrow block crosses, then reading each band
between full-width blocks left column first. :func:`build_page` normalises block text and lays the
page text out as visible blocks in reading order followed by hidden blocks, so every block's
``char_start`` is an offset into ``Page.text`` and later stages can exclude hidden ranges.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_engine.contracts import BBox, Block, BlockKind, Page
from ai_engine.extraction.normalise import normalise_text

BLOCK_SEPARATOR = "\n\n"


@dataclass
class RawBlock:
    text: str
    kind: BlockKind = BlockKind.TEXT
    bbox: tuple[float, float, float, float] | None = None
    font_size: float | None = None
    bold: bool = False
    hidden: bool = False


def find_gutter(blocks: list[RawBlock], width: float) -> float | None:
    """x of a column gutter, or None for a single-column page."""
    boxed = [b.bbox for b in blocks if b.bbox is not None]
    narrow = [bb for bb in boxed if (bb[2] - bb[0]) < 0.55 * width]
    if len(narrow) < 4:
        return None
    lo, hi = 0.3 * width, 0.7 * width
    step = width / 200
    best: float | None = None
    best_gap = 0.0
    x = lo
    while x <= hi:
        if not any(bb[0] < x < bb[2] for bb in narrow):
            # widen to the free interval around x; a gutter needs text on both sides
            lefts = [bb[2] for bb in narrow if bb[2] <= x]
            rights = [bb[0] for bb in narrow if bb[0] >= x]
            if not lefts or not rights:
                x += step
                continue
            left, right = max(lefts), min(rights)
            if right - left > best_gap:
                best_gap, best = right - left, (left + right) / 2
        x += step
    if best is None:
        return None
    left_count = sum(1 for bb in narrow if bb[2] <= best)
    right_count = sum(1 for bb in narrow if bb[0] >= best)
    return best if left_count >= 2 and right_count >= 2 else None


def reading_order(blocks: list[RawBlock], width: float | None) -> list[RawBlock]:
    """Sort blocks top-to-bottom, column by column when the page has two columns."""
    unboxed = [b for b in blocks if b.bbox is None]
    boxed = [b for b in blocks if b.bbox is not None]

    def top(b: RawBlock) -> tuple[float, float]:
        bb = b.bbox or (0.0, 0.0, 0.0, 0.0)
        return (round(bb[1], 1), bb[0])

    boxed.sort(key=top)
    gutter = find_gutter(boxed, width) if width else None
    if gutter is None:
        return boxed + unboxed
    ordered: list[RawBlock] = []
    left: list[RawBlock] = []
    right: list[RawBlock] = []

    def flush() -> None:
        ordered.extend(left)
        ordered.extend(right)
        left.clear()
        right.clear()

    for b in boxed:
        bb = b.bbox or (0.0, 0.0, 0.0, 0.0)
        if bb[2] <= gutter:
            left.append(b)
        elif bb[0] >= gutter:
            right.append(b)
        else:  # spans both columns: a full-width heading/band boundary
            flush()
            ordered.append(b)
    flush()
    return ordered + unboxed


def build_page(
    number: int,
    raw: list[RawBlock],
    *,
    width: float | None = None,
    height: float | None = None,
    image_only: bool = False,
    order: bool = True,
) -> Page:
    visible = [b for b in raw if not b.hidden]
    hidden = [b for b in raw if b.hidden]
    if order:
        visible = reading_order(visible, width)
    parts: list[str] = []
    blocks: list[Block] = []
    offset = 0
    for b in visible + hidden:
        text = normalise_text(b.text)
        if not text:
            continue
        if parts:
            offset += len(BLOCK_SEPARATOR)
        blocks.append(
            Block(
                text=text,
                kind=b.kind,
                bbox=BBox(x0=b.bbox[0], y0=b.bbox[1], x1=b.bbox[2], y1=b.bbox[3])
                if b.bbox
                else None,
                font_size=round(b.font_size, 2) if b.font_size is not None else None,
                bold=b.bold,
                hidden=b.hidden,
                char_start=offset,
            )
        )
        parts.append(text)
        offset += len(text)
    return Page(
        number=number,
        text=BLOCK_SEPARATOR.join(parts),
        width=width,
        height=height,
        blocks=tuple(blocks),
        image_only=image_only and not any(not b.hidden for b in blocks),
    )


def hidden_ranges(page: Page) -> list[tuple[int, int]]:
    """Character ranges of ``page.text`` that belong to hidden blocks (never evaluated)."""
    return [(b.char_start, b.char_start + len(b.text)) for b in page.blocks if b.hidden]
