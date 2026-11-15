"""Skill criteria (P07-T02, docs/05 §8.1, EC-AI-01, EC-DOC-24).

Cascade, strongest first: **exact** (same taxonomy skill, written as its name) -> **alias** (same
skill under another name, or a criterion equivalent written in the CV) -> **relation** (the
taxonomy says the candidate's skill implies, or is a narrower form of, the required one; a
``related`` skill is weak, indirect evidence) -> **semantic** (local embeddings, similarity at or
above the configured threshold). The method, a confidence and the cited claims are recorded.

How the skill appears matters (EC-DOC-24): used in a role or project scores higher than mentioned
in the profile, which scores higher than only listed under "Skills". Inferred matches are capped.
No match at all is ``missing`` - unknown, not a fail.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from ai_engine.contracts import (
    CandidateEvidence,
    CriterionResult,
    CriterionSpec,
    EvidenceStatus,
    ExtractedClaim,
    SectionKind,
    SkillData,
)
from ai_engine.matching.config import DEFAULT_CONFIG, EngineConfig
from ai_engine.matching.rules import fold, mentions, missing, ref
from ai_engine.matching.semantic import EmbeddingService, cosine

USED = frozenset({SectionKind.EXPERIENCE, SectionKind.ATTACHMENT, SectionKind.PROJECTS})
MENTIONED = frozenset(
    {
        SectionKind.PROFILE,
        SectionKind.ACHIEVEMENTS,
        SectionKind.CERTIFICATIONS,
        SectionKind.EDUCATION,
    }
)
STRONG_RELATIONS = ("implies", "narrower")


@dataclass(frozen=True)
class SkillGraph:
    """Taxonomy relations as (from_id, to_id, relation): ``A implies B``, ``A narrower B``,
    ``A related B``, ``A broader B``."""

    edges: tuple[tuple[str, str, str], ...] = ()
    _out: dict[str, list[tuple[str, str]]] = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def build(cls, edges: Iterable[tuple[str, str, str]]) -> SkillGraph:
        graph = cls(tuple(edges))
        for a, b, rel in graph.edges:
            graph._out.setdefault(a, []).append((b, rel))
        return graph

    def leads_to(self, start: str, target: str, *, max_hops: int = 3) -> str | None:
        """Strongest relation path from ``start`` to ``target`` (implies/narrower chains, else
        a direct or symmetric ``related`` link)."""
        frontier, seen = [start], {start}
        for _ in range(max_hops):
            nxt: list[str] = []
            for node in frontier:
                for to, rel in self._out.get(node, []):
                    if rel not in STRONG_RELATIONS or to in seen:
                        continue
                    if to == target:
                        return "relation"
                    seen.add(to)
                    nxt.append(to)
            frontier = nxt
        related = any(rel == "related" and {a, b} == {start, target} for a, b, rel in self.edges)
        return "related" if related else None


def usage_score(claim: ExtractedClaim, config: EngineConfig) -> int:
    section = claim.section
    if section in USED:
        return config.skill_used
    if section in MENTIONED:
        return config.skill_mentioned
    return config.skill_listed_only


@dataclass
class _Hit:
    claim: ExtractedClaim
    method: str
    score: int
    confidence: float
    status: EvidenceStatus


def _skill_claims(evidence: CandidateEvidence) -> list[ExtractedClaim]:
    return [c for c in evidence.of_type("skill") if isinstance(c.data, SkillData)]


def match_skill(
    spec: CriterionSpec,
    evidence: CandidateEvidence,
    *,
    graph: SkillGraph | None = None,
    semantic: EmbeddingService | None = None,
    config: EngineConfig = DEFAULT_CONFIG,
) -> CriterionResult:
    graph = graph or SkillGraph()
    names = (spec.title, *spec.equivalents)
    hits: list[_Hit] = []
    claims = _skill_claims(evidence)
    for claim in claims:
        data = claim.data
        if not isinstance(data, SkillData):  # narrowed by _skill_claims; keeps mypy happy
            continue
        base = usage_score(claim, config)
        same_skill = spec.skill_id is not None and data.skill_id == spec.skill_id
        if same_skill:
            method = "exact" if fold(data.raw) == fold(data.canonical or data.raw) else "alias"
            hits.append(_Hit(claim, method, base, 0.95, EvidenceStatus.EXPLICIT))
            continue
        if mentions(f"{data.raw} {data.canonical or ''}", spec.equivalents) or (
            spec.skill_id is None and mentions(f"{data.raw} {data.canonical or ''}", names)
        ):
            hits.append(_Hit(claim, "alias", base, 0.85, EvidenceStatus.EXPLICIT))
            continue
        if spec.skill_id and data.skill_id:
            link = graph.leads_to(data.skill_id, spec.skill_id)
            if link == "relation":
                hits.append(
                    _Hit(
                        claim,
                        "relation",
                        min(base, config.relation_cap),
                        0.7,
                        EvidenceStatus.INFERRED,
                    )
                )
            elif link == "related":
                hits.append(
                    _Hit(claim, "related", config.related_score, 0.4, EvidenceStatus.INFERRED)
                )
    if not any(h.method in ("exact", "alias", "relation") for h in hits) and semantic is not None:
        hits += _semantic_hits(spec, claims, semantic, config)
    if not hits:
        return missing(spec)
    rank = {"exact": 4, "alias": 3, "relation": 2, "semantic": 1, "related": 0}
    hits.sort(key=lambda h: (h.score, rank[h.method], h.confidence), reverse=True)
    best = hits[0]
    cited = [h for h in hits if h.method == best.method][:3]
    return CriterionResult(
        criterion_id=spec.id,
        status=best.status,
        score=best.score,
        method=best.method,
        confidence=round(best.confidence, 3),
        evidence=tuple(ref(evidence, h.claim) for h in cited),
        reason="listed_only"
        if best.score == config.skill_listed_only
        and best.method
        in (
            "exact",
            "alias",
        )
        else best.method,
    )


def _semantic_hits(
    spec: CriterionSpec,
    claims: Sequence[ExtractedClaim],
    semantic: EmbeddingService,
    config: EngineConfig,
) -> list[_Hit]:
    if not claims:
        return []
    query = semantic.embed_one(" / ".join((spec.title, *spec.equivalents)))
    texts = [c.data.raw if isinstance(c.data, SkillData) else "" for c in claims]
    vectors = semantic.embed(texts)
    out = []
    for claim, vector in zip(claims, vectors, strict=True):
        similarity = cosine(query, vector)
        if similarity >= config.semantic_skill_threshold:
            out.append(
                _Hit(
                    claim,
                    "semantic",
                    min(usage_score(claim, config), config.semantic_cap),
                    round(similarity, 3),
                    EvidenceStatus.INFERRED,
                )
            )
    return out
