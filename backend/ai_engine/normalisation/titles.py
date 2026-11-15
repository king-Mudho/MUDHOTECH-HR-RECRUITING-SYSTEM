"""Job title normalisation (docs/05 §6): lowercase, expand abbreviations, split out seniority,
map synonyms to a common title. Used to compare roles with a vacancy title; never scored alone.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from ai_engine.contracts import ExperienceData, ExtractedClaim, ExtractionResult

ABBREVIATIONS = {
    "sr": "senior",
    "snr": "senior",
    "jr": "junior",
    "jnr": "junior",
    "asst": "assistant",
    "ass": "assistant",
    "mgr": "manager",
    "mngr": "manager",
    "dev": "developer",
    "eng": "engineer",
    "engr": "engineer",
    "admin": "administrator",
    "exec": "executive",
    "rep": "representative",
    "coord": "coordinator",
    "hr": "human resources",
    "ict": "information technology",
    "it": "information technology",
    "acc": "accounts",
    "accts": "accounts",
    "rgn": "registered general nurse",
    "qa": "quality assurance",
    "bi": "business intelligence",
    "ceo": "chief executive officer",
    "cfo": "chief finance officer",
    "cto": "chief technology officer",
}
SENIORITY = {
    "intern": "intern",
    "internship": "intern",
    "attachment": "intern",
    "attachee": "intern",
    "student": "intern",
    "trainee": "trainee",
    "graduate": "trainee",
    "junior": "junior",
    "associate": "junior",
    "assistant": "junior",
    "mid": "mid",
    "intermediate": "mid",
    "senior": "senior",
    "lead": "lead",
    "principal": "lead",
    "head": "head",
    "chief": "head",
}
# seniority words that are also part of the job itself and must stay in the title
KEEP_IN_TITLE = frozenset({"assistant", "associate", "head", "chief", "student", "attachment"})
SYNONYMS = {
    "software engineer": "software developer",
    "programmer": "software developer",
    "developer": "software developer",
    "application developer": "software developer",
    "systems developer": "software developer",
    "backend developer": "software developer",
    "back end developer": "software developer",
    "frontend developer": "software developer",
    "front end developer": "software developer",
    "full stack developer": "software developer",
    "fullstack developer": "software developer",
    "web developer": "software developer",
    "registered general nurse": "registered nurse",
    "staff nurse": "registered nurse",
    "nursing sister": "registered nurse",
    "ward nurse": "registered nurse",
    "general nurse": "registered nurse",
    "personnel officer": "human resources officer",
    "human resources business partner": "human resources business partner",
    "people officer": "human resources officer",
    "human resource officer": "human resources officer",
    "human resources practitioner": "human resources officer",
    "business intelligence analyst": "data analyst",
    "data and insights analyst": "data analyst",
    "reporting analyst": "data analyst",
    "finance officer": "accountant",
    "accounting officer": "accountant",
    "chartered accountant": "accountant",
}
_DROP = re.compile(
    r"\((?:[^)]*)\)|\b(part[- ]time|full[- ]time|contract|temporary|permanent|acting|weekends?)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NormalisedTitle:
    title: str  # normalised, with seniority removed and synonyms applied
    seniority: str | None
    tokens: tuple[str, ...]


def normalise_title(raw: str) -> NormalisedTitle:
    text = unicodedata.normalize("NFKD", raw)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = _DROP.sub(" ", text)
    text = re.sub(r"[^a-z0-9&/ ]+", " ", text).replace("&", " and ").replace("/", " ")
    words = [ABBREVIATIONS.get(w, w) for w in text.split()]
    words = " ".join(words).split()
    seniority: str | None = None
    kept: list[str] = []
    for w in words:
        level = SENIORITY.get(w)
        if level is not None and seniority is None:
            seniority = level
        if level is None or w in KEEP_IN_TITLE:
            kept.append(w)
    # "software developer ii", "nurse grade 2"
    kept = [w for w in kept if w not in {"i", "ii", "iii", "iv", "1", "2", "3", "grade", "level"}]
    title = " ".join(kept)
    title = SYNONYMS.get(title, title)
    return NormalisedTitle(title=title, seniority=seniority, tokens=tuple(title.split()))


def normalise_experience(result: ExtractionResult) -> ExtractionResult:
    claims: list[ExtractedClaim] = []
    for claim in result.claims:
        if isinstance(claim.data, ExperienceData) and claim.data.title:
            norm = normalise_title(claim.data.title)
            claim = claim.model_copy(
                update={
                    "data": claim.data.model_copy(
                        update={"title_normalised": norm.title, "seniority": norm.seniority}
                    )
                }
            )
        claims.append(claim)
    return result.model_copy(update={"claims": tuple(claims)})
