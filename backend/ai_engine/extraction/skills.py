"""Skill mentions via Aho-Corasick over taxonomy names and aliases (docs/05 §6).

The index is built from plain dicts (``id``, ``name``, ``aliases``) so the engine stays free of
Django; ``apps.taxonomy`` supplies the active taxonomy (and organisation-specific aliases).

Ambiguous names - two letters or fewer (``R``, ``C``, ``JS``) and everyday words (``Go``,
``Swift``, ``Spring``, ``Express``, ``Sage`` ...) - only match with the casing the taxonomy uses,
and the very short ones only in a list context (a skills section, or next to a comma, slash,
bullet or "and"). Matches inside a longer match ("Django" in "Django REST Framework") are
dropped; the taxonomy's ``implies`` relations cover the parent skill later.
"""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

AMBIGUOUS_WORDS = frozenset(
    {
        "go",
        "swift",
        "rust",
        "dart",
        "spring",
        "express",
        "access",
        "word",
        "sage",
        "oracle",
        "ruby",
        "rails",
        "chef",
        "puppet",
        "flask",
        "ionic",
        "helm",
        "jest",
        "lua",
        "scala",
        "elixir",
        "pastel",
        "looker",
        "airflow",
        "kanban",
        "sentry",
        "xero",
        "salesforce",
    }
)
_LIST_CONTEXT = re.compile(r"(^|[,;/|•·(]|\band\b|^\s*-)\s*$", re.IGNORECASE)
_LIST_AFTER = re.compile(r"^\s*($|[,;/|)]|and\b)", re.IGNORECASE)


@dataclass(frozen=True)
class SkillEntry:
    skill_id: str
    canonical: str


@dataclass(frozen=True)
class SkillMention:
    skill_id: str
    canonical: str
    start: int
    end: int
    text: str


def _lower(text: str) -> str:
    """Lowercase without changing string length (offsets must stay valid)."""
    out = text.lower()
    if len(out) == len(text):
        return out
    return "".join(c.lower() if len(c.lower()) == 1 else c for c in text)


def _boundary_before(text: str, i: int) -> bool:
    if i == 0:
        return True
    c = text[i - 1]
    return not (c.isalnum() or c in "+#_" or (c == "." and i >= 2 and text[i - 2].isalnum()))


def _boundary_after(text: str, j: int) -> bool:
    if j >= len(text):
        return True
    c = text[j]
    if c.isalnum() or c in "+#_":
        return False
    return not (c == "." and j + 1 < len(text) and text[j + 1].isalnum())


class SkillIndex:
    def __init__(self, patterns: dict[str, list[tuple[SkillEntry, str]]]) -> None:
        # pattern (lowercase) -> [(entry, original spelling)]
        self._patterns = patterns
        self._goto: list[dict[str, int]] = [{}]
        self._fail: list[int] = [0]
        self._out: list[list[str]] = [[]]
        for pattern in patterns:
            node = 0
            for ch in pattern:
                nxt = self._goto[node].get(ch)
                if nxt is None:
                    nxt = len(self._goto)
                    self._goto[node][ch] = nxt
                    self._goto.append({})
                    self._fail.append(0)
                    self._out.append([])
                node = nxt
            self._out[node].append(pattern)
        queue: deque[int] = deque(self._goto[0].values())
        while queue:
            node = queue.popleft()
            for ch, nxt in self._goto[node].items():
                queue.append(nxt)
                f = self._fail[node]
                while f and ch not in self._goto[f]:
                    f = self._fail[f]
                self._fail[nxt] = self._goto[f].get(ch, 0) if self._goto[f].get(ch) != nxt else 0
                self._out[nxt] = self._out[nxt] + self._out[self._fail[nxt]]

    @classmethod
    def from_taxonomy(cls, skills: Iterable[Mapping[str, Any]]) -> SkillIndex:
        patterns: dict[str, list[tuple[SkillEntry, str]]] = {}
        for skill in skills:
            entry = SkillEntry(skill_id=str(skill["id"]), canonical=str(skill["name"]))
            for spelling in [skill["name"], *skill.get("aliases", [])]:
                spelling = str(spelling).strip()
                if spelling:
                    patterns.setdefault(_lower(spelling), []).append((entry, spelling))
        return cls(patterns)

    def __len__(self) -> int:
        return len(self._patterns)

    def lookup(self, phrase: str) -> SkillEntry | None:
        """Exact (case-insensitive) name/alias lookup, for list items and corrections."""
        found = self._patterns.get(_lower(phrase.strip()))
        return found[0][0] if found else None

    def find(self, text: str, *, list_context: bool = False) -> list[SkillMention]:
        lowered = _lower(text)
        raw: list[SkillMention] = []
        node = 0
        for j, ch in enumerate(lowered):
            while node and ch not in self._goto[node]:
                node = self._fail[node]
            node = self._goto[node].get(ch, 0)
            for pattern in self._out[node]:
                end = j + 1
                start = end - len(pattern)
                if not (_boundary_before(lowered, start) and _boundary_after(lowered, end)):
                    continue
                written = text[start:end]
                for entry, spelling in self._patterns[pattern]:
                    if self._ambiguous(spelling) and not self._ambiguous_ok(
                        text, start, end, written, spelling, list_context
                    ):
                        continue
                    raw.append(SkillMention(entry.skill_id, entry.canonical, start, end, written))
                    break
        return _drop_contained(raw)

    @staticmethod
    def _ambiguous(spelling: str) -> bool:
        return len(spelling) <= 2 or spelling.lower() in AMBIGUOUS_WORDS

    @staticmethod
    def _ambiguous_ok(
        text: str, start: int, end: int, written: str, spelling: str, list_context: bool
    ) -> bool:
        if written != spelling:
            return False
        if written.islower() and not list_context:
            return False  # "spring", "go": ordinary words unless in a skills list
        if len(spelling) > 2 or list_context:
            return True
        line_start = text.rfind("\n", 0, start) + 1
        line_end = text.find("\n", end)
        before = text[line_start:start]
        after = text[end : line_end if line_end != -1 else len(text)]
        return bool(_LIST_CONTEXT.search(before)) and bool(_LIST_AFTER.match(after))


def _drop_contained(mentions: list[SkillMention]) -> list[SkillMention]:
    mentions.sort(key=lambda m: (m.start, -(m.end - m.start)))
    kept: list[SkillMention] = []
    for m in mentions:
        if any(
            k.start <= m.start and m.end <= k.end and (k.start, k.end) != (m.start, m.end)
            for k in kept
        ):
            continue
        if any((k.start, k.end, k.skill_id) == (m.start, m.end, m.skill_id) for k in kept):
            continue
        kept.append(m)
    return kept
