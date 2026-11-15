"""Text quality, language and "is this a CV?" checks (docs/05 §4, EC-DOC-11/12/28).

All rules are deterministic. Flags inform humans and route the application to manual review;
none of them lowers a score or rejects a candidate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ai_engine.contracts import Flag, Page
from ai_engine.extraction.sections import HeadingMatch, match_heading

GARBLED_SHARE = 0.05  # replacement / private-use / CID artefacts
MIN_WORDLIKE_SHARE = 0.5
MIN_WORDS_FOR_CV = 80
MIN_CHARS_FOR_LANGUAGE = 200

_CID = re.compile(r"\(cid:\d+\)")
_TOKEN = re.compile(r"\S+")
_WORDLIKE = re.compile(r"^[(\"'\[]?[A-Za-zÀ-ÿ][a-zà-ÿ'-]*[A-Za-zà-ÿ]?[.,;:!?)\]\"']*$")

NOT_CV_PATTERNS = re.compile(
    r"this is to certify|certificate of (completion|achievement|attendance|competence)|"
    r"has (successfully )?completed|is hereby awarded|national registration|identity card|"
    r"registrar[- ]general|republic of zimbabwe\s+passport|date of issue|place of birth|"
    r"statement of results|transcript of (academic )?records|invoice|receipt no",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Quality:
    score: float
    language: str | None
    flags: frozenset[Flag]
    word_count: int
    garbled: bool


def visible_text(pages: list[Page]) -> str:
    return "\n\n".join(b.text for p in pages for b in p.blocks if not b.hidden)


def is_garbled(text: str) -> bool:
    """CID-font or encoding damage: replacement/private-use glyphs, ``(cid:N)``, or non-words."""
    if not text.strip():
        return False
    artefacts = len(_CID.findall(text)) * 6
    artefacts += sum(1 for c in text if c == "�" or "" <= c <= "")
    if artefacts / max(len(text), 1) >= GARBLED_SHARE:
        return True
    tokens = [t for t in _TOKEN.findall(text) if any(c.isalpha() for c in t)]
    if len(tokens) < 30:
        return False
    wordlike = sum(1 for t in tokens if _WORDLIKE.match(t))
    return wordlike / len(tokens) < MIN_WORDLIKE_SHARE


def detect_language(text: str) -> str | None:
    """ISO 639-1 code, or None when there is too little text to tell."""
    if len(text) < MIN_CHARS_FOR_LANGUAGE:
        return None
    from langdetect import DetectorFactory, LangDetectException, detect_langs

    DetectorFactory.seed = 0  # deterministic
    try:
        best = detect_langs(text[:5000])[0]
    except LangDetectException:
        return None
    return str(best.lang) if best.prob >= 0.7 else None


def _headings(text: str) -> list[HeadingMatch]:
    found = []
    for line in text.splitlines():
        match = match_heading(line)
        if match is not None:
            found.append(match)
    return found


def heading_hits(text: str) -> int:
    return len(_headings(text))


def heading_language(text: str) -> str | None:
    """Language of the section headings, when most recognised headings are non-English.

    A CV whose headings and profile are French but whose duties keep English technical terms
    reads as English to a character model; the headings say what language it was written in.
    """
    counts: dict[str, int] = {}
    for match in _headings(text):
        counts[match.language] = counts.get(match.language, 0) + 1
    english = counts.pop("en", 0)
    if not counts:
        return None
    language, hits = max(counts.items(), key=lambda kv: kv[1])
    return language if hits >= 2 and hits > english else None


def possibly_not_cv(text: str, words: int, headings: int) -> bool:
    """Certificates, ID copies, blank pages (EC-DOC-12). Short real CVs still pass."""
    if headings >= 2:
        return False
    if headings == 0:
        return True
    return words < MIN_WORDS_FOR_CV or bool(NOT_CV_PATTERNS.search(text))


def assess(
    pages: list[Page], *, supported_languages: frozenset[str] = frozenset({"en"})
) -> Quality:
    text = visible_text(pages)
    words = len([t for t in _TOKEN.findall(text) if any(c.isalpha() for c in t)])
    garbled = is_garbled(text)
    language = None if garbled else (heading_language(text) or detect_language(text))
    headings = heading_hits(text)
    flags: set[Flag] = set()
    if garbled:
        flags.add(Flag.GARBLED_TEXT)
    if language is not None and language not in supported_languages:
        flags.add(Flag.LANGUAGE_UNSUPPORTED)
    if possibly_not_cv(text, words, headings):
        flags.add(Flag.POSSIBLY_NOT_CV)
    ocr_pages = [p for p in pages if p.ocr]
    if any((p.ocr_confidence or 0) < 70 for p in ocr_pages):
        flags.add(Flag.LOW_OCR_CONFIDENCE)

    # score: density, readable words, structure, OCR confidence (when used)
    chars_per_page = len(text) / max(len(pages), 1)
    density = min(chars_per_page / 1500, 1.0)
    tokens = [t for t in _TOKEN.findall(text) if any(c.isalpha() for c in t)]
    readable = (sum(1 for t in tokens if _WORDLIKE.match(t)) / len(tokens)) if tokens else 0.0
    structure = min(headings / 4, 1.0)
    parts = [(density, 0.3), (readable, 0.35), (structure, 0.35)]
    if ocr_pages:
        confidence = sum(p.ocr_confidence or 0 for p in ocr_pages) / len(ocr_pages) / 100
        parts = [(density, 0.2), (readable, 0.25), (structure, 0.25), (confidence, 0.3)]
    score = sum(v * w for v, w in parts)
    if garbled:
        score = min(score, 0.3)
    return Quality(
        score=round(max(0.0, min(score, 1.0)), 3),
        language=language,
        flags=frozenset(flags),
        word_count=words,
        garbled=garbled,
    )
