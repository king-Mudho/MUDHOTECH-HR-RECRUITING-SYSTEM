"""Shared corpus helpers: run extraction once per CV and evaluate it against its role rubric.

The rubrics mirror the generator's criteria (``scripts/generate_synthetic_cvs.py``) so the gold
``expected_evidence`` and ``hr_reference_suitability`` labels can be compared with the engine.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from ai_engine.contracts import (
    CandidateEvidence,
    CriterionSpec,
    CriterionType,
    ExtractionResult,
    Importance,
)
from ai_engine.evaluation.engine import EvaluationInput, EvaluationResult, evaluate
from ai_engine.evaluation.scoring import CategorySpec
from ai_engine.extraction.extract import extract_document
from ai_engine.extraction.parser import Semantic, extract_claims
from ai_engine.extraction.pii import protect
from ai_engine.extraction.skills import SkillIndex
from ai_engine.matching.semantic import EmbeddingService
from ai_engine.matching.skills_match import SkillGraph
from ai_engine.normalisation.qualifications import QualificationIndex, normalise_education
from ai_engine.normalisation.titles import normalise_experience

BACKEND = Path(__file__).resolve().parents[3]
CORPUS = BACKEND / "fixtures" / "synthetic_cvs"
TAXONOMY = BACKEND / "fixtures" / "taxonomy"
TODAY = (2026, 10)
JOB_TITLES = {
    "software_developer": "Software Developer",
    "accountant": "Accountant",
    "registered_nurse": "Registered Nurse",
    "data_analyst": "Data Analyst",
    "hr_officer": "Human Resources Officer",
}
SKILLS = {  # criterion id -> (title, taxonomy skill, accepted equivalents)
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
CERTS = {"council_registration": "Nurses Council registration", "bls": "Basic Life Support"}
CATEGORIES = (
    CategorySpec(key="technical", label="Technical skills", weight=45),
    CategorySpec(key="experience", label="Relevant experience", weight=30),
    CategorySpec(key="qualification", label="Qualifications", weight=25),
)


@dataclass(frozen=True)
class Taxonomy:
    skills: SkillIndex
    qualifications: QualificationIndex
    graph: SkillGraph
    ranks: dict[str, int]


@cache
def taxonomy() -> Taxonomy:
    skills = json.loads((TAXONOMY / "skills.json").read_text(encoding="utf-8"))
    quals = json.loads((TAXONOMY / "qualifications.json").read_text(encoding="utf-8"))
    return Taxonomy(
        skills=SkillIndex.from_taxonomy([dict(s, id=s["name"]) for s in skills["skills"]]),
        qualifications=QualificationIndex.from_taxonomy(
            quals["levels"], quals["professional_bodies"]
        ),
        graph=SkillGraph.build((r["from"], r["to"], r["relation"]) for r in skills["relations"]),
        ranks={lvl["code"]: lvl["rank"] for lvl in quals["levels"]},
    )


@cache
def labels() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((CORPUS / "labels.json").read_text(encoding="utf-8"))
    return data


def criteria_for(cv: dict[str, Any]) -> tuple[CriterionSpec, ...]:
    out = []
    for item in cv["criteria"]:
        importance = Importance.ESSENTIAL if item["essential"] else Importance.PREFERRED
        common = {"id": item["id"], "importance": importance}
        if item["kind"] == "skill":
            title, skill_id, equivalents = SKILLS[item["id"]]
            out.append(
                CriterionSpec(
                    **common,
                    type=CriterionType.SKILL,
                    title=title,
                    skill_id=skill_id,
                    equivalents=equivalents,
                    category="technical",
                )
            )
        elif item["kind"] == "qualification":
            out.append(
                CriterionSpec(
                    **common,
                    type=CriterionType.QUALIFICATION,
                    title=item["label"],
                    qualification_level="ZW_ND",
                    category="qualification",
                )
            )
        elif item["kind"] == "certification":
            out.append(
                CriterionSpec(
                    **common,
                    type=CriterionType.CERTIFICATION,
                    title=CERTS[item["id"]],
                    category="qualification",
                )
            )
        else:
            years = int("".join(ch for ch in item["id"] if ch.isdigit()))
            out.append(
                CriterionSpec(
                    **common,
                    type=CriterionType.EXPERIENCE,
                    title=item["label"],
                    min_months=years * 12,
                    category="experience",
                )
            )
    return tuple(out)


def extract(data: bytes, document_id: str, semantic: Semantic | None = None) -> ExtractionResult:
    tax = taxonomy()
    result = extract_document(data, document_id=document_id)
    result = extract_claims(result, today=TODAY, skills=tax.skills, semantic=semantic)
    return protect(normalise_experience(normalise_education(result, tax.qualifications)))


def evaluation_input(cv: dict[str, Any], result: ExtractionResult) -> EvaluationInput:
    tax = taxonomy()
    quality = result.document.quality_score if result.document else None
    return EvaluationInput(
        application_id=cv["id"],
        evidence=CandidateEvidence.from_results(cv["id"], [result]),
        criteria=criteria_for(cv),
        categories=CATEGORIES,
        job_title=JOB_TITLES[cv["role"]],
        today=TODAY,
        level_ranks=tax.ranks,
        quality=quality,
    )


def evaluate_cv(
    cv: dict[str, Any], data: bytes | None = None, semantic: EmbeddingService | None = None
) -> tuple[EvaluationInput, EvaluationResult, ExtractionResult]:
    raw = data if data is not None else (CORPUS / cv["file"]).read_bytes()
    result = extract(raw, cv["id"])
    inp = evaluation_input(cv, result)
    return inp, evaluate(inp, graph=taxonomy().graph, semantic=semantic), result


def readable_cvs() -> Iterator[dict[str, Any]]:
    for cv in labels()["cvs"]:
        if cv["parse_expected"] == "ok":
            yield cv
