"""Skill embedding precompute and semantic matcher (P06-T10)."""

from __future__ import annotations

from io import StringIO
from typing import Any

import pytest
from django.core.management import call_command
from django.test import override_settings

from ai_engine.matching import semantic
from apps.organisations.models import Organisation
from apps.taxonomy import embeddings
from apps.taxonomy.models import Skill, SkillAlias, SkillCategory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _fresh() -> Any:
    embeddings.clear_matchers()
    yield
    embeddings.clear_matchers()


def make_skill(name: str, *aliases: str, org: Organisation | None = None) -> Skill:
    skill = Skill.objects.create(
        canonical_name=name,
        slug=name.lower().replace(" ", "-") + (f"-{org.pk}" if org else ""),
        category=SkillCategory.SOFTWARE_IT,
        organisation=org,
    )
    for alias in aliases:
        SkillAlias.objects.create(skill=skill, alias=alias)
    return skill


def test_embed_command_writes_vectors_once_per_model() -> None:
    python = make_skill("Python", "py", "python3")
    make_skill("Payroll")
    Skill.objects.create(
        canonical_name="Retired", slug="retired", category="general", is_active=False
    )
    out = StringIO()
    call_command("embed_skills", stdout=out)
    assert "Embedded 2 skills" in out.getvalue()
    python.refresh_from_db()
    assert python.embedding is not None and len(python.embedding) == 384
    assert python.embedding_model == "hashing-384"
    assert embeddings.skill_text(python) == "Python (py, python3)"
    assert embeddings.embed_skills() == 0  # nothing missing
    assert embeddings.embed_skills(force=True) == 2
    assert Skill.objects.get(slug="retired").embedding is None


def test_model_change_re_embeds(monkeypatch: pytest.MonkeyPatch) -> None:
    make_skill("Python")
    embeddings.embed_skills()
    with override_settings(EMBEDDING_MODEL="hashing-64"):
        monkeypatch.setitem(semantic._ENCODERS, "hashing-64", semantic.HashingEncoder(384))
        assert embeddings.embed_skills() == 1
        assert Skill.objects.get().embedding_model == "hashing-64"


@override_settings(SEMANTIC_SKILL_THRESHOLD=0.6)
def test_matcher_includes_only_own_organisation_skills() -> None:
    org_a = Organisation.objects.create(name="A", slug="a")
    org_b = Organisation.objects.create(name="B", slug="b")
    make_skill("Python", "python3")
    make_skill("Ndebele interpreting", org=org_a)
    make_skill("Ndebele translation", org=org_b)
    embeddings.embed_skills()
    platform = embeddings.semantic_matcher()
    assert platform is not None
    found = platform("Python (python3)")
    assert found is not None and found[1] == "Python"
    assert "Ndebele interpreting" not in {s.name for s in platform.skills}  # no org skills
    for_a = embeddings.semantic_matcher(org_a.pk)
    assert for_a is not None
    names = {s.name for s in for_a.skills}
    assert "Ndebele interpreting" in names and "Ndebele translation" not in names
    assert embeddings.semantic_matcher(org_a.pk) is for_a  # cached per process


def test_no_embeddings_or_no_model_means_no_semantic_matching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    make_skill("Python")
    assert embeddings.semantic_matcher() is None  # nothing embedded yet
    embeddings.embed_skills()

    class Broken(semantic.HashingEncoder):
        def encode(self, texts: Any) -> Any:
            raise ImportError("sentence_transformers")

    monkeypatch.setitem(semantic._ENCODERS, "hashing-384", Broken())
    assert embeddings.semantic_matcher() is None  # deterministic path continues (EC-AI-06)
