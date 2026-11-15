"""Experience criteria (P07-T03, docs/05 §8.1, EC-AI-02, EC-DOC-18/21).

A role counts towards "N years of X" when it is relevant to the vacancy:

1. its normalised title equals the vacancy title or an equivalent title HR listed
   (``CriterionSpec.equivalents``) -> method ``title``;
2. otherwise its title, or its duties, share the key words of the vacancy/criterion
   (light stemming: "developer" ~ "development", "accountant" ~ "accounting") -> ``keywords``;
3. otherwise, when the local embedding model is loaded, title + duties are semantically similar
   to the vacancy at or above ``role_relevance_threshold`` -> ``semantic``.

Months of relevant roles are combined with an interval union (overlaps count once). Attachments,
internships and volunteer work count only when the rubric says so (``include_kinds``). Roles that
are not relevant are not ignored silently: when no role is relevant the result is weak, indirect
evidence (25) flagged ``relevance_uncertain`` for a person to look at - never a hard fail.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ai_engine.contracts import (
    CandidateEvidence,
    CriterionResult,
    CriterionSpec,
    EmploymentKind,
    EvidenceStatus,
    ExperienceData,
    ExtractedClaim,
)
from ai_engine.matching.config import DEFAULT_CONFIG, EngineConfig
from ai_engine.matching.rules import (
    Context,
    check_min_experience,
    fold,
    missing,
    ref,
)
from ai_engine.matching.semantic import EmbeddingService, cosine
from ai_engine.normalisation.experience import DEFAULT_COUNTED
from ai_engine.normalisation.titles import normalise_title

STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "or",
        "of",
        "the",
        "in",
        "for",
        "to",
        "with",
        "at",
        "on",
        "by",
        "as",
        "from",
        "years",
        "year",
        "yrs",
        "experience",
        "experienced",
        "relevant",
        "minimum",
        "least",
        "plus",
        "work",
        "working",
        "role",
        "roles",
        "job",
        "post",
        "position",
        "professional",
        "including",
        "related",
        "similar",
        "field",
        "etc",
        "using",
    ]
)
_SUFFIXES = (
    "ments",
    "ment",
    "ings",
    "ing",
    "ers",
    "er",
    "ants",
    "ant",
    "ists",
    "ist",
    "ions",
    "ion",
    "als",
    "al",
    "s",
)


@dataclass(frozen=True)
class JobContext:
    """The vacancy as relevance needs it (plain text; the adapter strips HTML)."""

    title: str
    responsibilities: str = ""


def stem(word: str) -> str:
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


# word-level synonyms for role nouns (not "engineer": a civil engineer is not a software developer)
WORD_SYNONYMS = {
    "programmer": "develop",
    "programm": "develop",
    "coder": "develop",
    "cod": "develop",
}


def keywords(text: str) -> set[str]:
    words = re.findall(r"[a-z][a-z+#]+", fold(text))
    stems = {stem(w) for w in words if w not in STOP and len(w) > 2}
    return {WORD_SYNONYMS.get(w, w) for w in stems}


@dataclass(frozen=True)
class Relevance:
    claim: ExtractedClaim
    relevant: bool
    method: str
    score: float


def role_relevance(
    claim: ExtractedClaim,
    spec: CriterionSpec,
    job: JobContext,
    *,
    semantic: EmbeddingService | None = None,
    config: EngineConfig = DEFAULT_CONFIG,
) -> Relevance:
    data = claim.data
    if not isinstance(data, ExperienceData):
        return Relevance(claim, False, "none", 0.0)
    role_title = data.title_normalised or normalise_title(data.title).title
    targets = {normalise_title(t).title for t in (job.title, *spec.equivalents) if t.strip()}
    if role_title and role_title in targets:
        return Relevance(claim, True, "title", 1.0)

    target_title_words = set().union(*(keywords(t) for t in targets)) if targets else set()
    criterion_words = keywords(f"{spec.title} {spec.description}")
    title_words = keywords(f"{role_title} {data.title}")
    if target_title_words:
        overlap = len(title_words & target_title_words) / len(target_title_words)
        if overlap >= 0.5:
            return Relevance(claim, True, "keywords", round(overlap, 3))
    if criterion_words and title_words & criterion_words:
        return Relevance(claim, True, "keywords", 0.6)
    duty_words = keywords(" ".join(data.responsibilities))
    focus = criterion_words | target_title_words | keywords(job.responsibilities)
    if len(duty_words & focus) >= 3:
        return Relevance(claim, True, "keywords", 0.6)

    if semantic is not None:
        query = semantic.embed_one(f"{job.title}. {spec.title}. {spec.description}")
        role_text = f"{data.title}. " + " ".join(data.responsibilities[:5])
        similarity = cosine(query, semantic.embed_one(role_text))
        if similarity >= config.role_relevance_threshold:
            return Relevance(claim, True, "semantic", round(similarity, 3))
        return Relevance(claim, False, "semantic", round(similarity, 3))
    return Relevance(claim, False, "keywords", 0.0)


def match_experience(
    spec: CriterionSpec,
    evidence: CandidateEvidence,
    ctx: Context,
    job: JobContext,
    *,
    semantic: EmbeddingService | None = None,
    config: EngineConfig = DEFAULT_CONFIG,
    include_kinds: Iterable[EmploymentKind] = (),
) -> CriterionResult:
    roles = list(evidence.of_type("experience"))
    if not roles:
        return missing(spec)
    counted = DEFAULT_COUNTED | frozenset(include_kinds)
    judged = [role_relevance(r, spec, job, semantic=semantic, config=config) for r in roles]
    relevant = [j.claim for j in judged if j.relevant]
    if not relevant:
        return CriterionResult(
            criterion_id=spec.id,
            status=EvidenceStatus.EXPLICIT,
            score=25,
            method="keywords" if semantic is None else "semantic",
            confidence=0.3,
            evidence=tuple(ref(evidence, r) for r in roles[:5]),
            flags=("relevance_uncertain",),
            reason="no_relevant_roles",
        )
    result = check_min_experience(
        spec, evidence, ctx, roles=relevant, method=_method(judged), counted=counted
    )
    only_uncounted = _only_uncounted(relevant, counted)
    if only_uncounted and result.status != EvidenceStatus.MISSING:
        return result.model_copy(
            update={
                "score": 25,
                "status": EvidenceStatus.EXPLICIT,
                "flags": (*result.flags, "only_attachment_internship_or_volunteer"),
                "reason": "not_counted_by_rubric",
                "evidence": result.evidence or tuple(ref(evidence, r) for r in relevant[:5]),
            }
        )
    if result.assessable and len(relevant) < len(roles):
        result = result.model_copy(update={"flags": (*result.flags, "some_roles_not_relevant")})
    return result


def _method(judged: Sequence[Relevance]) -> str:
    methods = {j.method for j in judged if j.relevant}
    for m in ("semantic", "keywords", "title"):
        if m in methods:
            return m  # the weakest method used decides how sure we are
    return "title"


def _only_uncounted(roles: Sequence[ExtractedClaim], counted: frozenset[EmploymentKind]) -> bool:
    kinds = {r.data.employment_kind for r in roles if isinstance(r.data, ExperienceData)}
    return bool(kinds) and not (kinds & counted) and EmploymentKind.PART_TIME not in kinds
