"""Skill criteria (P07-T02): exact -> alias -> relation -> semantic; listed vs used (EC-DOC-24)."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from ai_engine.contracts import (
    CandidateEvidence,
    ClaimSource,
    CriterionSpec,
    CriterionType,
    EvidenceStatus,
    ExtractedClaim,
    ExtractionMethod,
    Importance,
    SectionKind,
    SkillData,
)
from ai_engine.extraction.extract import extract_document
from ai_engine.extraction.parser import extract_claims
from ai_engine.extraction.skills import SkillIndex
from ai_engine.matching.config import EngineConfig
from ai_engine.matching.semantic import EmbeddingService, HashingEncoder
from ai_engine.matching.skills_match import SkillGraph, match_skill

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "fixtures" / "synthetic_cvs"
K = SectionKind


def skill(
    raw: str, skill_id: str | None, section: SectionKind = K.SKILLS, canonical: str | None = None
) -> ExtractedClaim:
    return ExtractedClaim(
        data=SkillData(
            raw=raw, skill_id=skill_id, canonical=canonical or (raw if skill_id else None)
        ),
        source=ClaimSource(snippet=raw, document_id="d", page=1, char_start=0, char_end=len(raw)),
        method=ExtractionMethod.TAXONOMY,
        confidence=0.8,
        section=section,
    )


def ev(*claims: ExtractedClaim) -> CandidateEvidence:
    return CandidateEvidence(application_id="a", claims=claims)


def criterion(title: str, skill_id: str | None = None, **kw: Any) -> CriterionSpec:
    return CriterionSpec(
        id="c",
        type=CriterionType.SKILL,
        title=title,
        skill_id=skill_id,
        importance=Importance.ESSENTIAL,
        **kw,
    )


GRAPH = SkillGraph.build(
    [
        ("Django", "Python", "implies"),
        ("Django REST Framework", "Django", "implies"),
        ("Amazon EC2", "AWS", "narrower"),
        ("AWS", "Cloud computing", "narrower"),
        ("Kubernetes", "Docker", "related"),
        ("Cloud computing", "AWS", "broader"),
    ]
)


def test_usage_decides_the_band() -> None:
    """EC-DOC-24: listed only 50, mentioned in profile 75, used in a role/project 100."""
    c = criterion("Python", "Python")
    assert match_skill(c, ev(skill("Python", "Python"))).score == 50
    assert match_skill(c, ev(skill("Python", "Python", K.PROFILE))).score == 75
    used = match_skill(c, ev(skill("Python", "Python", K.EXPERIENCE)))
    assert used.score == 100 and used.method == "exact" and used.status == EvidenceStatus.EXPLICIT
    project = match_skill(c, ev(skill("Python", "Python", K.PROJECTS)))
    assert project.score == 100
    listed = match_skill(c, ev(skill("Python", "Python")))
    assert listed.reason == "listed_only"


# EC-AI-01: equivalent skill present -> alias/relation/semantic match, method recorded
def test_alias_and_equivalents() -> None:
    alias = match_skill(
        criterion("Python", "Python"), ev(skill("python3", "Python", canonical="Python"))
    )
    assert alias.method == "alias" and alias.score == 50
    either = criterion(
        "Django or similar web framework", "Django", equivalents=("Flask", "FastAPI")
    )
    flask = match_skill(either, ev(skill("Flask", "Flask", K.EXPERIENCE)))
    assert flask.method == "alias" and flask.score == 100
    raw = match_skill(
        criterion("Labour Act knowledge", None, equivalents=("Labour Act",)),
        ev(skill("Labour Act", None)),
    )
    assert raw.method == "alias" and raw.status == EvidenceStatus.EXPLICIT


def test_relations_are_inferred_and_capped() -> None:
    py = match_skill(
        criterion("Python", "Python"), ev(skill("Django", "Django", K.EXPERIENCE)), graph=GRAPH
    )
    assert py.method == "relation" and py.status == EvidenceStatus.INFERRED and py.score == 75
    chain = match_skill(
        criterion("Python", "Python"),
        ev(skill("Django REST Framework", "Django REST Framework")),
        graph=GRAPH,
    )
    assert chain.method == "relation" and chain.score == 50  # listed only, still below the cap
    cloud = match_skill(
        criterion("Cloud computing", "Cloud computing"),
        ev(skill("Amazon EC2", "Amazon EC2", K.EXPERIENCE)),
        graph=GRAPH,
    )
    assert cloud.method == "relation"
    related = match_skill(
        criterion("Docker", "Docker"),
        ev(skill("Kubernetes", "Kubernetes", K.EXPERIENCE)),
        graph=GRAPH,
    )
    assert related.method == "related" and related.score == 25  # weak, indirect
    broader = match_skill(
        criterion("AWS", "AWS"), ev(skill("Cloud computing", "Cloud computing")), graph=GRAPH
    )
    assert broader.status == EvidenceStatus.MISSING  # knowing "cloud" doesn't show AWS


def test_strongest_evidence_wins_and_is_cited() -> None:
    result = match_skill(
        criterion("Python", "Python"),
        ev(
            skill("Django", "Django", K.EXPERIENCE),
            skill("Python", "Python"),
            skill("Python", "Python", K.EXPERIENCE),
        ),
        graph=GRAPH,
    )
    assert result.method == "exact" and result.score == 100
    assert [e.claim_index for e in result.evidence] == [2, 1]


def test_missing_is_unknown_not_zero() -> None:
    result = match_skill(
        criterion("Rust", "Rust"), ev(skill("Python", "Python", K.EXPERIENCE)), graph=GRAPH
    )
    assert result.status == EvidenceStatus.MISSING and result.score is None


def test_semantic_fallback_threshold() -> None:
    svc = EmbeddingService(HashingEncoder())
    c = criterion("Data visualisation", "Data visualisation")
    close = ev(skill("data visualisations and dashboards", None))
    low = EngineConfig(semantic_skill_threshold=0.3)
    hit = match_skill(c, close, semantic=svc, config=low)
    assert hit.method == "semantic" and hit.status == EvidenceStatus.INFERRED and hit.score == 50
    assert 0.3 <= hit.confidence <= 1
    assert (
        match_skill(c, ev(skill("Wound care", None)), semantic=svc, config=low).status
        == EvidenceStatus.MISSING
    )
    strict = EngineConfig(semantic_skill_threshold=0.99)
    assert match_skill(c, close, semantic=svc, config=strict).status == EvidenceStatus.MISSING
    # an exact match never consults the model
    exact = match_skill(
        c, ev(skill("Data visualisation", "Data visualisation")), semantic=svc, config=low
    )
    assert exact.method == "exact"


# ---------------------------------------------------------------------------------- corpus
@cache
def taxonomy() -> tuple[SkillIndex, SkillGraph]:
    doc = json.loads((ROOT / "fixtures/taxonomy/skills.json").read_text(encoding="utf-8"))
    return (
        SkillIndex.from_taxonomy([dict(s, id=s["name"]) for s in doc["skills"]]),
        SkillGraph.build((r["from"], r["to"], r["relation"]) for r in doc["relations"]),
    )


CORPUS_CRITERIA = {  # generator SKILL_CRITERIA as rubric criteria
    "python": ("Python", "Python", ()),
    "web_framework": ("Django or similar web framework", "Django", ("Flask", "FastAPI")),
    "sql": ("SQL database experience", "SQL", ("PostgreSQL",)),
    "vcs": ("Version control (Git)", "Git", ()),
    "ifrs": ("IFRS reporting", "IFRS", ()),
    "accounting_software": (
        "Accounting software (Pastel/Sage)",
        "Pastel",
        ("Sage Evolution", "Sage"),
    ),
    "reconciliations": ("Reconciliations", "Bank reconciliation", ()),
    "bi_tool": ("BI tool (Power BI/Tableau)", "Power BI", ("Tableau",)),
    "statistics": ("Statistics", "Statistics", ()),
    "labour_law": ("Knowledge of the Labour Act", "Labour law", ()),
    "recruitment": ("Recruitment", "Recruitment", ()),
    "payroll": ("Payroll", "Payroll", ()),
}


@pytest.mark.skipif(not CORPUS.exists(), reason="synthetic corpus missing")
def test_corpus_skill_criteria_agree_with_gold() -> None:
    """Every skill the gold labels mark as met is found; nothing is credited from the skills
    list when the gold says it is not listed. Extra evidence (profile/duty mentions, Django =>
    Python, weak "related" links) is real CV content the list-based labels don't count.
    Synonym-only CVs need the embedding model (measured in the P07-T15 benchmark)."""
    index, graph = taxonomy()
    labels = json.loads((CORPUS / "labels.json").read_text(encoding="utf-8"))["cvs"]
    met = met_found = 0
    extra: list[tuple[str, str, str, int | None]] = []
    false_listed = []
    for cv in labels:
        if (
            cv["parse_expected"] != "ok"
            or cv["needs_ocr"]
            or "equivalent_wording" in cv["variations"]
        ):
            continue
        result = extract_claims(
            extract_document((CORPUS / cv["file"]).read_bytes(), document_id=cv["id"]),
            today=(2026, 10),
            skills=index,
        )
        evidence = CandidateEvidence.from_results(cv["id"], [result])
        for item in cv["criteria"]:
            if item["kind"] != "skill" or item["id"] not in CORPUS_CRITERIA:
                continue
            title, skill_id, equivalents = CORPUS_CRITERIA[item["id"]]
            got = match_skill(
                criterion(title, skill_id, equivalents=equivalents), evidence, graph=graph
            )
            if cv["expected_evidence"][item["id"]] == "met":
                met += 1
                met_found += got.assessable
            elif got.assessable:
                # gold counts only the skills list; other evidence must not come from that list
                extra.append((cv["file"], item["id"], got.method, got.score))
                if got.reason == "listed_only":
                    false_listed.append((cv["file"], item["id"]))
    assert met > 150 and met_found / met >= 0.98, (met, met_found)
    assert false_listed == []
    assert all(m != "exact" or (s is not None and s > 50) for _, _, m, s in extra)  # mentions
