"""AI-assist stub (P03-T08): flag-gated, deterministic, suggestions only."""

from __future__ import annotations

import pytest

from apps.core import flags
from apps.jobs.models import JobCriterion
from apps.jobs.suggestions import FLAG, SuggestionsDisabledError, extract_skills, suggest
from apps.jobs.tests.factories import JobFactory
from apps.organisations.models import OrganisationPolicy
from apps.questionnaires.validation import validate_questions
from apps.taxonomy.models import Skill, SkillAlias

pytestmark = pytest.mark.django_db


@pytest.fixture
def taxonomy() -> None:
    for name in ("Python", "Django", "PostgreSQL", "Machine learning", "Go"):
        Skill.objects.create(
            canonical_name=name, slug=name.lower().replace(" ", "-"), category="software_it"
        )
    SkillAlias.objects.create(
        skill=Skill.objects.get(canonical_name="PostgreSQL"), alias="postgres"
    )


def test_extracts_skills_by_name_and_alias_longest_first(taxonomy: None) -> None:
    text = "We use Python/Django with Postgres. Experience in machine learning is a plus. Let's go!"
    names = [s.canonical_name for s in extract_skills(text)]
    assert names == ["Python", "Django", "PostgreSQL", "Machine learning", "Go"]
    assert extract_skills("Nothing relevant here") == []


def test_disabled_by_default_and_respects_policy(taxonomy: None) -> None:
    job = JobFactory()
    with pytest.raises(SuggestionsDisabledError):
        suggest(job)
    flags.set_flag(FLAG, True, job.organisation)
    flags.invalidate(FLAG)
    OrganisationPolicy.objects.filter(organisation=job.organisation).update(ai_enabled=False)
    with pytest.raises(SuggestionsDisabledError):
        suggest(job)


def test_suggestions_are_preferred_unsaved_and_valid(taxonomy: None) -> None:
    job = JobFactory()  # factory requirements mention Python, Django and PostgreSQL
    python = Skill.objects.get(canonical_name="Python")
    JobCriterion.objects.filter(job_version=job.current_version).update(skill=python)
    flags.set_flag(FLAG, True, job.organisation)
    flags.invalidate(FLAG)
    before = JobCriterion.objects.for_org(job.organisation).count()
    result = suggest(job)
    assert result["requires_acceptance"] is True
    titles = [c["title"] for c in result["criteria"]]
    assert "Python" not in titles  # already a criterion
    assert {"Django", "PostgreSQL"} <= set(titles)
    assert all(c["importance"] == "preferred" for c in result["criteria"])
    assert validate_questions(result["questions"]) == {}
    assert JobCriterion.objects.for_org(job.organisation).count() == before
