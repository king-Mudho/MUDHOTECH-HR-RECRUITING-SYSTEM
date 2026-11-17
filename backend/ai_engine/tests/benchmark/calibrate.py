"""Threshold calibration on the labelled synthetic corpus (P10-T03, docs/05 §8.3).

    python -m ai_engine.tests.benchmark.calibrate --out-dir ../docs/reports [--semantic]

Every readable, text-based CV is extracted once. Each candidate configuration is then evaluated
against two rubrics per role:

* ``corpus``  - the generator's rubric (skills + qualification + years of experience);
* ``vacancy`` - a skills-heavy rubric written the way HR writes vacancies (the demo Software
  Developer vacancy is the model): the role's skills as essentials, one "demonstrable related
  work" experience criterion, and two preferred criteria that CVs rarely evidence. This is the
  shape that exposed D-008 (suitable developers routed to *lower match*).

Per configuration it reports recall of gold-*suitable* candidates in recommended or review needed
(target >= 0.95), the share of suitable candidates *recommended*, and gold-*not suitable*
candidates *recommended* (must stay 0). Writes ``calibration_<date>.md`` + ``.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from itertools import product
from pathlib import Path
from typing import Any

from ai_engine.contracts import CriterionSpec, CriterionType, ExtractionResult, Importance
from ai_engine.evaluation.bands import LOWER, RECOMMENDED, REVIEW
from ai_engine.evaluation.engine import evaluate
from ai_engine.evaluation.scoring import CategorySpec
from ai_engine.extraction.parser import Semantic
from ai_engine.matching.config import DEFAULT_CONFIG, EngineConfig
from ai_engine.matching.semantic import EmbeddingService

from .corpus import (
    CORPUS,
    SKILLS,
    criteria_for,
    evaluation_input,
    extract,
    readable_cvs,
    taxonomy,
)
from .run_extraction_benchmark import semantic_matcher

VACANCY_CATEGORIES = (
    CategorySpec(key="technical", label="Technical skills", weight=70),
    CategorySpec(key="experience", label="Relevant experience", weight=30),
)
# Preferred extras of the kind HR adds; most CVs do not evidence them (missing = not assessable).
EXTRAS = {
    "software_developer": ("REST API design", "Cloud deployment"),
    "accountant": ("Audit exposure", "Tax returns"),
    "registered_nurse": ("Theatre experience", "Community outreach"),
    "data_analyst": ("Dashboard design", "Python scripting"),
    "hr_officer": ("Employee wellness programmes", "HRIS administration"),
}


def vacancy_criteria(cv: dict[str, Any]) -> tuple[CriterionSpec, ...]:
    out: list[CriterionSpec] = []
    for item in cv["criteria"]:
        if item["kind"] != "skill":
            continue
        title, skill_id, equivalents = SKILLS[item["id"]]
        out.append(
            CriterionSpec(
                id=f"v_{item['id']}",
                importance=Importance.ESSENTIAL,
                type=CriterionType.SKILL,
                title=title,
                skill_id=skill_id,
                equivalents=equivalents,
                category="technical",
            )
        )
    out.append(
        CriterionSpec(
            id="v_related_work",
            importance=Importance.ESSENTIAL,
            type=CriterionType.EXPERIENCE,
            title="Demonstrable related work",
            min_months=12,
            category="experience",
        )
    )
    for i, title in enumerate(EXTRAS[cv["role"]]):
        out.append(
            CriterionSpec(
                id=f"v_extra_{i}",
                importance=Importance.PREFERRED,
                type=CriterionType.SKILL,
                title=title,
                category="technical",
            )
        )
    return tuple(out)


def _bands(
    extracted: list[tuple[dict[str, Any], ExtractionResult]],
    config: EngineConfig,
    rubric: str,
    semantic: EmbeddingService | None,
) -> dict[str, Counter[str]]:
    graph = taxonomy().graph
    confusion: dict[str, Counter[str]] = {}
    for cv, result in extracted:
        inp = evaluation_input(cv, result)
        if rubric == "vacancy":
            inp = inp.model_copy(
                update={"criteria": vacancy_criteria(cv), "categories": VACANCY_CATEGORIES}
            )
        else:
            inp = inp.model_copy(update={"criteria": criteria_for(cv)})
        inp = inp.model_copy(update={"config": config})
        band = evaluate(inp, graph=graph, semantic=semantic).band
        confusion.setdefault(cv["hr_reference_suitability"], Counter())[band] += 1
    return confusion


def _metrics(confusion: dict[str, Counter[str]]) -> dict[str, Any]:
    suitable = confusion.get("suitable", Counter())
    n = sum(suitable.values()) or 1
    not_suitable = confusion.get("not_suitable", Counter())
    return {
        "recall": (suitable[RECOMMENDED] + suitable[REVIEW]) / n,
        "recommended": suitable[RECOMMENDED] / n,
        "suitable_lower": suitable[LOWER],
        "not_suitable_recommended": not_suitable[RECOMMENDED],
        "confusion": {k: dict(v) for k, v in confusion.items()},
    }


def run(
    listed: list[int],
    thresholds: list[float],
    semantic: EmbeddingService | None,
    matcher: Semantic | None = None,
) -> dict[str, Any]:
    extracted = [
        (cv, extract((CORPUS / cv["file"]).read_bytes(), cv["id"], semantic=matcher))
        for cv in readable_cvs()
        if not cv["needs_ocr"]
    ]
    rows = []
    for listed_score, threshold in product(listed, thresholds):
        config = DEFAULT_CONFIG.model_copy(
            update={"skill_listed_only": listed_score, "semantic_skill_threshold": threshold}
        )
        row: dict[str, Any] = {"skill_listed_only": listed_score, "semantic_threshold": threshold}
        for rubric in ("corpus", "vacancy"):
            row[rubric] = _metrics(_bands(extracted, config, rubric, semantic))
        rows.append(row)
    return {
        "date": date.today().isoformat(),
        "cvs": len(extracted),
        "semantic": semantic is not None,
        "baseline": {
            "skill_listed_only": DEFAULT_CONFIG.skill_listed_only,
            "semantic_threshold": DEFAULT_CONFIG.semantic_skill_threshold,
        },
        "rows": rows,
    }


def acceptable(row: dict[str, Any]) -> bool:
    return all(
        row[r]["recall"] >= 0.95 and row[r]["not_suitable_recommended"] == 0
        for r in ("corpus", "vacancy")
    )


def markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Threshold calibration — {report['date']}",
        "",
        "Generated by `python -m ai_engine.tests.benchmark.calibrate` (P10-T03). Synthetic corpus "
        f"only: {report['cvs']} readable text CVs, five roles. Semantic matching: "
        f"**{'on' if report['semantic'] else 'off'}**.",
        "",
        "Recall = gold *suitable* in recommended or review needed (target ≥ 95 %). "
        "*Rec.* = share of suitable recommended. *NS rec.* = gold *not suitable* recommended "
        "(must be 0). ✅ = acceptable on both rubrics.",
        "",
        "| Listed-only score | Semantic threshold | Corpus recall | Corpus rec. | Corpus NS rec. "
        "| Vacancy recall | Vacancy rec. | Vacancy NS rec. | OK |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in report["rows"]:
        c, v = row["corpus"], row["vacancy"]
        lines.append(
            f"| {row['skill_listed_only']} | {row['semantic_threshold']:.2f} "
            f"| {c['recall']:.0%} | {c['recommended']:.0%} | {c['not_suitable_recommended']} "
            f"| {v['recall']:.0%} | {v['recommended']:.0%} | {v['not_suitable_recommended']} "
            f"| {'✅' if acceptable(row) else '—'} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=".")
    parser.add_argument("--semantic", action="store_true", help="Use the local embedding model")
    parser.add_argument("--listed", default="50,75")
    parser.add_argument("--thresholds", default="0.78")
    args = parser.parse_args(argv)
    semantic: EmbeddingService | None = None
    matcher = semantic_matcher(args.semantic)
    if matcher is not None:
        from ai_engine.matching.semantic import DEFAULT_MODEL, get_encoder

        semantic = EmbeddingService(get_encoder(DEFAULT_MODEL))
    report = run(
        [int(x) for x in args.listed.split(",")],
        [float(x) for x in args.thresholds.split(",")],
        semantic,
        matcher,
    )
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = out / f"calibration_{report['date']}"
    stem.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    stem.with_suffix(".md").write_text(markdown(report), encoding="utf-8")
    sys.stdout.buffer.write(markdown(report).encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
