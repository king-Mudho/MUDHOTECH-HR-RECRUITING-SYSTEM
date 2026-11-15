"""Determinism (EC-AI-08) and counterfactual fairness (EC-AI-13), P07-T08.

Counterfactuals are re-rendered from the synthetic generator with the name, gender, home city,
job cities and school town swapped; scores, bands and every criterion result must be identical.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from ai_engine.evaluation.engine import evaluate

from .benchmark.corpus import CORPUS, evaluate_cv, labels, readable_cvs, taxonomy

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "generate_synthetic_cvs.py"
SWAPS = [  # (name, gender, city) - names deliberately cross gender, language and region
    ("Tafadzwa Ncube", "Male", "Bulawayo"),
    ("Chiedza Mlambo", "Female", "Mutare"),
    ("Thandeka Dube", "Female", "Gweru"),
    ("Farai Moyo", "Male", "Chinhoyi"),
]
EXCLUDED = {"encrypted", "corrupted", "scanned"}


@pytest.fixture(scope="module")
def gen() -> ModuleType:
    if not SCRIPT.exists():
        pytest.skip("scripts/ not mounted")
    spec = importlib.util.spec_from_file_location("generate_synthetic_cvs", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def counterfactual(gen: ModuleType, cv: Any, name: str, gender: str, city: str) -> Any:
    old_city = cv.city
    first = name.split()[0].lower()
    jobs = [dataclasses.replace(j, city=city) for j in cv.jobs]
    education = [
        dataclasses.replace(e, institution=e.institution.replace(old_city, city))
        for e in cv.education
    ]
    personal = dict(cv.personal)
    if "Gender" in personal:
        personal["Gender"] = gender
    return dataclasses.replace(
        cv,
        name=name,
        email=f"{first}.{name.split()[1].lower()}@example.test",
        city=city,
        jobs=jobs,
        education=education,
        personal=personal,
        summary=cv.summary.replace(old_city, city),
    )


def render(gen: ModuleType, cv: Any, path: Path) -> bytes:
    (gen.write_docx if cv.fmt == "docx" else gen.write_pdf)(cv, path)
    return path.read_bytes()


def fingerprint(result: Any) -> tuple[Any, ...]:
    return (
        result.total,
        result.coverage,
        result.band,
        result.confidence,
        tuple((c.criterion_id, c.status, c.score, c.method) for c in result.criteria),
    )


@pytest.mark.skipif(not CORPUS.exists(), reason="synthetic corpus missing")
def test_evaluation_is_deterministic() -> None:
    """EC-AI-08: same input -> identical result and input hash, every time."""
    for cv in list(readable_cvs())[:20]:
        inp, first, _ = evaluate_cv(cv)
        again = evaluate(inp, graph=taxonomy().graph)
        assert again.model_dump_json() == first.model_dump_json()
        _, rerun, _ = evaluate_cv(cv)  # extraction too
        assert rerun.input_hash == first.input_hash
        assert rerun.model_dump_json() == first.model_dump_json()


@pytest.mark.skipif(not CORPUS.exists(), reason="synthetic corpus missing")
def test_counterfactual_invariance(gen: ModuleType, tmp_path: Path) -> None:
    """EC-AI-13: name, gender, location and institution town never change a score."""
    planned = {cv.id: cv for cv in gen.plan(labels()["count"], labels()["seed"])}
    checked = 0
    for label in labels()["cvs"]:
        cv = planned[label["id"]]
        if set(cv.variations) & EXCLUDED or cv.fmt == "scanned":
            continue
        original = render(gen, cv, tmp_path / f"o_{cv.id}.{cv.fmt}")
        _, base, _ = evaluate_cv(label, data=original)
        for i, (name, gender, city) in enumerate(SWAPS):
            if city == cv.city:
                continue
            swapped = counterfactual(gen, cv, name, gender, city)
            data = render(gen, swapped, tmp_path / f"c{i}_{cv.id}.{cv.fmt}")
            _, other, _ = evaluate_cv(label, data=data)
            assert fingerprint(other) == fingerprint(base), (cv.id, name, city)
            checked += 1
        if checked >= 120:
            break
    assert checked >= 100
