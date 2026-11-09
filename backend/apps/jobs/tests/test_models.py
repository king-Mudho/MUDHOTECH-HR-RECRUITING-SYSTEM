"""Job data model invariants (P03-T02)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.postgres.search import SearchQuery
from django.db import IntegrityError, transaction

from apps.jobs.models import Job, JobSlugRedirect, JobVersion, Rubric
from apps.jobs.search import plain_text, unique_job_slug, update_search_vector
from apps.jobs.tests.factories import JobFactory
from apps.organisations.tests.factories import OrganisationFactory

pytestmark = pytest.mark.django_db


def test_factory_builds_job_with_draft_version_rubric_and_criterion() -> None:
    job = JobFactory()
    v = job.current_version
    assert v is not None and v.number == 1 and v.is_editable
    assert v.rubric.total_weight == 100 and v.criteria.count() == 1
    assert job.lock_version == 1 and not job.accepts_applications


def test_openings_and_salary_constraints() -> None:
    job = JobFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        Job.objects.unscoped().filter(pk=job.pk).update(openings=0)
    with pytest.raises(IntegrityError), transaction.atomic():
        Job.objects.unscoped().filter(pk=job.pk).update(
            salary_min=Decimal("2000"), salary_max=Decimal("1000")
        )
    Job.objects.unscoped().filter(pk=job.pk).update(salary_min=Decimal("800"), salary_max=None)


def test_approved_rubric_must_total_100() -> None:
    """EC-JOB-02 (database backstop; the service validates with a friendly message)."""
    job = JobFactory()
    rubric = job.current_version.rubric  # type: ignore[union-attr]
    with pytest.raises(IntegrityError), transaction.atomic():
        Rubric.objects.unscoped().filter(pk=rubric.pk).update(status="approved", total_weight=90)
    Rubric.objects.unscoped().filter(pk=rubric.pk).update(status="draft", total_weight=90)


def test_version_numbers_unique_per_job() -> None:
    job = JobFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        JobVersion.objects.create(organisation=job.organisation, job=job, number=1)


def test_slug_generation_is_unique_and_respects_redirects() -> None:
    org = OrganisationFactory(slug="mudhotech")
    first = unique_job_slug("Software Developer!", org.slug)
    assert first == "software-developer-mudhotech"
    JobFactory(organisation=org, slug=first)
    second = unique_job_slug("Software Developer", org.slug)
    assert second == "software-developer-mudhotech-2"
    JobSlugRedirect.objects.create(old_slug=second, job=Job.objects.unscoped().get(slug=first))
    assert unique_job_slug("Software Developer", org.slug) == "software-developer-mudhotech-3"
    job = Job.objects.unscoped().get(slug=first)
    assert unique_job_slug("Software Developer", org.slug, exclude_job_id=job.pk) == first


def test_search_vector_ranks_title_and_body() -> None:
    org = OrganisationFactory(name="Acme Mining Zimbabwe")
    dev = JobFactory(organisation=org, title="Senior Django Developer")
    nurse = JobFactory(organisation=org, title="Registered Nurse")
    for job in (dev, nurse):
        update_search_vector(job)
    hits = Job.objects.unscoped().filter(search_vector=SearchQuery("senior", config="english"))
    assert list(hits) == [dev]
    by_org = Job.objects.unscoped().filter(search_vector=SearchQuery("acme", config="english"))
    assert set(by_org) == {dev, nurse}
    by_body = Job.objects.unscoped().filter(
        search_vector=SearchQuery("postgresql", config="english")
    )
    assert set(by_body) == {dev, nurse}


def test_plain_text_strips_markup() -> None:
    assert plain_text("<p>Hello <strong>world</strong></p>\n<script>x</script>") == "Hello world"
