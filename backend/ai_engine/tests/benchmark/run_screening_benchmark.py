"""Screening benchmark on the synthetic corpus (P07-T15, docs/09 §5, Phase 07 exit criteria).

    python -m ai_engine.tests.benchmark.run_screening_benchmark --out-dir ../docs/reports --check

For every readable CV it extracts once, evaluates against the role rubric and explains, then
compares with the gold labels in ``labels.json``:

* recall: gold ``suitable`` candidates routed to ``recommended_for_review`` or ``review_needed``
  (target >= 0.95) - the engine must not bury qualified people in ``lower_match``;
* criterion agreement with ``expected_evidence`` (informational);
* grounding: share of explanation sentences that survive the grounding check (target 100%);
* determinism: a second evaluation of the same input is byte-identical (target 100%);
* counterfactual invariance: name/gender/town swaps never change the result (target 100%;
  needs ``scripts/generate_synthetic_cvs.py``);
* throughput: 100 evaluations + explanations after extraction (target <= 5 min).

Writes ``screening_benchmark_<date>.json`` + ``.md``; ``--check`` exits 1 if a target is missed.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import tempfile
import time
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from ai_engine import ENGINE_VERSION
from ai_engine.evaluation.bands import RECOMMENDED, REVIEW
from ai_engine.evaluation.engine import EvaluationInput, EvaluationResult, evaluate
from ai_engine.explanations.grounding import explain
from ai_engine.matching.config import DEFAULT_CONFIG

from .corpus import CORPUS, evaluate_cv, labels, readable_cvs, taxonomy

TARGETS = {
    "recall_suitable": 0.95,
    "grounding_rate": 1.0,
    "determinism": 1.0,
    "counterfactual": 1.0,
    "seconds_per_100": 300.0,
}
AGREES = {"met": {100, 75, 50}, "partial": {50, 75, 25}, "missing": {None, 25, 0}}


def _counterfactual(limit: int) -> dict[str, Any]:
    try:
        from ai_engine.tests import test_fairness as tf
    except Exception as exc:  # pragma: no cover - pytest missing outside dev
        return {"skipped": f"helpers unavailable: {exc}"}
    if not tf.SCRIPT.exists():
        return {"skipped": "scripts/generate_synthetic_cvs.py not available"}
    import importlib.util

    spec = importlib.util.spec_from_file_location("generate_synthetic_cvs", tf.SCRIPT)
    assert spec and spec.loader
    gen = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = gen
    spec.loader.exec_module(gen)
    planned = {cv.id: cv for cv in gen.plan(labels()["count"], labels()["seed"])}
    checked = same = 0
    diffs: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for label in labels()["cvs"]:
            cv = planned[label["id"]]
            if set(cv.variations) & tf.EXCLUDED or cv.fmt == "scanned":
                continue
            _, base, _ = evaluate_cv(label, data=tf.render(gen, cv, root / f"o.{cv.fmt}"))
            for i, (name, gender, city) in enumerate(tf.SWAPS):
                if city == cv.city:
                    continue
                swapped = tf.counterfactual(gen, cv, name, gender, city)
                data = tf.render(gen, swapped, root / f"c{i}.{cv.fmt}")
                _, other, _ = evaluate_cv(label, data=data)
                checked += 1
                if tf.fingerprint(other) == tf.fingerprint(base):
                    same += 1
                else:
                    diffs.append(f"{cv.id}:{name}")
            if checked >= limit:
                break
    return {
        "checked": checked,
        "invariant": same,
        "rate": same / checked if checked else None,
        "differences": diffs[:10],
    }


def run(counterfactual_limit: int = 120) -> dict[str, Any]:
    evaluated: list[tuple[dict[str, Any], EvaluationInput, EvaluationResult]] = []
    for cv in readable_cvs():
        if cv["needs_ocr"]:
            continue  # OCR needs Tesseract (worker image); reported by the extraction benchmark
        inp, result, _ = evaluate_cv(cv)
        evaluated.append((cv, inp, result))

    graph = taxonomy().graph
    confusion: dict[str, Counter[str]] = {}
    agree = total = 0
    sentences = dropped = 0
    deterministic = 0
    missed: list[str] = []
    for cv, inp, result in evaluated:
        gold = cv["hr_reference_suitability"]
        confusion.setdefault(gold, Counter())[result.band] += 1
        if gold == "suitable" and result.band not in (RECOMMENDED, REVIEW):
            missed.append(f"{cv['id']} -> {result.band} ({result.band_reasons})")
        by_id = {c.criterion_id: c for c in result.criteria}
        for item in cv["criteria"]:
            want = cv["expected_evidence"].get(item["id"])
            got = by_id.get(item["id"])
            if want in AGREES and got is not None:
                total += 1
                agree += got.score in AGREES[want]
        explanation = explain(result, inp.criteria, inp.evidence)
        sentences += len(explanation.sentences)
        dropped += explanation.dropped
        again = evaluate(inp, graph=graph)
        deterministic += again.model_dump_json() == result.model_dump_json()

    suitable = sum(confusion.get("suitable", Counter()).values())
    found = sum(confusion.get("suitable", Counter())[b] for b in (RECOMMENDED, REVIEW))
    not_suitable = confusion.get("not_suitable", Counter())

    # throughput: 100 evaluations + explanations of already-extracted inputs
    batch = [(inp) for _, inp, _ in evaluated]
    batch = (batch * (100 // max(1, len(batch)) + 1))[:100]
    start = time.perf_counter()
    for inp in batch:
        explain(evaluate(inp, graph=graph), inp.criteria, inp.evidence)
    seconds = time.perf_counter() - start

    cf = _counterfactual(counterfactual_limit) if counterfactual_limit else {"skipped": "off"}
    return {
        "date": date.today().isoformat(),
        "engine_version": ENGINE_VERSION,
        "config_version": DEFAULT_CONFIG.version,
        "machine": f"{platform.system()} {platform.machine()} · Python {platform.python_version()}",
        "evaluated": len(evaluated),
        "bands": dict(Counter(r.band for _, _, r in evaluated)),
        "confusion": {k: dict(v) for k, v in sorted(confusion.items())},
        "recall_suitable": found / suitable if suitable else None,
        "suitable": suitable,
        "missed_suitable": missed,
        "not_suitable_recommended_rate": (
            not_suitable[RECOMMENDED] / sum(not_suitable.values()) if not_suitable else None
        ),
        "criterion_agreement": agree / total if total else None,
        "criteria_compared": total,
        "explanation_sentences": sentences,
        "grounding_dropped": dropped,
        "grounding_rate": sentences / (sentences + dropped) if sentences + dropped else None,
        "determinism": deterministic / len(evaluated) if evaluated else None,
        "counterfactual": cf,
        "seconds_per_100": round(seconds, 2),
    }


def failures(report: dict[str, Any]) -> list[str]:
    out = []
    for key in ("recall_suitable", "grounding_rate", "determinism"):
        value = report[key]
        if value is None or value < TARGETS[key]:
            out.append(f"{key}={value} < {TARGETS[key]}")
    rate = report["counterfactual"].get("rate")
    if "skipped" not in report["counterfactual"] and (rate is None or rate < 1.0):
        out.append(f"counterfactual={rate} < 1.0")
    if report["seconds_per_100"] > TARGETS["seconds_per_100"]:
        out.append(f"seconds_per_100={report['seconds_per_100']} > 300")
    return out


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def markdown(r: dict[str, Any]) -> str:
    cf = r["counterfactual"]
    cf_line = (
        f"skipped ({cf['skipped']})"
        if "skipped" in cf
        else f"{cf['invariant']}/{cf['checked']} invariant ({pct(cf['rate'])})"
    )
    bands = sorted({b for row in r["confusion"].values() for b in row})
    lines = [
        f"# Screening benchmark — {r['date']}",
        "",
        "Synthetic corpus only (`backend/fixtures/synthetic_cvs`, no real people). Generated by",
        "`python -m ai_engine.tests.benchmark.run_screening_benchmark` (P07-T15).",
        "",
        f"- Engine `{r['engine_version']}`, thresholds `{r['config_version']}`; {r['machine']}",
        f"- CVs evaluated: **{r['evaluated']}** (OCR-only CVs are covered by the extraction "
        "benchmark)",
        "",
        "| Metric | Result | Target |",
        "|---|---|---|",
        f"| Recall of gold *suitable* in recommended or review needed | "
        f"**{pct(r['recall_suitable'])}** ({r['suitable']} suitable) | ≥ 95% |",
        f"| Explanation grounding | **{pct(r['grounding_rate'])}** "
        f"({r['explanation_sentences']} sentences, {r['grounding_dropped']} dropped) | 100% |",
        f"| Determinism (re-evaluation identical) | **{pct(r['determinism'])}** | 100% |",
        f"| Counterfactual invariance (name/gender/town) | **{cf_line}** | 100% |",
        f"| 100 evaluations + explanations after extraction | **{r['seconds_per_100']} s** | "
        "≤ 300 s |",
        f"| Criterion agreement with gold evidence (informational) | "
        f"{pct(r['criterion_agreement'])} ({r['criteria_compared']} criteria) | — |",
        f"| Gold *not suitable* placed in recommended (informational) | "
        f"{pct(r['not_suitable_recommended_rate'])} | — |",
        "",
        "## Gold suitability by band",
        "",
        "| Gold \\ band | " + " | ".join(bands) + " |",
        "|---|" + "---|" * len(bands),
    ]
    for gold, row in r["confusion"].items():
        lines.append(f"| {gold} | " + " | ".join(str(row.get(b, 0)) for b in bands) + " |")
    lines += [
        "",
        "Bands are routing hints for people; there is no reject band and nothing is decided "
        "automatically. Missing evidence is unknown (review needed), never a fail.",
    ]
    if r["missed_suitable"]:
        lines += ["", "## Suitable candidates not routed to review", ""]
        lines += [f"- {m}" for m in r["missed_suitable"]]
    if r["counterfactual"].get("differences"):
        lines += ["", "## Counterfactual differences", ""]
        lines += [f"- {d}" for d in r["counterfactual"]["differences"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--counterfactual", type=int, default=120, help="0 to skip")
    args = parser.parse_args(argv)
    if not CORPUS.exists():
        sys.stderr.write("synthetic corpus missing\n")
        return 2
    report = run(args.counterfactual)
    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        stem = args.out_dir / f"screening_benchmark_{report['date']}"
        stem.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        stem.with_suffix(".md").write_text(markdown(report), encoding="utf-8")
    summary = {k: v for k, v in report.items() if k != "confusion"}
    sys.stdout.write(json.dumps(summary, indent=2) + "\n")
    problems = failures(report)
    for p in problems:
        sys.stderr.write(f"TARGET MISSED: {p}\n")
    return 1 if args.check and problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
