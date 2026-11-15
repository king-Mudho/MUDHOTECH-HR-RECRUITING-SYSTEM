"""Deterministic criterion checks (P07-T01, docs/05 §8.1): qualification, certification/licence,
minimum experience and language.

Every result cites the claims it used. No evidence means ``missing`` - not assessable, never a
score of 0 (principle 3). Things a person must confirm (a foreign qualification, an expired
licence, roles without dates) come back as ``needs_verification`` with a middle score, so they
are neither silently accepted nor counted against the candidate.

Score bands: 100 strong/explicit and sufficient, 75 good, 50 partial, 25 weak/indirect.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from ai_engine.contracts import (
    CandidateEvidence,
    CertificationData,
    CriterionResult,
    CriterionSpec,
    CriterionType,
    EducationData,
    EmploymentKind,
    EvidenceRef,
    EvidenceStatus,
    ExperienceData,
    ExtractedClaim,
    LanguageData,
)
from ai_engine.normalisation.experience import DEFAULT_COUNTED, Role, summarise

YearMonth = tuple[int, int]
LANGUAGE_LEVELS = {  # coarse order for "fluent English" style requirements
    "basic": 1,
    "elementary": 1,
    "conversational": 2,
    "intermediate": 2,
    "working knowledge": 2,
    "proficient": 3,
    "advanced": 3,
    "fluent": 3,
    "courant": 3,
    "native": 4,
    "mother tongue": 4,
    "first language": 4,
    "natif": 4,
}


@dataclass(frozen=True)
class Context:
    """What rules need besides the evidence: today and the taxonomy's qualification ranks."""

    today: YearMonth
    level_ranks: Mapping[str, int]


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return re.sub(
        r"\s+", " ", "".join(c for c in text if not unicodedata.combining(c)).lower()
    ).strip()


def mentions(text: str, terms: Iterable[str]) -> bool:
    """Whole-phrase, case/accent-insensitive containment of any term."""
    hay = f" {re.sub(r'[^a-z0-9+#]+', ' ', fold(text))} "
    for term in terms:
        needle = re.sub(r"[^a-z0-9+#]+", " ", fold(term)).strip()
        if needle and f" {needle} " in hay:
            return True
    return False


def ref(evidence: CandidateEvidence, claim: ExtractedClaim) -> EvidenceRef:
    return EvidenceRef(claim_index=evidence.claims.index(claim), source=claim.source)


def missing(spec: CriterionSpec, reason: str = "no_evidence") -> CriterionResult:
    return CriterionResult(criterion_id=spec.id, status=EvidenceStatus.MISSING, reason=reason)


def months_score(months: int, required: int) -> int:
    """``min(1, months/required)`` mapped to bands (docs/05 §8.1)."""
    if required <= 0:
        return 100
    ratio = months / required
    if ratio >= 1:
        return 100
    if ratio >= 0.75:
        return 75
    if ratio >= 0.5:
        return 50
    return 25


def experience_months(
    evidence: CandidateEvidence,
    today: YearMonth,
    *,
    roles: Iterable[ExtractedClaim] | None = None,
    counted: frozenset[EmploymentKind] = DEFAULT_COUNTED,
) -> tuple[int, list[ExtractedClaim], int]:
    """(counted months, dated role claims, undated roles) over the given (or all) roles."""
    claims = list(roles) if roles is not None else list(evidence.of_type("experience"))
    dated: list[ExtractedClaim] = []
    role_list: list[Role] = []
    for claim in claims:
        data = claim.data
        if isinstance(data, ExperienceData):
            role_list.append(Role(data.dates, data.employment_kind))
            if data.dates.start is not None:
                dated.append(claim)
    summary = summarise(role_list, today, counted=counted)
    return summary.total_months, dated, summary.undated_roles


# --------------------------------------------------------------------------- qualification
def check_qualification(
    spec: CriterionSpec, evidence: CandidateEvidence, ctx: Context
) -> CriterionResult:
    required = spec.qualification_rank
    if required is None and spec.qualification_level:
        required = ctx.level_ranks.get(spec.qualification_level)
    field_terms = spec.equivalents
    best: tuple[int, ExtractedClaim, EducationData, bool] | None = None
    for claim in evidence.of_type("education"):
        data = claim.data
        if not isinstance(data, EducationData):
            continue
        rank = ctx.level_ranks.get(data.level or "", -1)
        field_ok = not field_terms or mentions(
            f"{data.qualification_text} {data.field}", field_terms
        )
        key = (rank, field_ok)
        if best is None or key > (best[0], best[3]):
            best = (rank, claim, data, field_ok)

    alternative = _equivalent_experience(spec, evidence, ctx)
    if best is None:
        return alternative or missing(spec)
    rank, claim, data, field_ok = best
    cite = (ref(evidence, claim),)
    if data.level is None:
        result = CriterionResult(
            criterion_id=spec.id,
            status=EvidenceStatus.NEEDS_VERIFICATION,
            score=50,
            confidence=0.4,
            evidence=cite,
            reason="level_unknown",
        )
        return _better(result, alternative)
    if required is None or rank >= required:
        if data.foreign or data.needs_verification:
            status, score, reason = EvidenceStatus.NEEDS_VERIFICATION, 75, "foreign_qualification"
        elif field_ok:
            status, score, reason = EvidenceStatus.EXPLICIT, 100, "meets_level"
        else:
            status, score, reason = EvidenceStatus.EXPLICIT, 50, "field_differs"
    else:
        gap = _levels_below(rank, required, ctx)
        status, score = EvidenceStatus.EXPLICIT, 50 if gap == 1 else 25
        reason = "rank_below_required"
    result = CriterionResult(
        criterion_id=spec.id,
        status=status,
        score=score,
        confidence=0.9 if status == EvidenceStatus.EXPLICIT else 0.6,
        evidence=cite,
        flags=("foreign_qualification",) if data.foreign else (),
        reason=reason,
    )
    return _better(result, alternative)


def _levels_below(rank: int, required: int, ctx: Context) -> int:
    distinct = sorted(set(ctx.level_ranks.values()))
    return sum(1 for r in distinct if rank < r <= required)


def _equivalent_experience(
    spec: CriterionSpec, evidence: CandidateEvidence, ctx: Context
) -> CriterionResult | None:
    """ "Or equivalent experience": ``min_months`` on a qualification criterion (docs/05 §8.1)."""
    if not spec.min_months:
        return None
    months, dated, _ = experience_months(evidence, ctx.today)
    if not dated or months < spec.min_months:
        return None
    return CriterionResult(
        criterion_id=spec.id,
        status=EvidenceStatus.INFERRED,
        score=75,
        method="equivalent_experience",
        confidence=0.6,
        evidence=tuple(ref(evidence, c) for c in dated[:5]),
        reason="equivalent_experience",
    )


def _better(a: CriterionResult, b: CriterionResult | None) -> CriterionResult:
    if b is None:
        return a
    return b if (b.score or 0) > (a.score or 0) else a


# --------------------------------------------------------------- certification / licence
def check_certification(
    spec: CriterionSpec, evidence: CandidateEvidence, ctx: Context
) -> CriterionResult:
    terms = (spec.title, *spec.equivalents)
    wanted_class = re.search(r"\bclass\s*([1-5])\b", " ".join(terms), re.IGNORECASE)
    hits: list[tuple[ExtractedClaim, CertificationData]] = []
    for claim in evidence.of_type("certification"):
        data = claim.data
        if not isinstance(data, CertificationData):
            continue
        if mentions(f"{data.name} {data.body}", terms) or _core_terms_match(spec, data):
            hits.append((claim, data))
    if not hits:
        return missing(spec)
    current = [(c, d) for c, d in hits if not _expired(d, ctx.today)]
    claim, data = (current or hits)[0]
    cite = (ref(evidence, claim),)
    if not current:
        return CriterionResult(
            criterion_id=spec.id,
            status=EvidenceStatus.NEEDS_VERIFICATION,
            score=50,
            confidence=0.6,
            evidence=cite,
            flags=("expired",),
            reason="expired",
        )
    if wanted_class and data.licence_class and int(data.licence_class) < int(wanted_class.group(1)):
        return CriterionResult(
            criterion_id=spec.id,
            status=EvidenceStatus.EXPLICIT,
            score=50,
            confidence=0.8,
            evidence=cite,
            reason="licence_class_below_required",
        )
    return CriterionResult(
        criterion_id=spec.id,
        status=EvidenceStatus.EXPLICIT,
        score=100,
        confidence=0.9,
        evidence=cite,
        reason="certified",
    )


_STOP = {
    "or",
    "and",
    "of",
    "the",
    "a",
    "in",
    "certificate",
    "certification",
    "registration",
    "licence",
    "license",
}


def _core_terms_match(spec: CriterionSpec, data: CertificationData) -> bool:
    """'Nurses Council registration' matches 'Nurses Council of Zimbabwe - practising certificate':
    every significant word of the criterion title appears in the certification."""
    words = [w for w in re.findall(r"[a-z0-9]+", fold(spec.title)) if w not in _STOP and len(w) > 1]
    hay = set(re.findall(r"[a-z0-9]+", fold(f"{data.name} {data.body}")))
    return bool(words) and all(w in hay for w in words)


def _expired(data: CertificationData, today: YearMonth) -> bool:
    if data.expires is None:
        return False
    return data.expires.ordinal(end=True) < today[0] * 12 + (today[1] - 1)


# ------------------------------------------------------------------------------ experience
def check_min_experience(
    spec: CriterionSpec,
    evidence: CandidateEvidence,
    ctx: Context,
    *,
    roles: Iterable[ExtractedClaim] | None = None,
    method: str = "rule",
    counted: frozenset[EmploymentKind] = DEFAULT_COUNTED,
) -> CriterionResult:
    """Months of (relevant) experience against ``min_months``. P07-T03 passes relevant roles."""
    role_claims = list(roles) if roles is not None else list(evidence.of_type("experience"))
    months, dated, undated = experience_months(
        evidence, ctx.today, roles=role_claims, counted=counted
    )
    if not dated:
        if undated:
            claims = role_claims
            return CriterionResult(
                criterion_id=spec.id,
                status=EvidenceStatus.NEEDS_VERIFICATION,
                score=50,
                confidence=0.3,
                evidence=tuple(ref(evidence, c) for c in claims[:5]),
                reason="roles_without_dates",
                method=method,
            )
        return missing(spec)
    required = spec.min_months or 0
    score = months_score(months, required)
    return CriterionResult(
        criterion_id=spec.id,
        status=EvidenceStatus.EXPLICIT,
        score=score,
        confidence=0.85 if not undated else 0.6,
        evidence=tuple(ref(evidence, c) for c in dated[:8]),
        flags=("some_roles_undated",) if undated else (),
        reason=f"months={months}/{required}",
        method=method,
    )


# -------------------------------------------------------------------------------- language
def check_language(
    spec: CriterionSpec, evidence: CandidateEvidence, ctx: Context
) -> CriterionResult:
    terms = (spec.title, *spec.equivalents)
    wanted_level = next(
        (lvl for name, lvl in LANGUAGE_LEVELS.items() if mentions(spec.title, [name])), 0
    )
    for claim in evidence.of_type("language"):
        data = claim.data
        if not isinstance(data, LanguageData) or not mentions(" ".join(terms), [data.language]):
            continue
        have = LANGUAGE_LEVELS.get(data.level, 0)
        score = 100 if not wanted_level or not have or have >= wanted_level else 75
        return CriterionResult(
            criterion_id=spec.id,
            status=EvidenceStatus.EXPLICIT,
            score=score,
            confidence=0.85 if have or not wanted_level else 0.6,
            evidence=(ref(evidence, claim),),
            reason="language_listed" if score == 100 else "level_below_required",
        )
    return missing(spec)


Rule = Callable[[CriterionSpec, CandidateEvidence, Context], CriterionResult]
RULES: dict[CriterionType, Rule] = {
    CriterionType.QUALIFICATION: check_qualification,
    CriterionType.CERTIFICATION: check_certification,
    CriterionType.LICENCE: check_certification,
    CriterionType.EXPERIENCE: check_min_experience,
    CriterionType.LANGUAGE: check_language,
}


def evaluate_rule(
    spec: CriterionSpec, evidence: CandidateEvidence, ctx: Context
) -> CriterionResult | None:
    """Result for rule-based criterion types; None for types handled elsewhere (skills, ...)."""
    rule = RULES.get(spec.type)
    return rule(spec, evidence, ctx) if rule else None
