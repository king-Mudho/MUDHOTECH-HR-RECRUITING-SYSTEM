"""Protected and irrelevant personal data (docs/05 §7, EC-DOC-15/16) and the safety pass.

Detected: date of birth/age, Zimbabwean national ID (``63-1234567 A 42`` shape), passport
numbers, gender/sex, marital status, number of children, religion/church, tribe/ethnicity/race,
nationality/citizenship, health/disability/HIV status, political affiliation and home address.
Each detection is stored as a ``protected`` claim with ``excluded_reason=protected_attribute``
so audits can prove the exclusion - with the *value masked* in the snippet (data minimisation).
Evaluable text that contains protected details (e.g. a profile mentioning age or religion) is
redacted. Photos are never processed (EC-DOC-15). Graduation years are kept for recency but are
not an age (docs/05 §7).

:func:`protect` also runs the prompt-injection detector and excludes claims inside injected text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ai_engine.contracts import (
    SNIPPET_MAX,
    ClaimSource,
    ExcludedReason,
    ExtractedClaim,
    ExtractionMethod,
    ExtractionResult,
    Flag,
    ProtectedData,
    SummaryData,
)
from ai_engine.security.injection import find_injections, is_suspected, sentence_span

REDACTED = "[redacted]"
_SEP = r"\s*(?:[:-]|\bis\b)?\s*"  # dashes are normalised upstream
_VALUE = r"(?:[^\n|;.]|\.(?=\S)){1,60}"  # stops at a sentence end
_REQ = r"\s*(?::|\s-\s|\bis\b)\s*"  # "Religion: ...", not "religion" in prose

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "date_of_birth",
        re.compile(
            r"\b(date of birth|d\.?\s?o\.?\s?b\.?|birth\s?date|born(?: on)?)" + _SEP + _VALUE,
            re.IGNORECASE,
        ),
    ),
    (
        "age",
        re.compile(
            r"\bage" + _SEP + r"\d{2}\b|\b\d{2}[- ]?(?:years?|yrs?)[- ]old\b", re.IGNORECASE
        ),
    ),
    (
        "national_id",
        re.compile(
            r"\b(national id(?:entity)?(?: (?:no|number))?|id (?:no|number)\.?|i\.d\.)"
            + _REQ
            + _VALUE
            + r"|\b\d{2}[- ]?\d{6,7}[- ]?[A-Z][- ]?\d{2}\b",
            re.IGNORECASE,
        ),
    ),
    (
        "passport",
        re.compile(
            r"\bpassport(?: (?:no|number|#))?\.?" + _SEP + r"[A-Z]{1,2}\d{6,8}\b", re.IGNORECASE
        ),
    ),
    ("gender", re.compile(r"\b(gender|sex)" + _SEP + r"(male|female|m|f|other)\b", re.IGNORECASE)),
    (
        "marital_status",
        re.compile(
            r"\bmarital status" + _REQ + _VALUE + r"|\b(married|divorced|widowed) (with|and)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "children",
        re.compile(
            r"\b(number of children|no\.? of children|dependants|dependents|children)"
            + _REQ
            + r"\d+\b",
            re.IGNORECASE,
        ),
    ),
    (
        "religion",
        re.compile(r"\b(religion|denomination|church|faith)" + _REQ + _VALUE, re.IGNORECASE),
    ),
    (
        "ethnicity",
        re.compile(r"\b(tribe|totem|ethnicity|ethnic group|race)" + _REQ + _VALUE, re.IGNORECASE),
    ),
    (
        "nationality",
        re.compile(r"\b(nationality|citizenship)" + _REQ + _VALUE, re.IGNORECASE),
    ),
    (
        "health",
        re.compile(
            r"\b(health(?: status)?|disabilit(?:y|ies)|medical condition|hiv status)"
            + _REQ
            + _VALUE
            + r"|\bhiv[- ](?:positive|negative)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "political",
        re.compile(
            r"\b(political (?:affiliation|party)|party membership)"
            + _REQ
            + _VALUE
            + r"|\b(member|cadre|activist) of (zanu[- ]?pf|mdc(?:[- ]t)?|ccc)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "home_address",
        re.compile(r"\b(home|residential|physical|postal) address" + _REQ + _VALUE, re.IGNORECASE),
    ),
]
# "Health" as a field of work (e.g. "Health and Safety", "public health") is not a status
_NOT_HEALTH = re.compile(
    r"health\s*(and|&)\s*safety|public health|health (care|education|informat)", re.I
)


@dataclass(frozen=True)
class Detection:
    attribute: str
    start: int
    end: int
    label_end: int  # end of the label ("Date of birth:"), the value follows


def find_protected(text: str) -> list[Detection]:
    found: list[Detection] = []
    for attribute, pattern in PATTERNS:
        for m in pattern.finditer(text):
            if attribute == "health" and _NOT_HEALTH.search(text[m.start() : m.end() + 20]):
                continue
            label_end = m.end(1) if m.lastindex and m.group(1) else m.start()
            found.append(Detection(attribute, m.start(), m.end(), label_end))
    found.sort(key=lambda d: (d.start, -(d.end - d.start)))
    kept: list[Detection] = []
    for d in found:  # the national ID number inside "National ID: ..." is one detection
        if kept and d.start < kept[-1].end:
            continue
        kept.append(d)
    return kept


def redact(text: str, spans: list[tuple[int, int]]) -> str:
    for start, end in sorted(spans, reverse=True):
        text = text[:start] + REDACTED + text[end:]
    return text


def _masked(text: str, d: Detection) -> str:
    label = text[d.start : d.label_end].strip(" :-")
    masked = f"{label}: {REDACTED}" if label else REDACTED
    return masked[:SNIPPET_MAX]


def protect(result: ExtractionResult) -> ExtractionResult:
    """Add protected-attribute claims, redact evaluable text, exclude injected claims."""
    if result.document is None:
        return result
    document_id = result.document.document_id
    claims = list(result.claims)
    flags = set(result.flags)
    protected_spans: dict[int, list[tuple[int, int]]] = {}
    injected_spans: dict[int, list[tuple[int, int]]] = {}
    for page in result.document.pages:
        detections = find_protected(page.text)
        protected_spans[page.number] = [(d.start, d.end) for d in detections]
        for d in detections:
            claims.append(
                ExtractedClaim(
                    data=ProtectedData(attribute=d.attribute),
                    source=ClaimSource(
                        snippet=_masked(page.text, d),
                        document_id=document_id,
                        page=page.number,
                        char_start=d.start,
                        char_end=d.end,
                    ),
                    method=ExtractionMethod.RULE,
                    confidence=0.9,
                    excluded_reason=ExcludedReason.PROTECTED_ATTRIBUTE,
                )
            )
        hits = find_injections(page.text)
        if is_suspected(hits):
            flags.add(Flag.INJECTION_SUSPECTED)
            injected_spans[page.number] = [sentence_span(page.text, h.start, h.end) for h in hits]

    out: list[ExtractedClaim] = []
    for claim in claims:
        src = claim.source
        page_no, start, end = src.page or 0, src.char_start, src.char_end
        if claim.evaluable and start is not None and end is not None:
            if any(a < end and start < b for a, b in injected_spans.get(page_no, [])):
                claim = claim.model_copy(update={"excluded_reason": ExcludedReason.INJECTION})
            elif isinstance(claim.data, SummaryData):
                overlapping = [
                    (a, b) for a, b in protected_spans.get(page_no, []) if a < end and start < b
                ]
                if overlapping:
                    claim = _redact_summary(claim, result, overlapping)
        out.append(claim)
    return result.model_copy(update={"claims": tuple(out), "flags": frozenset(flags)})


def _redact_summary(
    claim: ExtractedClaim, result: ExtractionResult, spans: list[tuple[int, int]]
) -> ExtractedClaim:
    if result.document is None:
        return claim
    page = result.document.page(claim.source.page or 1)
    start, end = claim.source.char_start or 0, claim.source.char_end or 0
    local = [(max(a, start) - start, min(b, end) - start) for a, b in spans]
    text = " ".join(redact(page.text[start:end], local).split())
    return claim.model_copy(
        update={
            "data": SummaryData(text=text[:2000]),
            "source": claim.source.model_copy(update={"snippet": text[:SNIPPET_MAX] or REDACTED}),
        }
    )


def redact_for_llm(text: str, *, names: list[str] | None = None) -> str:
    """docs/05 §9.1: names -> [CANDIDATE]; emails, phones, IDs and protected values removed."""
    spans = [(d.start, d.end) for d in find_protected(text)]
    text = redact(text, spans)
    text = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "[EMAIL]", text)
    text = re.sub(r"(?:\+?\d[\d\s-]{7,}\d)", "[PHONE]", text)
    for name in names or []:
        for part in [name, *name.split()]:
            if len(part) >= 3:
                text = re.sub(rf"\b{re.escape(part)}\b", "[CANDIDATE]", text, flags=re.IGNORECASE)
    return text
