"""Synthetic vacancy factories (docs/09 §3: make_published_job)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import factory

from apps.core import time
from apps.jobs.models import Job, JobCriterion, JobVersion, Rubric
from apps.organisations.tests.factories import OrganisationFactory

DEFAULT_RUBRIC: list[dict[str, Any]] = [
    {"key": "technical", "label": "Technical skills", "weight": 35},
    {"key": "experience", "label": "Relevant experience", "weight": 25},
    {"key": "competency", "label": "Job competencies", "weight": 20},
    {"key": "qualification", "label": "Qualifications", "weight": 10},
    {"key": "answers", "label": "Screening answers", "weight": 10},
]
BANDS = [
    {"score": 0, "descriptor": "No evidence"},
    {"score": 25, "descriptor": "Limited evidence"},
    {"score": 50, "descriptor": "Meets some expectations"},
    {"score": 75, "descriptor": "Meets expectations"},
    {"score": 100, "descriptor": "Exceeds expectations"},
]


def default_rubric_categories() -> list[dict[str, Any]]:
    return [{**c, "bands": [dict(b) for b in BANDS]} for c in DEFAULT_RUBRIC]


class JobFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Job
        skip_postgeneration_save = True

    organisation = factory.SubFactory(OrganisationFactory)
    title = factory.Sequence(lambda n: f"Software Developer {n}")
    slug = factory.Sequence(lambda n: f"software-developer-{n}")
    closes_at = factory.LazyFunction(lambda: time.now() + timedelta(days=21))

    @factory.post_generation
    def version(self, create: bool, extracted: Any, **kwargs: Any) -> None:
        if not create:
            return
        version = JobVersion.objects.create(
            organisation=self.organisation,
            job=self,
            number=1,
            summary="Build and maintain web applications for our clients.",
            responsibilities_html="<ul><li>Write clean, tested code</li></ul>",
            requirements_html="<p>Python, Django and PostgreSQL experience.</p>",
            required_documents=["cv"],
        )
        Rubric.objects.create(
            organisation=self.organisation,
            job_version=version,
            categories=default_rubric_categories(),
            total_weight=100,
        )
        JobCriterion.objects.create(
            organisation=self.organisation,
            job_version=version,
            order=1,
            type="skill",
            importance="essential",
            title="Python",
            justification="Core language of the stack.",
            rubric_category="technical",
        )
        self.current_version = version
        self.save(update_fields=["current_version"])
