"""Extraction benchmark on the synthetic corpus (P06-T15, docs/09 §5).

    python -m ai_engine.tests.benchmark.run_extraction_benchmark \
        --out-dir ../docs/reports --workers 2 --check

Runs the full pure pipeline (text -> sections -> claims -> normalisation -> protection) over
``backend/fixtures/synthetic_cvs`` with the taxonomy fixtures, compares with ``labels.json`` and
writes ``extraction_benchmark_<date>.json`` + ``.md``. ``--check`` exits 1 when a docs/09 target
is missed. ``--workers N`` also times N parallel sandboxed extractions of 100 CVs (the exit
criterion: <= 10 minutes with 2 document workers). OCR needs Tesseract and semantic matching the
``ml`` extra - both present in the worker image the nightly job uses; without them the related
metrics are reported as skipped/informational.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from ai_engine import ENGINE_VERSION
from ai_engine.contracts import (
    CandidateEvidence,
    ExtractionResult,
    Flag,
    PartialDate,
)
from ai_engine.extraction.extract import extract_document
from ai_engine.extraction.parser import Semantic, extract_claims
from ai_engine.extraction.pii import protect
from ai_engine.extraction.sandbox import run_extraction
from ai_engine.extraction.skills import SkillIndex
from ai_engine.normalisation.experience import Role, summarise
from ai_engine.normalisation.qualifications import QualificationIndex, normalise_education
from ai_engine.normalisation.titles import normalise_experience

BACKEND = Path(__file__).resolve().parents[3]
CORPUS = BACKEND / "fixtures" / "synthetic_cvs"
TAXONOMY = BACKEND / "fixtures" / "taxonomy"

TARGETS = {  # docs/09 §5 (defaults; owner confirms in Phase 10)
    "parse_success_text": 0.98,
    "parse_success_all": 0.90,
    "experience_f1": 0.85,
    "education_level_accuracy": 0.90,
    "skill_precision": 0.85,
    "skill_recall": 0.80,
    "grounding_rate": 1.0,
    "determinism": 1.0,
    "protected_leaks": 0,
    "seconds_per_100_cvs": 600,
}
LABEL_LEVELS = {
    "o_level": "ZW_OLEVEL",
    "a_level": "ZW_ALEVEL",
    "national_certificate": "ZW_NC",
    "national_diploma": "ZW_ND",
    "diploma": "ZW_ND",
    "hnd": "ZW_HND",
    "bachelor": "BACHELOR",
    "honours": "HONOURS",
}
PROTECTED = {
    "Date of birth": "date_of_birth",
    "National ID": "national_id",
    "Gender": "gender",
    "Marital status": "marital_status",
    "Religion": "religion",
    "Health": "health",
}


@dataclass
class Counter:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


@dataclass
class Tally:
    n: int = 0
    ok: int = 0

    @property
    def rate(self) -> float:
        return self.ok / self.n if self.n else 1.0


@dataclass
class Results:
    parse_text: Tally = field(default_factory=Tally)
    parse_all: Tally = field(default_factory=Tally)
    expected_failures: Tally = field(default_factory=Tally)
    experience: Counter = field(default_factory=Counter)
    employment_kind: Tally = field(default_factory=Tally)
    total_months_exact: Tally = field(default_factory=Tally)
    total_months_abs_error: list[int] = field(default_factory=list)
    education_found: Tally = field(default_factory=Tally)
    education_level: Tally = field(default_factory=Tally)
    foreign_flagged: Tally = field(default_factory=Tally)
    certifications: Tally = field(default_factory=Tally)
    languages: Tally = field(default_factory=Tally)
    skill_listed: Counter = field(default_factory=Counter)
    skill_recall: Tally = field(default_factory=Tally)
    equivalent_recall: Tally = field(default_factory=Tally)
    protected_recall: Tally = field(default_factory=Tally)
    protected_false_cvs: int = 0
    protected_leaks: int = 0
    injection: Counter = field(default_factory=Counter)
    hidden: Counter = field(default_factory=Counter)
    claims: int = 0
    grounded: int = 0
    determinism: Tally = field(default_factory=Tally)
    extract_ms: list[float] = field(default_factory=list)
    misses: list[str] = field(default_factory=list)


def load_indexes() -> tuple[SkillIndex, QualificationIndex]:
    skills = json.loads((TAXONOMY / "skills.json").read_text(encoding="utf-8"))
    quals = json.loads((TAXONOMY / "qualifications.json").read_text(encoding="utf-8"))
    return (
        SkillIndex.from_taxonomy([dict(s, id=s["name"]) for s in skills["skills"]]),
        QualificationIndex.from_taxonomy(quals["levels"], quals["professional_bodies"]),
    )


def semantic_matcher(enabled: bool) -> Semantic | None:
    if not enabled or importlib.util.find_spec("sentence_transformers") is None:
        return None
    from ai_engine.matching.semantic import (
        DEFAULT_MODEL,
        EmbeddingService,
        SemanticSkillMatcher,
        SkillVector,
        get_encoder,
    )

    doc = json.loads((TAXONOMY / "skills.json").read_text(encoding="utf-8"))
    svc = EmbeddingService(get_encoder(DEFAULT_MODEL))
    texts = [
        f"{s['name']} ({', '.join(s['aliases'][:8])})" if s["aliases"] else s["name"]
        for s in doc["skills"]
    ]
    vectors = svc.embed(texts)
    skills = [
        SkillVector(s["name"], s["name"], v) for s, v in zip(doc["skills"], vectors, strict=True)
    ]
    return SemanticSkillMatcher(svc, skills)


def pipeline(
    data: bytes,
    doc_id: str,
    skills: SkillIndex,
    quals: QualificationIndex,
    semantic: Semantic | None,
    today: tuple[int, int],
) -> ExtractionResult:
    result = extract_document(data, document_id=doc_id)
    result = extract_claims(result, today=today, skills=skills, semantic=semantic)
    return protect(normalise_experience(normalise_education(result, quals)))


def _pd(value: str | None) -> PartialDate | None:
    return None if value is None else PartialDate(year=int(value[:4]), month=int(value[5:]))


def score_cv(
    cv: dict[str, Any], result: ExtractionResult, skills: SkillIndex, r: Results, today: Any
) -> None:
    fmt_text = cv["format"] in ("pdf", "docx") and not cv["needs_ocr"]
    if cv["parse_expected"] != "ok":
        r.expected_failures.n += 1
        expected = {"encrypted": "encrypted_pdf"}.get(cv["parse_expected"], cv["parse_expected"])
        r.expected_failures.ok += result.error_code == expected
        return
    page_text = result.document.pages[0].text if result.document and result.document.pages else ""
    readable = result.document is not None and len(page_text.strip()) > 200
    r.parse_all.n += 1
    r.parse_all.ok += readable
    if fmt_text:
        r.parse_text.n += 1
        r.parse_text.ok += readable
    if not readable:
        r.misses.append(f"{cv['file']}: not readable ({result.error_code or sorted(result.flags)})")
        return

    ev = [c for c in result.claims if c.evaluable]
    # grounding: every claim's snippet is the located text
    for claim in result.claims:
        r.claims += 1
        src = claim.source
        located = " ".join(page_text[src.char_start or 0 : src.char_end or 0].split())
        if claim.data.type == "protected":
            r.grounded += bool(src.snippet) and src.char_end is not None
        else:
            r.grounded += located.startswith(src.snippet.rstrip("…")[:40])

    # experience
    jobs = [c.data for c in ev if c.data.type == "experience"]
    gold = {(j["title"], j["employer"]): j for j in cv["experience"]}
    found = {(j.title, j.employer): j for j in jobs}
    for key, j in gold.items():
        if key in found:
            r.experience.tp += 1
            r.employment_kind.n += 1
            r.employment_kind.ok += found[key].employment_kind.value == j["kind"]
        else:
            r.experience.fn += 1
            r.misses.append(f"{cv['file']}: missed role {key}")
    r.experience.fp += len([k for k in found if k not in gold])
    roles = [Role(j.dates, j.employment_kind) for j in jobs]
    total = summarise(roles, today).total_months
    r.total_months_exact.n += 1
    r.total_months_exact.ok += total == cv["total_experience_months"]
    r.total_months_abs_error.append(abs(total - cv["total_experience_months"]))

    # education
    edu = {c.data.qualification_text: c.data for c in ev if c.data.type == "education"}
    for e in cv["education"]:
        r.education_found.n += 1
        got = edu.get(e["qualification"])
        if got is None:
            continue
        r.education_found.ok += 1
        if e["foreign"]:
            r.foreign_flagged.n += 1
            r.foreign_flagged.ok += got.foreign and got.needs_verification
        else:
            r.education_level.n += 1
            r.education_level.ok += got.level == LABEL_LEVELS.get(e["level"])

    certs = {c.data.name for c in ev if c.data.type == "certification"}
    r.certifications.n += len(cv["certifications"])
    r.certifications.ok += sum(x in certs for x in cv["certifications"])
    langs = {c.data.language for c in ev if c.data.type == "language"}
    r.languages.n += len(cv["languages"])
    r.languages.ok += sum(x in langs for x in cv["languages"])

    # skills (gold resolved through the taxonomy aliases)
    def canon(name: str) -> str:
        entry = skills.lookup(name)
        return (entry.canonical if entry else name).lower()

    gold_skills = {canon(s) for s in cv["skills"]}
    all_found = {(c.data.canonical or c.data.raw).lower() for c in ev if c.data.type == "skill"}
    listed = {
        (c.data.canonical or c.data.raw).lower()
        for c in ev
        if c.data.type == "skill" and c.section is not None and c.section.value == "skills"
    }
    target = r.equivalent_recall if "equivalent_wording" in cv["variations"] else r.skill_recall
    target.n += len(gold_skills)
    target.ok += len(gold_skills & all_found)
    if "equivalent_wording" not in cv["variations"]:
        r.skill_listed.tp += len(listed & gold_skills)
        r.skill_listed.fp += len(listed - gold_skills)
        r.skill_listed.fn += len(gold_skills - listed)

    # protection, injection, hidden text
    found_attrs = {c.data.attribute for c in result.claims if c.data.type == "protected"}
    wanted = {PROTECTED[p] for p in cv["protected_data_present"]}
    r.protected_recall.n += len(wanted)
    r.protected_recall.ok += len(wanted & found_attrs)
    r.protected_false_cvs += bool(found_attrs - wanted)
    evidence = CandidateEvidence.from_results(cv["id"], [result]).model_dump_json()
    for line in page_text.splitlines():
        for label in cv["protected_data_present"]:
            if line.startswith(f"{label}:"):
                value = line.split(":", 1)[1].strip()
                r.protected_leaks += bool(value) and value in evidence
    injected = Flag.INJECTION_SUSPECTED in result.flags
    if cv["injection"]:
        r.injection.tp += injected
        r.injection.fn += not injected
        r.protected_leaks += cv["injection"][:30] in evidence
    else:
        r.injection.fp += injected
    hidden = Flag.HIDDEN_TEXT in result.flags
    if cv.get("hidden_text"):
        r.hidden.tp += hidden
        r.hidden.fn += not hidden
        r.protected_leaks += cv["hidden_text"]["text"][:30] in evidence
    else:
        r.hidden.fp += hidden


def fingerprint(result: ExtractionResult) -> str:
    claims = [c.model_dump_json() for c in result.claims]
    return hashlib.sha256("\n".join(claims).encode()).hexdigest()


def throughput(files: list[Path], workers: int) -> dict[str, Any]:
    """Wall time for 100 sandboxed extractions with ``workers`` in parallel (EC-DOC-26 path)."""
    batch = (files * (100 // max(len(files), 1) + 1))[:100]

    def one(path: Path) -> str:
        return run_extraction(path.read_bytes(), document_id=path.stem).status.value

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        statuses = list(pool.map(one, batch))
    seconds = time.perf_counter() - started
    return {
        "cvs": len(batch),
        "workers": workers,
        "seconds": round(seconds, 1),
        "failed": sum(s == "failed" for s in statuses),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    labels = json.loads((CORPUS / "labels.json").read_text(encoding="utf-8"))
    today = tuple(int(x) for x in labels["reference_month"].split("-"))
    skills, quals = load_indexes()
    semantic = semantic_matcher(args.semantic)
    r = Results()
    for cv in labels["cvs"]:
        data = (CORPUS / cv["file"]).read_bytes()
        started = time.perf_counter()
        result = pipeline(data, cv["id"], skills, quals, semantic, today)  # type: ignore[arg-type]
        r.extract_ms.append((time.perf_counter() - started) * 1000)
        score_cv(cv, result, skills, r, today)
        if cv["parse_expected"] == "ok" and len(r.extract_ms) % 3 == 0:  # determinism sample
            again = pipeline(data, cv["id"], skills, quals, semantic, today)  # type: ignore[arg-type]
            r.determinism.n += 1
            r.determinism.ok += fingerprint(again) == fingerprint(result)
    timing = None
    if args.workers:
        texty = [CORPUS / cv["file"] for cv in labels["cvs"] if cv["parse_expected"] == "ok"]
        timing = throughput(texty, args.workers)

    ms = sorted(r.extract_ms)
    metrics = {
        "parse_success_text": round(r.parse_text.rate, 4),
        "parse_success_all": round(r.parse_all.rate, 4),
        "expected_failures_detected": round(r.expected_failures.rate, 4),
        "experience_precision": round(r.experience.precision, 4),
        "experience_recall": round(r.experience.recall, 4),
        "experience_f1": round(r.experience.f1, 4),
        "employment_kind_accuracy": round(r.employment_kind.rate, 4),
        "total_months_exact": round(r.total_months_exact.rate, 4),
        "total_months_mean_abs_error": round(
            sum(r.total_months_abs_error) / max(len(r.total_months_abs_error), 1), 2
        ),
        "education_found": round(r.education_found.rate, 4),
        "education_level_accuracy": round(r.education_level.rate, 4),
        "foreign_qualifications_flagged": round(r.foreign_flagged.rate, 4),
        "certification_recall": round(r.certifications.rate, 4),
        "language_recall": round(r.languages.rate, 4),
        "skill_precision": round(r.skill_listed.precision, 4),
        "skill_recall": round(r.skill_recall.rate, 4),
        "equivalent_wording_recall": round(r.equivalent_recall.rate, 4),
        "protected_recall": round(r.protected_recall.rate, 4),
        "protected_false_positive_cvs": r.protected_false_cvs,
        "protected_leaks": r.protected_leaks,
        "injection_precision": round(r.injection.precision, 4),
        "injection_recall": round(r.injection.recall, 4),
        "hidden_text_precision": round(r.hidden.precision, 4),
        "hidden_text_recall": round(r.hidden.recall, 4),
        "grounding_rate": round(r.grounded / max(r.claims, 1), 4),
        "determinism": round(r.determinism.rate, 4),
        "claims": r.claims,
        "ms_per_cv_median": round(ms[len(ms) // 2], 1),
        "ms_per_cv_p95": round(ms[int(len(ms) * 0.95) - 1], 1),
    }
    if timing:
        metrics["seconds_per_100_cvs"] = timing["seconds"]
    checks = {}
    for key, target in TARGETS.items():
        if key not in metrics:
            continue
        value = metrics[key]
        if key in ("protected_leaks", "seconds_per_100_cvs"):
            checks[key] = {"value": value, "target": f"<= {target}", "pass": value <= target}
        else:
            checks[key] = {"value": value, "target": f">= {target}", "pass": value >= target}
    ocr = shutil.which("tesseract") is not None
    return {
        "date": args.date or date.today().isoformat(),
        "engine_version": ENGINE_VERSION,
        "corpus": {
            "generator_version": labels["generator_version"],
            "seed": labels["seed"],
            "cvs": len(labels["cvs"]),
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cpus": os.cpu_count(),
            "tesseract": ocr,
            "semantic_model": semantic is not None,
        },
        "metrics": metrics,
        "checks": checks,
        "throughput": timing,
        "notes": [
            "skill_precision counts skills read from the skills section against the labelled "
            "skills; mentions inside duties are real but unlabelled, so they are not counted.",
            *(["OCR not available: scanned CVs count as unreadable."] if not ocr else []),
            *(
                ["Semantic model not loaded: equivalent-wording recall is rules-only."]
                if semantic is None
                else []
            ),
        ],
        "misses": r.misses[:40],
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Extraction benchmark — {report['date']}",
        "",
        f"Engine `{report['engine_version']}` · "
        f"synthetic corpus v{report['corpus']['generator_version']} "
        f"(seed {report['corpus']['seed']}, {report['corpus']['cvs']} CVs) · "
        f"Tesseract: {'yes' if report['environment']['tesseract'] else 'no'} · "
        f"semantic model: {'yes' if report['environment']['semantic_model'] else 'no'} · "
        f"{report['environment']['cpus']} CPUs",
        "",
        "## Targets (docs/09 §5)",
        "",
        "| Metric | Value | Target | Result |",
        "|---|---|---|---|",
    ]
    for key, check in report["checks"].items():
        result = "pass" if check["pass"] else "MISS"
        lines.append(f"| {key} | {check['value']} | {check['target']} | {result} |")
    lines += ["", "## All metrics", "", "| Metric | Value |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in report["metrics"].items()]
    if report["throughput"]:
        t = report["throughput"]
        lines += [
            "",
            "## Throughput",
            "",
            f"{t['cvs']} CVs, {t['workers']} parallel sandboxed workers: **{t['seconds']} s** "
            f"({t['failed']} failed).",
        ]
    lines += ["", "## Notes", ""] + [f"- {n}" for n in report["notes"]]
    if report["misses"]:
        lines += ["", "## Misses (first 40)", ""] + [f"- {m}" for m in report["misses"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--workers", type=int, default=0, help="time 100 CVs with N workers")
    parser.add_argument("--semantic", action="store_true", help="use the local embedding model")
    parser.add_argument("--check", action="store_true", help="exit 1 when a target is missed")
    parser.add_argument("--date", default=None)
    args = parser.parse_args(argv)
    report = run(args)
    text = markdown(report)
    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        stem = args.out_dir / f"extraction_benchmark_{report['date']}"
        stem.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        stem.with_suffix(".md").write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    failed = [k for k, c in report["checks"].items() if not c["pass"]]
    if args.check and failed:
        sys.stderr.write(f"targets missed: {', '.join(failed)}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
