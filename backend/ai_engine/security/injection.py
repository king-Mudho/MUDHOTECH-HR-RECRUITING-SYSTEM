"""Prompt-injection heuristics for CV text (docs/05 §9.3, EC-DOC-14).

CV text is untrusted data. Phrases that address an AI screener, try to change instructions,
fake chat-role markers or dictate a score are reported with their character spans. A hit sets
``injection_suspected``: any LLM step is skipped for that document, claims inside the injected
text are excluded, and a recruiter sees the flag. It is never a penalty by itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# (rule, pattern, strong) - one strong hit, or two weak hits in the document, raise the flag
RULES: list[tuple[str, re.Pattern[str], bool]] = [
    (
        "override_instructions",
        re.compile(
            r"\b(ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}\b(previous|prior|"
            r"above|earlier|all|your|system)\b[^.\n]{0,20}\b(instructions?|prompts?|rules|"
            r"guidelines|criteria)\b",
            re.IGNORECASE,
        ),
        True,
    ),
    (
        "role_marker",
        re.compile(
            r"(</?\s*(cv|resume|system|assistant|user|instructions?|prompt)\s*>|"
            r"(^|\n)\s*(system|assistant|user)\s*:|\[\s*(system|inst)\s*\])",
            re.IGNORECASE,
        ),
        True,
    ),
    (
        "addresses_ai",
        re.compile(
            r"\b(note|message|instruction)s?\s+(to|for)\s+(the\s+)?(ai|llm|bot|model|screener|"
            r"screening (system|tool)|ats)\b|\bdear\s+(ai|bot|screener)\b|"
            r"\bas an ai\b|\byou are (now )?(an?|the) (ai|assistant|screener|recruiter)",
            re.IGNORECASE,
        ),
        True,
    ),
    (
        "dictates_outcome",
        re.compile(
            r"\b(rate|score|rank|grade|mark)\s+(this|the|me|my)\s+(candidate|applicant|cv|resume|"
            r"application)\b|\b(shortlist|hire|select|recommend)\w*\s+"
            r"(me|this (candidate|applicant)|them)?\s*(immediately|now|without (review|question))|"
            r"\bwithout review\b|"
            r"\b\d{2,3}\s*/\s*100\b|\b(perfect|best) (match|candidate|fit)\b|"
            r"\bmeets every (criterion|criteria|requirement)\b",
            re.IGNORECASE,
        ),
        False,
    ),
    (
        "system_prompt",
        re.compile(
            r"\bsystem prompt\b|\bjailbreak\b|\bdeveloper mode\b|\bprompt injection\b", re.I
        ),
        False,
    ),
]


@dataclass(frozen=True)
class InjectionHit:
    rule: str
    start: int
    end: int
    strong: bool


def find_injections(text: str) -> list[InjectionHit]:
    hits = [
        InjectionHit(rule, m.start(), m.end(), strong)
        for rule, pattern, strong in RULES
        for m in pattern.finditer(text)
    ]
    return sorted(hits, key=lambda h: h.start)


def is_suspected(hits: list[InjectionHit]) -> bool:
    return any(h.strong for h in hits) or len(hits) >= 2


def sentence_span(text: str, start: int, end: int) -> tuple[int, int]:
    """Widen a hit to its sentence/line so claims inside the injected text can be excluded."""
    left = max(text.rfind("\n", 0, start), text.rfind(". ", 0, start) + 1)
    right_candidates = [i for i in (text.find("\n", end), text.find(". ", end)) if i != -1]
    right = min(right_candidates) + 1 if right_candidates else len(text)
    return max(left, 0), right
