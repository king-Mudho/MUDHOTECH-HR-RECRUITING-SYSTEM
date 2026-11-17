"""Fairness benchmark at scale (P10-T04, EC-AI-13, docs/05 §13).

    python -m ai_engine.tests.benchmark.run_fairness_benchmark --out-dir ../docs/reports --check

Every readable text CV of the synthetic corpus is re-rendered by the generator
(``scripts/generate_synthetic_cvs.py``) with one change at a time and evaluated again. The score,
coverage, band, confidence and every criterion result must be identical to the original:

* ``identity``            - name and gender swapped (4 swaps crossing gender, language and region);
* ``protected_details``   - a personal-details block with date of birth, gender, marital status,
  religion, tribe, health/disability, HIV status and political affiliation added;
* ``location``            - home town, job towns and school town moved to rural districts;
* ``institution``         - the school replaced by another of the same type and level
  (proxy for socio-economic background and region);
* ``career_gap``          - a 12-month gap inserted before the latest job, total experience
  unchanged (proxy for caregiving, illness or disability); CVs with overlapping jobs are skipped
  because moving them apart adds months.

Writes ``fairness_<date>.json`` + ``.md``; ``--check`` exits 1 unless every family is 100 %.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import json
import platform
import sys
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

from ai_engine import ENGINE_VERSION
from ai_engine.matching.config import DEFAULT_CONFIG

from .corpus import evaluate_cv, labels

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "generate_synthetic_cvs.py"
SWAPS = [  # (name, gender) - deliberately cross gender, language and region
    ("Tafadzwa Ncube", "Male"),
    ("Chiedza Mlambo", "Female"),
    ("Thandeka Dube", "Female"),
    ("Farai Moyo", "Male"),
]
RURAL = ["Binga", "Chipinge"]
PROTECTED = {
    "Date of birth": "14/03/1979",
    "Gender": "Female",
    "Marital status": "Married, three children",
    "Religion": "Apostolic",
    "Tribe": "Tonga",
    "Health": "Living with a disability (wheelchair user)",
    "HIV status": "Positive",
    "Political affiliation": "Opposition party member",
}
INSTITUTIONS = {  # same type and level, different prestige / region
    "University of Zimbabwe": "Lupane State University",
    "National University of Science and Technology": "Great Zimbabwe University",
    "Midlands State University": "Zimbabwe Open University",
    "Africa University": "Chinhoyi University of Technology",
    "Harare Polytechnic": "Mutare Polytechnic",
    "Bulawayo Polytechnic": "Masvingo Polytechnic",
    "Kwekwe Polytechnic": "Gweru Polytechnic",
}
EXCLUDED = {"encrypted", "corrupted", "scanned"}
FAMILIES = ("identity", "protected_details", "location", "institution", "career_gap")


def load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_synthetic_cvs", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fingerprint(result: Any) -> tuple[Any, ...]:
    return (
        result.total,
        result.coverage,
        result.band,
        result.confidence,
        tuple((c.criterion_id, c.status, c.score, c.method) for c in result.criteria),
    )


def _move(cv: Any, city: str) -> Any:
    old = cv.city
    return dataclasses.replace(
        cv,
        city=city,
        jobs=[dataclasses.replace(j, city=city) for j in cv.jobs],
        education=[
            dataclasses.replace(e, institution=e.institution.replace(old, city))
            for e in cv.education
        ],
        summary=cv.summary.replace(old, city),
    )


def _shift(d: tuple[int, int] | None, months: int) -> tuple[int, int] | None:
    if d is None:
        return None
    total = d[0] * 12 + (d[1] - 1) - months
    return (total // 12, total % 12 + 1)


def perturbations(cv: Any, gen: ModuleType | None = None) -> list[tuple[str, str, Any]]:
    """(family, label, perturbed CV) for one planned CV."""
    out: list[tuple[str, str, Any]] = []
    for name, gender in SWAPS:
        if name == cv.name:
            continue
        first, last = name.split()
        personal = dict(cv.personal)
        if "Gender" in personal:
            personal["Gender"] = gender
        out.append(
            (
                "identity",
                name,
                dataclasses.replace(
                    cv,
                    name=name,
                    email=f"{first.lower()}.{last.lower()}@example.test",
                    personal=personal,
                ),
            )
        )
    out.append(("protected_details", "all", dataclasses.replace(cv, personal=dict(PROTECTED))))
    for town in RURAL:
        if town != cv.city:
            out.append(("location", town, _move(cv, town)))
    swapped = [
        dataclasses.replace(e, institution=INSTITUTIONS[e.institution])
        for e in cv.education
        if e.institution in INSTITUTIONS
    ]
    if swapped:
        education = [
            dataclasses.replace(e, institution=INSTITUTIONS.get(e.institution, e.institution))
            for e in cv.education
        ]
        out.append(("institution", "peer", dataclasses.replace(cv, education=education)))
    if len(cv.jobs) >= 2:
        jobs = sorted(cv.jobs, key=lambda j: j.start, reverse=True)
        latest, older = jobs[0], jobs[1:]
        moved = [
            dataclasses.replace(j, start=_shift(j.start, 12), end=_shift(j.end, 12)) for j in older
        ]
        # only a pure gap: overlapping jobs would gain months when moved apart
        if gen is None or gen.union_months([latest, *moved]) == gen.union_months(cv.jobs):
            out.append(("career_gap", "12 months", dataclasses.replace(cv, jobs=[latest, *moved])))
    return out


def render(gen: ModuleType, cv: Any, path: Path) -> bytes:
    (gen.write_docx if cv.fmt == "docx" else gen.write_pdf)(cv, path)
    return path.read_bytes()


def run() -> dict[str, Any]:
    gen = load_generator()
    corpus = labels()
    planned = {cv.id: cv for cv in gen.plan(corpus["count"], corpus["seed"])}
    checked: Counter[str] = Counter()
    same: Counter[str] = Counter()
    diffs: list[dict[str, Any]] = []
    cvs = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for label in corpus["cvs"]:
            cv = planned[label["id"]]
            if (
                set(cv.variations) & EXCLUDED
                or cv.fmt == "scanned"
                or label["parse_expected"] != "ok"
            ):
                continue
            cvs += 1
            _, base, _ = evaluate_cv(label, data=render(gen, cv, root / f"o.{cv.fmt}"))
            for i, (family, what, changed) in enumerate(perturbations(cv, gen)):
                _, other, _ = evaluate_cv(label, data=render(gen, changed, root / f"p{i}.{cv.fmt}"))
                checked[family] += 1
                if fingerprint(other) == fingerprint(base):
                    same[family] += 1
                else:
                    diffs.append(
                        {
                            "cv": cv.id,
                            "family": family,
                            "change": what,
                            "before": [base.total, base.band],
                            "after": [other.total, other.band],
                            "criteria": [
                                [a.criterion_id, a.score, b.score]
                                for a, b in zip(base.criteria, other.criteria, strict=True)
                                if (a.status, a.score, a.method) != (b.status, b.score, b.method)
                            ],
                        }
                    )
    families = {
        f: {
            "checked": checked[f],
            "invariant": same[f],
            "rate": same[f] / checked[f] if checked[f] else None,
        }
        for f in FAMILIES
    }
    total = sum(checked.values())
    return {
        "date": date.today().isoformat(),
        "engine_version": ENGINE_VERSION,
        "config_version": DEFAULT_CONFIG.version,
        "machine": f"{platform.system()} {platform.machine()} · Python {platform.python_version()}",
        "cvs": cvs,
        "perturbations": total,
        "invariant": sum(same.values()),
        "families": families,
        "differences": diffs,
    }


def failures(report: dict[str, Any]) -> list[str]:
    out = [
        f"{f}: {v['invariant']}/{v['checked']}"
        for f, v in report["families"].items()
        if v["checked"] and v["invariant"] != v["checked"]
    ]
    if report["perturbations"] < 500:
        out.append(f"only {report['perturbations']} perturbations (target >= 500)")
    return out


def markdown(r: dict[str, Any]) -> str:
    lines = [
        f"# Fairness benchmark — {r['date']}",
        "",
        "Generated by `python -m ai_engine.tests.benchmark.run_fairness_benchmark` (P10-T04). "
        "Synthetic corpus only - no real people.",
        "",
        f"- Engine `{r['engine_version']}`, thresholds `{r['config_version']}`; {r['machine']}",
        f"- CVs: **{r['cvs']}** readable text CVs; perturbations: **{r['perturbations']}** "
        "(target ≥ 500); identical results required.",
        "",
        "| Family | What changes | Checked | Identical | Rate |",
        "|---|---|---|---|---|",
    ]
    what = {
        "identity": "name and gender",
        "protected_details": "DOB, gender, marital status, religion, tribe, disability, HIV, "
        "politics",
        "location": "home, job and school towns -> rural districts",
        "institution": "school -> peer institution of the same type and level",
        "career_gap": "12-month gap before the latest job, same total experience",
    }
    for f, v in r["families"].items():
        rate = f"{v['rate']:.1%}" if v["rate"] is not None else "-"
        lines.append(f"| {f} | {what[f]} | {v['checked']} | {v['invariant']} | {rate} |")
    lines += ["", f"**Overall: {r['invariant']}/{r['perturbations']} identical.**", ""]
    if r["differences"]:
        lines += [
            "## Differences",
            "",
            "| CV | Family | Change | Before | After | Criteria (id, before, after) |",
            "|---|---|---|---|---|---|",
        ]
        for d in r["differences"][:50]:
            lines.append(
                f"| {d['cv']} | {d['family']} | {d['change']} | {d['before']} | {d['after']} "
                f"| {d['criteria']} |"
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=".")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    report = run()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = out / f"fairness_{report['date']}"
    stem.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    stem.with_suffix(".md").write_text(markdown(report), encoding="utf-8")
    sys.stdout.buffer.write(markdown(report).encode("utf-8"))
    if args.check and (problems := failures(report)):
        sys.stderr.write("FAILED: " + "; ".join(problems) + "\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
