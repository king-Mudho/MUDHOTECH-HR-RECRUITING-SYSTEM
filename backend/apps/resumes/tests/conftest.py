"""Shared fixtures for the resumes tests: fake S3, a tiny taxonomy, commit-aware calls."""

from __future__ import annotations

from typing import Any

import pytest

from apps.resumes import engine
from apps.taxonomy.models import Skill, SkillAlias


@pytest.fixture(autouse=True)
def _setup(s3: Any, settings: Any) -> None:
    settings.RESUMES_AUTOSTART = True
    engine.clear_cache()
    for name, aliases in [("Python", ["python3"]), ("Django", []), ("PostgreSQL", ["postgres"])]:
        skill = Skill.objects.create(canonical_name=name, slug=name.lower(), category="software_it")
        for alias in aliases:
            SkillAlias.objects.create(skill=skill, alias=alias)


@pytest.fixture
def act(django_capture_on_commit_callbacks: Any) -> Any:
    """Run a service call and then its on-commit callbacks (queued tasks), like a real commit."""

    def run(fn: Any, *args: Any, **kwargs: Any) -> Any:
        with django_capture_on_commit_callbacks(execute=True):
            return fn(*args, **kwargs)

    return run
