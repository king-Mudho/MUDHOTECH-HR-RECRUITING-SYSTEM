"""Section detection (docs/05 §5).

A heading is a short line that matches the lexicon (English plus common French/Portuguese
headings, accent-insensitive, numbering and trailing colons ignored). Typography (bold, larger
font, ALL CAPS, own block) raises confidence but never creates a heading on its own: a bold job
title must not split an experience section. Text before the first heading (name, contact) is
``other``; DOCX headers/footers are their own ``other`` regions. ``personal`` and ``references``
sections are kept for contact de-duplication only and are excluded from evaluation.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from ai_engine.contracts import Block, BlockKind, Page, Section, SectionKind

MAX_HEADING_WORDS = 6
MAX_HEADING_CHARS = 60
MAX_EXTRA_WORDS = 3

K = SectionKind
_EN: dict[SectionKind, tuple[str, ...]] = {
    K.PROFILE: (
        "profile",
        "personal profile",
        "professional profile",
        "career profile",
        "summary",
        "professional summary",
        "career summary",
        "executive summary",
        "objective",
        "career objective",
        "objectives",
        "about me",
        "personal statement",
    ),
    K.EXPERIENCE: (
        "experience",
        "work experience",
        "professional experience",
        "relevant experience",
        "employment",
        "employment history",
        "employment record",
        "work history",
        "career history",
        "career",
        "positions held",
        "volunteer",
        "volunteer experience",
        "volunteering",
        "freelance experience",
    ),
    K.ATTACHMENT: (
        "industrial attachment",
        "attachment",
        "internship",
        "internships",
        "work related learning",
        "work-related learning",
        "practicum",
    ),
    K.EDUCATION: (
        "education",
        "educational background",
        "education and training",
        "academic qualifications",
        "academic background",
        "academic history",
        "qualifications",
        "educational qualifications",
    ),
    K.SKILLS: (
        "skills",
        "technical skills",
        "key skills",
        "core skills",
        "core competencies",
        "competencies",
        "computer skills",
        "it skills",
        "skills and competencies",
        "areas of expertise",
        "expertise",
        "technical expertise",
    ),
    K.CERTIFICATIONS: (
        "certifications",
        "certification",
        "certificates",
        "licences",
        "licenses",
        "licences and certifications",
        "licenses and certifications",
        "professional certifications",
        "professional qualifications",
        "courses",
        "short courses",
        "training",
        "professional development",
        "professional memberships",
        "memberships",
        "affiliations",
    ),
    K.PROJECTS: (
        "projects",
        "key projects",
        "selected projects",
        "personal projects",
        "academic projects",
        "portfolio",
    ),
    K.LANGUAGES: ("languages", "language skills", "languages spoken"),
    K.ACHIEVEMENTS: (
        "achievements",
        "key achievements",
        "accomplishments",
        "awards",
        "honours",
        "honors",
        "awards and achievements",
        "publications",
        "research",
    ),
    K.PERSONAL: (
        "personal details",
        "personal information",
        "personal data",
        "personal particulars",
        "bio data",
        "biodata",
        "contact details",
        "contact information",
    ),
    K.REFERENCES: ("references", "referees", "reference", "referee"),
    K.OTHER: (
        "hobbies",
        "interests",
        "hobbies and interests",
        "additional information",
        "other information",
        "declaration",
        "extra-curricular activities",
        "extracurricular activities",
        "activities",
    ),
}
_OTHER_LANGUAGES: dict[str, dict[SectionKind, tuple[str, ...]]] = {
    "fr": {
        K.PROFILE: ("profil", "profil professionnel", "résumé professionnel"),
        K.EXPERIENCE: ("expérience professionnelle", "expérience", "expériences"),
        K.ATTACHMENT: ("stage", "stages"),
        K.EDUCATION: ("formation", "éducation", "diplômes"),
        K.SKILLS: ("compétences", "compétences techniques"),
        K.LANGUAGES: ("langues",),
        K.PERSONAL: ("informations personnelles",),
        K.REFERENCES: ("références",),
        K.PROJECTS: ("projets",),
        K.OTHER: ("centres d'intérêt", "loisirs"),
    },
    "pt": {
        K.EXPERIENCE: ("experiência profissional", "experiência"),
        K.EDUCATION: ("formação", "formação académica"),
        K.SKILLS: ("competências",),
        K.LANGUAGES: ("idiomas", "línguas"),
        K.REFERENCES: ("referências",),
    },
}


@dataclass(frozen=True)
class HeadingMatch:
    kind: SectionKind
    phrase: str
    language: str  # language of the lexicon entry ("en" when the spelling is also English)
    exact: bool  # the whole line is the heading phrase


def fold(text: str) -> str:
    """Lowercase, strip accents, numbering, bullets and trailing punctuation."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = text.replace("&", " and ").replace("/", " and ")
    text = re.sub(r"^[\s\-*#>\d.)(ivx]*\s(?=[a-z])|^[\s\-*#>]+", "", text)
    text = re.sub(r"[\s:.\-|]+$", "", text)  # dashes were normalised already
    return re.sub(r"\s+", " ", text).strip()


_CONNECTORS = frozenset(
    [
        "with",
        "in",
        "of",
        "at",
        "for",
        "on",
        "to",
        "as",
        "from",
        "by",
        "using",
        "and",
        "or",
        "including",
    ]
)
_LEXICON: list[tuple[str, str, SectionKind, str]] = []  # (folded, original, kind, language)
for _kind, _phrases in _EN.items():
    _LEXICON += [(fold(p), p, _kind, "en") for p in _phrases]
for _lang, _table in _OTHER_LANGUAGES.items():
    for _kind, _phrases in _table.items():
        _LEXICON += [(fold(p), p, _kind, _lang) for p in _phrases]
_LEXICON.sort(key=lambda e: -len(e[0]))  # longest phrase wins


def match_heading(line: str) -> HeadingMatch | None:
    raw = line.strip()
    if not raw or len(raw) > MAX_HEADING_CHARS:
        return None
    folded = fold(raw)
    words = folded.split()
    if not words or len(words) > MAX_HEADING_WORDS:
        return None
    lowered = raw.lower()
    candidates = []
    for phrase_folded, original, kind, language in _LEXICON:
        if folded == phrase_folded or (
            folded.startswith(phrase_folded + " ")
            and len(words) - len(phrase_folded.split()) <= MAX_EXTRA_WORDS
            and not re.search(r"[,;|@]", raw)
            and words[len(phrase_folded.split())] not in _CONNECTORS
        ):
            candidates.append((phrase_folded, original, kind, language))
    if not candidates:
        return None
    best_len = len(candidates[0][0])
    best = [c for c in candidates if len(c[0]) == best_len]
    # same folded spelling in two languages (experience/expérience): prefer the exact accents
    exact = [c for c in best if lowered.startswith(c[1])]
    _, original, kind, language = (exact or best)[0]
    if not exact and language != "en" and any(c[3] == "en" for c in best):
        language = "en"
    return HeadingMatch(
        kind=kind, phrase=original, language=language, exact=folded == fold(original)
    )


def _looks_like_heading(line: str, block: Block, body_size: float) -> bool:
    letters = [c for c in line if c.isalpha()]
    caps = bool(letters) and all(c.isupper() for c in letters) and len(letters) >= 4
    bigger = block.font_size is not None and body_size > 0 and block.font_size > body_size * 1.1
    return block.bold or caps or bigger or line.rstrip().endswith(":")


def _body_size(page: Page) -> float:
    sizes = sorted(b.font_size for b in page.blocks if b.font_size and not b.hidden)
    return sizes[len(sizes) // 2] if sizes else 0.0


@dataclass
class _Open:
    kind: SectionKind
    heading: str
    start: int


def _close(out: list[Section], page: Page, region: _Open, end: int) -> None:
    if page.text[region.start : end].strip():
        out.append(
            Section(
                kind=region.kind,
                heading=region.heading,
                page=page.number,
                char_start=region.start,
                char_end=end,
            )
        )


def detect_sections(pages: list[Page] | tuple[Page, ...]) -> list[Section]:
    """Contiguous sections over the visible text of every page (hidden blocks are skipped)."""
    sections: list[Section] = []
    current: SectionKind = SectionKind.OTHER
    for page in pages:
        body = _body_size(page)
        region = _Open(current, "", 0)
        last_end = 0
        for block in page.blocks:
            if block.hidden:
                continue
            start = block.char_start
            end = start + len(block.text)
            if block.kind in (BlockKind.HEADER, BlockKind.FOOTER):
                _close(sections, page, region, start)
                _close(sections, page, _Open(SectionKind.OTHER, block.kind.value, start), end)
                region = _Open(region.kind, region.heading, end)
                last_end = end
                continue
            lines = block.text.split("\n")
            offset = start
            for line in lines:
                found = match_heading(line)
                if found and (found.exact or _looks_like_heading(line, block, body)):
                    _close(sections, page, region, offset)
                    region = _Open(found.kind, line.strip(), offset)
                offset += len(line) + 1
            last_end = end
        _close(sections, page, region, last_end)
        current = region.kind  # a section continues onto the next page
    return sections


def section_at(sections: list[Section], page: int, offset: int) -> Section | None:
    for section in sections:
        if section.page == page and section.char_start <= offset < section.char_end:
            return section
    return None
