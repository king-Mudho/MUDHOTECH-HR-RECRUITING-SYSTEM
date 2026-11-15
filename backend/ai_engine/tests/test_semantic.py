"""Embedding service (P06-T10): caching, batching, matcher threshold, optional real model."""

from __future__ import annotations

import importlib.util
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from ai_engine.matching import semantic
from ai_engine.matching.semantic import (
    EmbeddingService,
    HashingEncoder,
    SemanticSkillMatcher,
    SkillVector,
    cosine,
    get_encoder,
    pack,
    unpack,
)

ROOT = Path(__file__).resolve().parents[2]


class DictCache:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

    def get_many(self, keys: Iterable[str]) -> Mapping[str, Any]:
        return {k: self.data[k] for k in keys if k in self.data}

    def set_many(self, data: dict[str, Any], timeout: Any = None) -> None:
        self.data.update(data)


class CountingEncoder(HashingEncoder):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[int] = []

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(len(texts))
        return super().encode(texts)


def test_hashing_encoder_is_deterministic_unit_length() -> None:
    enc = HashingEncoder()
    a, b = enc.encode(["Python programming", "python   PROGRAMMING"])
    assert a == b and len(a) == 384
    assert math.isclose(sum(x * x for x in a), 1.0, rel_tol=1e-9)
    assert cosine(a, enc.encode(["Python developer"])[0]) > cosine(a, enc.encode(["Wound care"])[0])


def test_pack_round_trip() -> None:
    vector = HashingEncoder().encode(["Django"])[0]
    assert unpack(pack(vector)) == pytest.approx(vector, abs=1e-6)
    assert len(pack(vector)) == 384 * 4  # float32


def test_service_caches_by_normalised_text_and_batches() -> None:
    enc = CountingEncoder()
    cache = DictCache()
    svc = EmbeddingService(enc, cache)
    texts = [f"skill {i}" for i in range(70)] + ["Skill 0", "skill  1"]
    vectors = svc.embed(texts)
    assert len(vectors) == 72 and svc.encoded == 70
    assert enc.calls == [32, 32, 6]  # batches of 32, duplicates encoded once
    assert vectors[70] == pytest.approx(vectors[0], abs=1e-6)
    again = EmbeddingService(enc, cache)
    again.embed(["skill 5", "SKILL 6"])
    assert again.encoded == 0  # served from the cache
    assert svc.key("Python") != EmbeddingService(HashingEncoder(dimensions=64)).key("Python")


def test_get_encoder_is_a_per_process_singleton() -> None:
    assert get_encoder("hashing-384") is get_encoder("hashing-384")
    assert isinstance(get_encoder("hashing-384"), HashingEncoder)


def test_matcher_threshold_and_ordering() -> None:
    svc = EmbeddingService(HashingEncoder())
    names = ["Python", "Django", "Wound care", "Payroll"]
    skills = [SkillVector(n.lower(), n, v) for n, v in zip(names, svc.embed(names), strict=True)]
    matcher = SemanticSkillMatcher(svc, skills, threshold=0.5)
    assert matcher("python") == ("python", "Python", pytest.approx(1.0, abs=1e-4))
    assert matcher("completely unrelated phrase") is None
    nearest = matcher.nearest("wound dressing care", k=2)
    assert nearest[0][0].name == "Wound care" and nearest[0][1] >= nearest[1][1]
    assert SemanticSkillMatcher(svc, [], threshold=0.1)("python") is None


@pytest.mark.skipif(
    importlib.util.find_spec("sentence_transformers") is None,
    reason="ml extra not installed (worker image only)",
)
def test_real_model_matches_equivalent_wording() -> None:  # pragma: no cover - worker image
    """all-MiniLM-L6-v2: synonyms from the synthetic corpus land on the right skill."""
    svc = EmbeddingService(semantic.get_encoder(semantic.DEFAULT_MODEL))
    doc = json.loads((ROOT / "fixtures/taxonomy/skills.json").read_text(encoding="utf-8"))
    names = [s["name"] for s in doc["skills"]]
    texts = [
        f"{s['name']} ({', '.join(s['aliases'][:8])})" if s["aliases"] else s["name"]
        for s in doc["skills"]
    ]
    skills = [SkillVector(n, n, v) for n, v in zip(names, svc.embed(texts), strict=True)]
    matcher = SemanticSkillMatcher(svc, skills, threshold=0.5)
    pairs = {
        "RESTful web services": "REST APIs",
        "version control with GitHub": "Git",
        "relational databases (Postgres)": "PostgreSQL",
        "giving prescribed drugs safely": "Medication administration",
        "monthly salary processing": "Payroll",
        "charts and dashboards for managers": "Data visualisation",
    }
    hits = sum(
        1
        for phrase, want in pairs.items()
        if want in [s.name for s, _ in matcher.nearest(phrase, 3)]
    )
    assert hits >= 4, hits
