"""Public slugs and full-text search vectors for jobs."""

from __future__ import annotations

import re
import uuid

import nh3
from django.contrib.postgres.search import SearchVector
from django.db.models import Value
from django.utils.text import slugify

from .models import Job, JobSlugRedirect

SLUG_MAX = 120


def unique_job_slug(title: str, org_slug: str, *, exclude_job_id: uuid.UUID | None = None) -> str:
    """``<title>-<org>`` (globally unique; ``-2``, ``-3`` on collision)."""
    base = f"{slugify(title)[:70] or 'job'}-{org_slug[:40]}".strip("-")[: SLUG_MAX - 6]
    slug, n = base, 1
    while (
        Job.objects.unscoped().filter(slug=slug).exclude(pk=exclude_job_id).exists()
        or JobSlugRedirect.objects.filter(old_slug=slug).exists()
    ):
        n += 1
        slug = f"{base}-{n}"
    return slug


def plain_text(html: str) -> str:
    text = nh3.clean(html or "", tags=set())
    return re.sub(r"\s+", " ", text).strip()


def update_search_vector(job: Job) -> None:
    """Weighted FTS: A = title, B = summary + criteria + org name, C = advert body (EC-JOB-17)."""
    version = job.published_version or job.current_version
    criteria = ""
    body = ""
    summary = ""
    if version is not None:
        summary = version.summary
        criteria = " ".join(version.criteria.values_list("title", flat=True))
        body = " ".join(
            plain_text(h)
            for h in (
                version.responsibilities_html,
                version.requirements_html,
                version.benefits_html,
            )
        )
    org_name = job.organisation.name if job.organisation_id else ""
    vector = (
        SearchVector(Value(job.title), weight="A", config="english")
        + SearchVector(Value(f"{summary} {criteria} {org_name}"), weight="B", config="english")
        + SearchVector(Value(body), weight="C", config="english")
    )
    Job.objects.unscoped().filter(pk=job.pk).update(search_vector=vector)
