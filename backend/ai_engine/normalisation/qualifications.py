"""Qualification level mapping (docs/05 §6, EC-DOC-22/23).

Levels come from the taxonomy (``fixtures/taxonomy/qualifications.json`` via ``apps.taxonomy``):
ZIMSEC O/A Level, NC/ND/HND, degrees, postgraduate awards, plus Cambridge equivalents. Aliases
match on word boundaries; aliases of three letters or fewer (``BA``, ``MA``, ``ND``, ``NC``) must
be written in capitals. When several levels match one line the highest-ranked wins ("BSc
Honours" is honours, "Higher National Diploma" is HND, not ND).

Foreign qualifications (an institution or country outside Zimbabwe) keep the level we can map but
are marked ``needs_verification``; text that maps to no level is ``needs_verification`` too.
Neither is ever a negative: missing or unverified evidence goes to a human.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from ai_engine.contracts import EducationData, ExtractedClaim, ExtractionResult

FOREIGN = re.compile(
    r"\b(south africa|pretoria|johannesburg|cape town|witwatersrand|wits|unisa|kwazulu|"
    r"stellenbosch|"
    r"rhodes university|united kingdom|\buk\b|england|scotland|wales|london|manchester|"
    r"united states|\busa\b|canada|australia|new zealand|india|china|russia|cuba|germany|"
    r"france|malaysia|zambia|botswana|namibia|mozambique|malawi|kenya|uganda|tanzania|"
    r"nigeria|ghana|lusaka|gaborone|nairobi|kampala)\b",
    re.IGNORECASE,
)
FIELD = re.compile(r"\b(?:in|of)\s+(?!the\b)([A-Z][\w&,' -]{2,80}?)(?:\s*[(,]|$)")


@dataclass(frozen=True)
class Level:
    code: str
    name: str
    rank: int
    framework: str


@dataclass(frozen=True)
class QualificationMatch:
    level: Level | None
    alias: str
    foreign: bool
    needs_verification: bool
    field: str
    body: str | None  # professional body code (IPMZ, ACCA, ...)


class QualificationIndex:
    def __init__(
        self,
        levels: list[tuple[Level, re.Pattern[str]]],
        bodies: list[tuple[str, re.Pattern[str]]],
    ) -> None:
        self.levels = levels
        self.bodies = bodies

    @staticmethod
    def _pattern(alias: str) -> re.Pattern[str]:
        escaped = re.escape(alias.strip()).replace(r"\ ", r"\s+")
        flags = 0 if len(alias.replace(".", "")) <= 3 else re.IGNORECASE
        return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", flags)

    @classmethod
    def from_taxonomy(
        cls, levels: Iterable[Mapping[str, Any]], bodies: Iterable[Mapping[str, Any]] = ()
    ) -> QualificationIndex:
        out: list[tuple[Level, re.Pattern[str]]] = []
        for item in levels:
            level = Level(
                code=str(item["code"]),
                name=str(item["name"]),
                rank=int(item["rank"]),
                framework=str(item.get("framework", "")),
            )
            for alias in [item["name"], *item.get("aliases", [])]:
                if str(alias).strip():
                    out.append((level, cls._pattern(str(alias))))
        body_patterns = []
        for body in bodies:
            for alias in [body["code"], body["name"], *body.get("designations", [])]:
                body_patterns.append((str(body["code"]), cls._pattern(str(alias))))
        return cls(out, body_patterns)

    def match(self, text: str, *, institution: str = "", context: str = "") -> QualificationMatch:
        best: tuple[Level, str] | None = None
        for level, pattern in self.levels:
            found = pattern.search(text)
            if found and (
                best is None or (level.rank, len(found.group(0))) > (best[0].rank, len(best[1]))
            ):  # highest level; on a tie the longer, more specific alias
                best = (level, found.group(0))
        foreign = bool(FOREIGN.search(" ".join((text, institution, context))))
        body = next((code for code, p in self.bodies if p.search(f"{text} {context}")), None)
        field_match = FIELD.search(text)
        return QualificationMatch(
            level=best[0] if best else None,
            alias=best[1] if best else "",
            foreign=foreign,
            needs_verification=foreign or best is None,
            field=field_match.group(1).strip() if field_match else "",
            body=body,
        )


def normalise_education(result: ExtractionResult, index: QualificationIndex) -> ExtractionResult:
    """Fill ``level``/``foreign``/``needs_verification``/``field`` on education claims."""
    claims: list[ExtractedClaim] = []
    for claim in result.claims:
        data = claim.data
        if isinstance(data, EducationData):
            found = index.match(
                data.qualification_text, institution=data.institution, context=claim.source.snippet
            )
            data = data.model_copy(
                update={
                    "level": found.level.code if found.level else None,
                    "foreign": found.foreign,
                    "needs_verification": found.needs_verification,
                    "field": data.field or found.field,
                }
            )
            claim = claim.model_copy(update={"data": data})
        claims.append(claim)
    return result.model_copy(update={"claims": tuple(claims)})
