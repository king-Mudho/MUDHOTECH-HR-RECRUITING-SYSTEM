"""Claim extraction (docs/05 §6): experience, education, certifications/licences, skills,
projects, languages, profile summary and contact details.

Rules only, deterministic. Every claim carries the page, character offsets into ``Page.text``
and a snippet of at most 300 characters, the method, a confidence and whether it was stated
(``explicit``) or derived (``inferred``). Skills are found with the taxonomy index; listed-only
skills get lower confidence than skills used in a role or project (EC-DOC-24). Text in hidden
blocks yields claims marked ``excluded_reason=hidden_text`` (kept for audit, never evaluated).
Personal-details and references sections only feed contact de-duplication.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from ai_engine.contracts import (
    SNIPPET_MAX,
    CertificationData,
    ClaimEvidence,
    ClaimSource,
    ContactData,
    DateRange,
    EducationData,
    ExcludedReason,
    ExperienceData,
    ExtractedClaim,
    ExtractionMethod,
    ExtractionResult,
    Flag,
    LanguageData,
    Page,
    ProjectData,
    Section,
    SectionKind,
    SkillData,
    SummaryData,
)
from ai_engine.extraction.dates import YearMonth, find_date_ranges, parse_single_date
from ai_engine.extraction.layout import hidden_ranges
from ai_engine.extraction.skills import SkillIndex, SkillMention
from ai_engine.normalisation.experience import classify_employment

K = SectionKind
Semantic = Callable[[str], tuple[str, str, float] | None]  # phrase -> (skill_id, name, score)

SKILL_CONFIDENCE = {
    K.EXPERIENCE: 0.85,
    K.ATTACHMENT: 0.8,
    K.PROJECTS: 0.85,
    K.ACHIEVEMENTS: 0.75,
    K.CERTIFICATIONS: 0.75,
    K.PROFILE: 0.7,
    K.EDUCATION: 0.65,
    K.SKILLS: 0.6,  # listed without context (EC-DOC-24)
    K.LANGUAGES: 0.5,
    K.OTHER: 0.5,
}
TITLE_WORDS = re.compile(
    r"\b(developer|engineer|programmer|architect|analyst|accountant|auditor|officer|manager|"
    r"nurse|midwife|clerk|assistant|intern|trainee|student|attach[eé]e?|consultant|director|"
    r"lead|head|specialist|technician|administrator|supervisor|coordinator|controller|"
    r"executive|associate|representative|agent|teacher|lecturer|tutor|scientist|designer|"
    r"tester|administrator|cashier|bookkeeper|secretary|receptionist|driver|operator|"
    r"partner|founder|volunteer|practitioner|sister|matron|pharmacist|doctor|surveyor)s?\b",
    re.IGNORECASE,
)
INSTITUTION_WORDS = re.compile(
    r"universit|college|polytechnic|school|institute|academy|zimsec|cambridge|board|"
    r"centre|center|seminary|campus|ecole|école",
    re.IGNORECASE,
)
QUALIFICATION_WORDS = re.compile(
    r"\b(bsc|b\.sc|ba|b\.a|bcom|b\.com|btech|beng|bed|llb|mba|msc|m\.sc|ma|mphil|phd|dphil|"
    r"bachelor|master|doctor|diploma|certificate|hnd|nd|nc|level|degree|honours|hons|"
    r"o[- ]?level|a[- ]?level|igcse|gcse|matric|rgn|rmn|scn|licence|license)\b",
    re.IGNORECASE,
)
GRADE = re.compile(
    r"\b(distinction|merit|credit|first class|upper second|lower second|2[.:]1|2[.:]2|"
    r"cum laude|\d+ (?:subjects|points|units))\b",
    re.IGNORECASE,
)
KIND_ONLY = re.compile(
    r"\(?(contract|contractor|fixed[- ]term( contract)?|volunteer|voluntary|part[- ]time|"
    r"full[- ]time|permanent|temporary|freelance|internship|attachment)\)?",
    re.IGNORECASE,
)
CERT_BODIES = re.compile(
    r"\b(ACCA|CIMA|ICAZ|CIPS|IPMZ|CIPD|SHRM|PMI|AXELOS|ISACA|CompTIA|Cisco|AWS|Amazon Web Services|"
    r"Microsoft|Google|Oracle|Nurses Council of Zimbabwe|Medical and Dental Practitioners Council|"
    r"Health Professions Authority|ZIMRA|Engineering Council of Zimbabwe|ECZ|ZIE|"
    r"Vehicle Inspection Department|VID|Red Cross|St John)\b",
    re.IGNORECASE,
)
LICENCE_CLASS = re.compile(r"\bclass\s*([1-5])\b", re.IGNORECASE)
YEARS_BEFORE = re.compile(
    r"(\d{1,2})\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience\s+|exp\.?\s+)?(?:in|with|of|using)?\s*$",
    re.IGNORECASE,
)
YEARS_AFTER = re.compile(r"^\s*[(:-]?\s*(\d{1,2})\+?\s*(?:years?|yrs?)\b", re.IGNORECASE)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?:\+?263|0)[\s-]?7\d[\s-]?\d{3}[\s-]?\d{4}|\+\d{1,3}[\s\d-]{7,14}\d")
LANGUAGES = {
    "english": "English",
    "shona": "Shona",
    "ndebele": "Ndebele",
    "isindebele": "Ndebele",
    "tonga": "Tonga",
    "venda": "Venda",
    "kalanga": "Kalanga",
    "nambya": "Nambya",
    "chewa": "Chewa",
    "nyanja": "Nyanja",
    "sotho": "Sotho",
    "xhosa": "Xhosa",
    "zulu": "Zulu",
    "tswana": "Tswana",
    "swahili": "Swahili",
    "french": "French",
    "français": "French",
    "anglais": "English",
    "portuguese": "Portuguese",
    "spanish": "Spanish",
    "german": "German",
    "afrikaans": "Afrikaans",
    "arabic": "Arabic",
    "chinese": "Chinese",
    "mandarin": "Mandarin",
    "sign language": "Sign language",
    "zimbabwean sign language": "Sign language",
}
LANGUAGE_LEVEL = re.compile(
    r"\b(native|mother tongue|first language|fluent|proficient|advanced|intermediate|"
    r"conversational|basic|elementary|working knowledge|courant|natif)\b",
    re.IGNORECASE,
)
_SPLIT_HEADER = re.compile(r"\s*[|•·\t]\s*|\s+[-]\s+|\s+at\s+|\s+@\s+")
_SPLIT_LIST = re.compile(r"[,;|•·\n]|\s+-\s+|\band\b")


@dataclass(frozen=True)
class Line:
    text: str
    start: int  # offset in page text
    end: int

    @property
    def bullet(self) -> bool:
        return self.text.startswith(("-", "*", "o "))

    @property
    def content(self) -> str:
        return self.text.lstrip("-* ").strip() if self.bullet else self.text.strip()


def section_lines(page: Page, section: Section) -> list[Line]:
    """Non-empty lines of a section, without its heading line."""
    out: list[Line] = []
    offset = section.char_start
    for raw in page.text[section.char_start : section.char_end].split("\n"):
        stripped = raw.strip()
        if stripped:
            lead = len(raw) - len(raw.lstrip())
            out.append(Line(stripped, offset + lead, offset + lead + len(stripped)))
        offset += len(raw) + 1
    if out and section.heading and out[0].text == section.heading:
        out = out[1:]
    return out


def snippet(page: Page, start: int, end: int) -> str:
    text = " ".join(page.text[start:end].split())
    if len(text) > SNIPPET_MAX:
        text = text[: SNIPPET_MAX - 1].rstrip() + "…"
    return text or page.text[start : start + 1] or "?"


class _Builder:
    def __init__(self, result: ExtractionResult, today: YearMonth) -> None:
        if result.document is None:
            raise ValueError("claims need extracted text")
        self.document_id = result.document.document_id
        self.today = today
        self.claims: list[ExtractedClaim] = []
        self.flags: set[Flag] = set()

    def source(self, page: Page, start: int, end: int, *, text: str | None = None) -> ClaimSource:
        return ClaimSource(
            snippet=text or snippet(page, start, end),
            document_id=self.document_id,
            page=page.number,
            char_start=start,
            char_end=end,
        )

    def add(self, claim: ExtractedClaim) -> None:
        self.claims.append(claim)


# ------------------------------------------------------------------------- experience
def _entries(lines: list[Line], today: YearMonth) -> Iterator[tuple[list[Line], list[Line]]]:
    """(header lines, body lines) per role; a role is anchored on a line with a date range.

    When the dates sit on a line of their own, the (up to two) non-bullet lines just above them
    are the title/employer header.
    """

    def date_only(i: int) -> bool:
        return len(re.sub(r"[^A-Za-z]", "", _strip_dates(lines[i].text, today))) < 3

    def header_above(i: int, floor: int) -> int:
        start = i
        while start - 1 > floor and start - 1 >= i - 2 and not lines[start - 1].bullet:
            if find_date_ranges(lines[start - 1].text, today):
                break
            start -= 1
        return start

    anchors = [
        i for i, ln in enumerate(lines) if not ln.bullet and find_date_ranges(ln.text, today)
    ]
    taken = -1
    for n, i in enumerate(anchors):
        head_start = header_above(i, taken) if date_only(i) else i
        body_end = len(lines)
        if n + 1 < len(anchors):
            nxt = anchors[n + 1]
            body_end = header_above(nxt, i) if date_only(nxt) else nxt
        yield lines[head_start : i + 1], lines[i + 1 : body_end]
        taken = body_end - 1


def _strip_dates(text: str, today: YearMonth) -> str:
    for m in reversed(find_date_ranges(text, today)):
        text = text[: m.char_start] + text[m.char_end :]
    return text


def split_title_employer(header: str) -> tuple[str, str, str]:
    """(title, employer, location) from a header with the dates removed."""
    parts = [p.strip(" ,;:-") for p in _SPLIT_HEADER.split(header) if p and p.strip(" ,;:-")]
    parts = [p for p in parts if not KIND_ONLY.fullmatch(p)]  # "| Contract", "(Volunteer)"
    if len(parts) == 1 and "," in parts[0]:
        parts = [p.strip() for p in parts[0].split(",") if p.strip()]
        title, employer = parts[0], parts[1] if len(parts) > 1 else ""
        return title, employer, ", ".join(parts[2:])
    if not parts:
        return "", "", ""
    if len(parts) == 1:
        return parts[0], "", ""
    title_idx = next((i for i, p in enumerate(parts) if TITLE_WORDS.search(p)), 0)
    title = parts[title_idx]
    rest = [p for i, p in enumerate(parts) if i != title_idx]
    employer, location = rest[0], ", ".join(rest[1:])
    if "," in employer and not location:
        employer, location = (s.strip() for s in employer.rsplit(",", 1))
    return title, employer, location


def parse_experience(b: _Builder, page: Page, section: Section) -> None:
    lines = section_lines(page, section)
    for header_lines, body in _entries(lines, b.today):
        anchor = header_lines[-1]
        dates_found = find_date_ranges(anchor.text, b.today)
        match = dates_found[0]
        header = " | ".join(_strip_dates(ln.text, b.today) for ln in header_lines)
        title, employer, location = split_title_employer(header)
        cues = [p for p in _SPLIT_HEADER.split(header) if KIND_ONLY.fullmatch(p.strip(" ,;:-"))]
        # an explicit '| Contract' / '(Volunteer)' beats words in the title
        kind, _explicit = classify_employment(
            *(cues or [title, employer, header]), section=section.kind
        )
        if match.range is None:
            b.flags.add(Flag.DATE_ANOMALY)
        responsibilities = tuple(ln.content for ln in body if ln.content)[:20]
        data = ExperienceData(
            title=title[:200],
            employer=employer[:200],
            location=location[:120],
            dates=match.range or DateRange(),
            employment_kind=kind,
            responsibilities=tuple(r[:300] for r in responsibilities),
        )
        complete = bool(title and employer and match.range)
        start, end = header_lines[0].start, anchor.end
        b.add(
            ExtractedClaim(
                data=data,
                source=b.source(page, start, end),
                method=ExtractionMethod.RULE,
                confidence=0.85 if complete else 0.6,
                section=section.kind,
            )
        )


# -------------------------------------------------------------------------- education
def parse_education(b: _Builder, page: Page, section: Section) -> None:
    for ln in section_lines(page, section):
        if ln.bullet or not (
            QUALIFICATION_WORDS.search(ln.text) or INSTITUTION_WORDS.search(ln.text)
        ):
            continue
        ranges = [m for m in find_date_ranges(ln.text, b.today) if m.range is not None]
        text = _strip_dates(ln.text, b.today)
        dates = ranges[0].range if ranges else None
        if dates is None:
            single = parse_single_date(ln.text, b.today)
            if single is not None:
                dates = DateRange(end=single)
                text = re.sub(r"(?<!\d)" + str(single.year) + r"(?!\d)", "", text)
        parts = [p.strip(" ,;:-|") for p in re.split(r",|\||\s+-\s+", text) if p.strip(" ,;:-|")]
        if not parts:
            continue
        institution_idx = next(
            (i for i, p in enumerate(parts) if i > 0 and INSTITUTION_WORDS.search(p)), None
        )
        if institution_idx is None and len(parts) > 1 and not QUALIFICATION_WORDS.search(parts[1]):
            institution_idx = 1
        institution = parts[institution_idx] if institution_idx is not None else ""
        grade_match = GRADE.search(ln.text)
        b.add(
            ExtractedClaim(
                data=EducationData(
                    qualification_text=parts[0][:300],
                    institution=institution[:200],
                    dates=dates or DateRange(),
                    grade=grade_match.group(0) if grade_match else "",
                ),
                source=b.source(page, ln.start, ln.end),
                method=ExtractionMethod.RULE,
                confidence=0.85 if QUALIFICATION_WORDS.search(parts[0]) else 0.6,
                section=section.kind,
            )
        )


# ---------------------------------------------------------------------- certifications
def parse_certifications(b: _Builder, page: Page, section: Section) -> None:
    """One claim per line; the name is the credential as written (dates removed)."""
    for ln in section_lines(page, section):
        content = ln.content
        if len(content) < 3:
            continue
        issued = parse_single_date(content, b.today)
        name = _strip_dates(content, b.today)
        if issued is not None:
            name = re.sub(rf"(?<!\d){issued.year}(?!\d)", "", name)
        name = re.sub(r"\s+", " ", name).replace("()", "").strip(" ,;:-|")
        if name.count("(") < name.count(")"):
            name = name.rstrip(")").strip()
        if name.count("(") > name.count(")"):
            name = name.rstrip("(").strip()
        if len(name) < 3:
            continue
        body = CERT_BODIES.search(content)
        licence = LICENCE_CLASS.search(content)
        b.add(
            ExtractedClaim(
                data=CertificationData(
                    name=name[:200],
                    body=body.group(0) if body else "",
                    issued=issued,
                    licence_class=licence.group(1) if licence else "",
                ),
                source=b.source(page, ln.start, ln.end),
                method=ExtractionMethod.RULE,
                confidence=0.8,
                section=section.kind,
            )
        )


# --------------------------------------------------------------------------- languages
def parse_languages(b: _Builder, page: Page, section: Section) -> None:
    seen: set[str] = set()
    for ln in section_lines(page, section):
        offset = ln.start
        for item in re.split(r"([,;/|]|\band\b)", ln.text):
            item_start = offset
            offset += len(item)
            lowered = item.lower()
            for key, name in LANGUAGES.items():
                if re.search(rf"\b{re.escape(key)}\b", lowered) and name not in seen:
                    seen.add(name)
                    level = LANGUAGE_LEVEL.search(item)
                    lead = len(item) - len(item.lstrip())
                    b.add(
                        ExtractedClaim(
                            data=LanguageData(
                                language=name, level=level.group(0).lower() if level else ""
                            ),
                            source=b.source(
                                page, item_start + lead, item_start + len(item.rstrip())
                            ),
                            method=ExtractionMethod.RULE,
                            confidence=0.9,
                            section=section.kind,
                        )
                    )
                    break


# ---------------------------------------------------------------------------- projects
def parse_projects(b: _Builder, page: Page, section: Section, index: SkillIndex | None) -> None:
    lines = section_lines(page, section)
    groups: list[list[Line]] = []
    for ln in lines:
        if not ln.bullet or not groups:
            groups.append([ln])
        else:
            groups[-1].append(ln)
    for group in groups:
        title = group[0].content
        description = " ".join(ln.content for ln in group[1:])
        text = page.text[group[0].start : group[-1].end]
        tech = tuple(dict.fromkeys(m.canonical for m in (index.find(text) if index else [])))
        b.add(
            ExtractedClaim(
                data=ProjectData(
                    title=title[:200], description=description[:1000], technologies=tech
                ),
                source=b.source(page, group[0].start, group[-1].end),
                method=ExtractionMethod.RULE,
                confidence=0.75,
                section=section.kind,
            )
        )


# ------------------------------------------------------------------------------ skills
def _years(text: str, mention: SkillMention) -> float | None:
    line_start = text.rfind("\n", 0, mention.start) + 1
    line_end = text.find("\n", mention.end)
    before = text[line_start : mention.start]
    after = text[mention.end : line_end if line_end != -1 else len(text)]
    m = YEARS_BEFORE.search(before) or YEARS_AFTER.match(after)
    if not m:
        return None
    years = float(m.group(1))
    return years if 0 < years <= 60 else None


def parse_skills(
    b: _Builder,
    pages: tuple[Page, ...],
    sections: tuple[Section, ...],
    index: SkillIndex | None,
    semantic: Semantic | None,
) -> None:
    best: dict[str, ExtractedClaim] = {}

    def offer(claim: ExtractedClaim, key: str) -> None:
        current = best.get(key)
        if current is None or claim.confidence > current.confidence:
            best[key] = claim

    by_page = {p.number: p for p in pages}
    for section in sections:
        if not section.evaluable or section.kind == K.LANGUAGES:
            continue
        page = by_page[section.page]
        base = section.char_start  # skip the heading line itself ("Skills" is not a skill)
        if section.heading and page.text.startswith(section.heading, base):
            base += len(section.heading)
        text = page.text[base : section.char_end]
        listed = section.kind == K.SKILLS
        mentions = index.find(text, list_context=listed) if index else []
        confidence = SKILL_CONFIDENCE.get(section.kind, 0.5)
        for m in mentions:
            start, end = base + m.start, base + m.end
            line_start = page.text.rfind("\n", 0, start) + 1
            line_end = page.text.find("\n", end)
            line_end = line_end if line_end != -1 and line_end <= section.char_end else end
            offer(
                ExtractedClaim(
                    data=SkillData(
                        raw=m.text,
                        skill_id=m.skill_id,
                        canonical=m.canonical,
                        years=_years(text, m),
                    ),
                    source=b.source(page, line_start, line_end)
                    if line_end - line_start <= SNIPPET_MAX
                    else b.source(page, start, end),
                    method=ExtractionMethod.TAXONOMY,
                    confidence=confidence,
                    section=section.kind,
                ),
                f"id:{m.skill_id}",
            )
        if listed:
            covered = [(m.start, m.end) for m in mentions]
            for item, s, e in _list_items(text):
                if any(a < e and s < bnd for a, bnd in covered):
                    continue
                start, end = base + s, base + e
                found = semantic(item) if semantic else None
                if found is not None:
                    skill_id, canonical, score = found
                    offer(
                        ExtractedClaim(
                            data=SkillData(raw=item, skill_id=skill_id, canonical=canonical),
                            source=b.source(page, start, end),
                            method=ExtractionMethod.EMBEDDING,
                            confidence=round(min(score, 0.6), 3),
                            evidence=ClaimEvidence.INFERRED,
                            section=section.kind,
                        ),
                        f"id:{skill_id}",
                    )
                else:
                    offer(
                        ExtractedClaim(
                            data=SkillData(raw=item),
                            source=b.source(page, start, end),
                            method=ExtractionMethod.SECTION,
                            confidence=0.4,
                            section=section.kind,
                        ),
                        f"raw:{item.lower()}",
                    )
    for claim in sorted(
        best.values(), key=lambda c: (c.source.page or 0, c.source.char_start or 0)
    ):
        b.add(claim)

    # hidden text: record what it claims, excluded from evaluation (EC-DOC-13)
    for page in pages:
        for start, end in hidden_ranges(page):
            hidden = page.text[start:end]
            for m in index.find(hidden, list_context=True) if index else []:
                b.add(
                    ExtractedClaim(
                        data=SkillData(raw=m.text, skill_id=m.skill_id, canonical=m.canonical),
                        source=b.source(page, start, end),  # the whole hidden block
                        method=ExtractionMethod.TAXONOMY,
                        confidence=0.0,
                        excluded_reason=ExcludedReason.HIDDEN_TEXT,
                    )
                )


def _list_items(text: str) -> Iterator[tuple[str, int, int]]:
    pos = 0
    for piece in _SPLIT_LIST.split(text):
        start = text.find(piece, pos) if piece else pos
        pos = start + len(piece)
        item = piece.strip(" .:-*\t")
        if not item:
            continue
        lead = piece.find(item)
        words = item.split()
        if 2 <= len(item) <= 60 and len(words) <= 6 and any(c.isalpha() for c in item):
            yield item, start + lead, start + lead + len(item)


# ------------------------------------------------------------------- profile, contact
def parse_profile(b: _Builder, page: Page, section: Section) -> None:
    lines = section_lines(page, section)
    if not lines:
        return
    text = " ".join(ln.content for ln in lines)
    b.add(
        ExtractedClaim(
            data=SummaryData(text=text[:2000]),
            source=b.source(page, lines[0].start, lines[-1].end),
            method=ExtractionMethod.SECTION,
            confidence=0.9,
            section=section.kind,
        )
    )


def parse_contact(b: _Builder, page: Page, section: Section) -> None:
    text = page.text[section.char_start : section.char_end]
    email = EMAIL.search(text)
    phone = PHONE.search(text)
    if not email and not phone:
        return
    hits = [m for m in (email, phone) if m]
    start = section.char_start + min(m.start() for m in hits)
    end = section.char_start + max(m.end() for m in hits)
    if end - start > SNIPPET_MAX:
        end = start + (hits[0].end() - hits[0].start())
    b.add(
        ExtractedClaim(
            data=ContactData(
                email=email.group(0) if email else "", phone=phone.group(0).strip() if phone else ""
            ),
            source=b.source(page, start, end),
            method=ExtractionMethod.RULE,
            confidence=0.95,
            section=section.kind,
            excluded_reason=ExcludedReason.PERSONAL_SECTION if section.kind == K.PERSONAL else None,
        )
    )


# --------------------------------------------------------------------------- pipeline
def extract_claims(
    result: ExtractionResult,
    *,
    today: YearMonth,
    skills: SkillIndex | None = None,
    semantic: Semantic | None = None,
) -> ExtractionResult:
    """Add claims to an extraction result (no-op for failed results)."""
    if result.document is None:
        return result
    b = _Builder(result, today)
    pages = {p.number: p for p in result.document.pages}
    contact_done = False
    for section in result.sections:
        page = pages[section.page]
        if section.kind in (K.EXPERIENCE, K.ATTACHMENT):
            parse_experience(b, page, section)
        elif section.kind == K.EDUCATION:
            parse_education(b, page, section)
        elif section.kind == K.CERTIFICATIONS:
            parse_certifications(b, page, section)
        elif section.kind == K.LANGUAGES:
            parse_languages(b, page, section)
        elif section.kind == K.PROJECTS:
            parse_projects(b, page, section, skills)
        elif section.kind == K.PROFILE:
            parse_profile(b, page, section)
        if section.kind in (K.OTHER, K.PERSONAL) and not contact_done:
            before = len(b.claims)
            parse_contact(b, page, section)
            contact_done = len(b.claims) > before
    parse_skills(b, result.document.pages, result.sections, skills, semantic)
    flags = result.flags | b.flags
    return result.model_copy(update={"claims": result.claims + tuple(b.claims), "flags": flags})
