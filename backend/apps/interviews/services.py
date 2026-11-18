"""Interview services (P12). P12-T01: scorecard templates derived from the vacancy's criteria."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.db import transaction

from apps.audit import services as audit
from apps.core.exceptions import DomainError
from apps.jobs.models import CriterionType, Job, JobCriterion

from .models import ScorecardTemplate

# Eligibility criteria (right to work, licences checked by documents) are verified, not rated.
NOT_RATED = {CriterionType.ELIGIBILITY}
MAX_CRITERIA = 20


def template_from_job(
    job: Job,
    *,
    actor: Any,
    name: str = "",
    extra_competencies: Iterable[str] = (),
) -> ScorecardTemplate:
    """A scorecard template with one row per rated criterion of the published version, then extra
    competencies HR wants assessed (e.g. "Communication"). Keys are stable within the template."""
    version = job.published_version
    if version is None:
        raise DomainError(
            "job_not_published", "Publish the vacancy before creating a scorecard.", 409
        )
    criteria: list[dict[str, Any]] = []
    rows = (
        JobCriterion.objects.for_org(job.organisation).filter(job_version=version).order_by("order")
    )
    for c in rows:
        if c.type in NOT_RATED:
            continue
        criteria.append(
            {
                "key": f"c{len(criteria) + 1}",
                "title": c.title,
                "description": c.evidence_guidance or c.description,
                "source_criterion_id": str(c.pk),
            }
        )
    for title in extra_competencies:
        title = title.strip()
        if title and title.lower() not in {x["title"].lower() for x in criteria}:
            criteria.append(
                {
                    "key": f"c{len(criteria) + 1}",
                    "title": title[:200],
                    "description": "",
                    "source_criterion_id": None,
                }
            )
    if not criteria:
        raise DomainError("scorecard_empty", "The scorecard needs at least one criterion.", 422)
    if len(criteria) > MAX_CRITERIA:
        raise DomainError(
            "scorecard_too_long", f"A scorecard can have at most {MAX_CRITERIA} criteria.", 422
        )
    with transaction.atomic():
        template = ScorecardTemplate.objects.create(
            organisation=job.organisation,
            job=job,
            job_version=version,
            name=(name or f"{job.title} - interview scorecard")[:120],
            criteria=criteria,
            created_by=actor,
        )
        audit.record(
            actor=actor,
            action="interviews.scorecard_template_created",
            target=template,
            organisation=job.organisation,
            after={"criteria": len(criteria), "job_id": str(job.pk)},
        )
    return template
