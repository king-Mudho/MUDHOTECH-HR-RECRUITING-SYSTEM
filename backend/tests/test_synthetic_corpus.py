"""The committed synthetic CV corpus matches its generator and stays synthetic (P06-T01)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Any

import pymupdf
import pytest
from docx import Document

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "backend" / "fixtures" / "synthetic_cvs"
SCRIPT = ROOT / "scripts" / "generate_synthetic_cvs.py"

pytestmark = pytest.mark.skipif(
    not SCRIPT.exists(),
    reason="repository scripts/ not mounted (e.g. inside the backend container)",
)


@pytest.fixture(scope="module")
def gen() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_synthetic_cvs", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations via sys.modules
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def labels() -> dict[str, Any]:
    return json.loads((CORPUS / "labels.json").read_text(encoding="utf-8"))


def test_committed_labels_match_the_generator(gen: ModuleType, labels: dict[str, Any]) -> None:
    expected = gen.corpus_labels(labels["count"], labels["seed"])
    assert labels == json.loads(json.dumps(expected, ensure_ascii=False))


def test_corpus_shape_and_coverage(gen: ModuleType, labels: dict[str, Any]) -> None:
    cvs = labels["cvs"]
    assert labels["synthetic"] is True and len(cvs) >= 150
    assert set(Counter(c["role"] for c in cvs).values()) == {len(cvs) // 5}
    assert set(Counter(c["profile"] for c in cvs).values()) == {len(cvs) // 3}
    variations = Counter(v for c in cvs for v in c["variations"])
    assert set(variations) == set(gen.VARIATIONS)
    assert min(variations.values()) >= gen.MIN_PER_VARIATION
    assert {c["format"] for c in cvs} == {"pdf", "docx", "scanned"}
    files = {p.name for p in CORPUS.iterdir() if p.suffix in (".pdf", ".docx")}
    assert files == {c["file"] for c in cvs}  # no stray or missing files


def test_only_invented_contact_details(labels: dict[str, Any]) -> None:
    """No real personal data: reserved e-mail domain and an obviously fake number range."""
    for c in labels["cvs"]:
        assert c["person"]["email"].endswith("@example.test")
        assert re.fullmatch(r"\+263 77 000 \d{4}", c["person"]["phone"])


def normalise(text: str) -> str:
    """PDF text keeps typographic ligatures ("ﬁ") and line wraps: NFKC + collapse whitespace.
    The P06-T03 extractor must do the same before matching."""
    return " ".join(unicodedata.normalize("NFKC", text).split())


def test_documents_contain_what_the_labels_say(labels: dict[str, Any]) -> None:
    for c in labels["cvs"]:
        path = CORPUS / c["file"]
        if c["parse_expected"] == "encrypted":
            assert pymupdf.open(path).needs_pass, c["id"]
            continue
        if c["parse_expected"] == "corrupt":
            with pymupdf.open(path) as doc:  # repaired at best, never readable text
                assert "".join(p.get_text() for p in doc).strip() == "", c["id"]
            continue
        if c["format"] == "docx":
            doc = Document(str(path))
            text = "\n".join(p.text for p in doc.paragraphs)
            text += "\n".join(cell.text for t in doc.tables for r in t.rows for cell in r.cells)
            text += "\n".join(p.text for s in doc.sections for p in s.header.paragraphs)
        else:
            with pymupdf.open(path) as doc:
                text = "".join(p.get_text(clip=pymupdf.INFINITE_RECT()) for p in doc)
            if c["needs_ocr"]:
                assert text.strip() == "", f"{c['id']}: scanned CVs have no text layer"
                continue
        text = normalise(text)
        assert c["person"]["name"] in text, c["id"]
        for phrase in c["skill_phrases"]:
            assert phrase in text, (c["id"], phrase)
        for job in c["experience"]:
            assert job["employer"] in text, (c["id"], job["employer"])
        if c["injection"]:
            assert c["injection"] in text, c["id"]
        if c["hidden_text"]:
            assert c["hidden_text"]["text"][:40] in text, c["id"]
        for field in c["protected_data_present"]:
            assert field in text, (c["id"], field)


def test_generation_is_reproducible(gen: ModuleType, tmp_path: Path) -> None:
    """Same seed -> byte-identical files (encrypted PDFs excepted: random AES salt)."""
    first, second = tmp_path / "a", tmp_path / "b"
    gen.generate(first, 12, 7)
    gen.generate(second, 12, 7)
    labels = json.loads((first / "labels.json").read_text(encoding="utf-8"))
    encrypted = {c["file"] for c in labels["cvs"] if c["parse_expected"] == "encrypted"}

    def digest(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()

    for path in first.iterdir():
        if path.name not in encrypted:
            assert digest(path) == digest(second / path.name), path.name


def test_gold_labels_follow_the_fairness_rules(labels: dict[str, Any]) -> None:
    """Missing evidence is never labelled a fail; foreign qualifications need verification."""
    allowed = {"met", "partial", "missing", "needs_verification", "not_assessable"}
    for c in labels["cvs"]:
        assert set(c["expected_evidence"].values()) <= allowed
        if "foreign_qualifications" in c["variations"] and c["parse_expected"] == "ok":
            assert "needs_verification" in c["expected_evidence"].values(), c["id"]
        if c["parse_expected"] != "ok":
            assert c["hr_reference_suitability"] == "not_assessable"
