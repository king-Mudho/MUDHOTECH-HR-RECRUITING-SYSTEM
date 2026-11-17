"""Retention engine (P09-T05; D-03, docs/06 §5).

Every day: for each organisation, applications that were not hired, belong to a vacancy closed more
than ``retention_months`` ago and are not under a legal hold are anonymised (the same erasure as a
deletion request, per application). Weekly, a dry run tells each organisation's admins what the next
runs will remove. Every run is recorded in ``RetentionRun`` with counts only. Already-erased
applications are skipped, so runs are idempotent.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.db.models import Q, QuerySet

from apps.audit import services as audit
from apps.core.time import now

from .models import RetentionRun
from .services import is_held

KEEP_STATUSES = ("hired", "offer", "interview", "shortlisted")  # never removed by retention


def due_applications(organisation: Any, *, at: Any = None) -> QuerySet[Any]:
    from apps.applications.models import Application
    from apps.organisations.models import OrganisationPolicy

    moment = at or now()
    months = (
        OrganisationPolicy.objects.filter(organisation=organisation)
        .values_list("retention_months", flat=True)
        .first()
        or 12
    )
    cutoff = moment - timedelta(days=30 * int(months))
    return (
        Application.objects.for_org(organisation.pk)
        .filter(job__closed_at__isnull=False, job__closed_at__lt=cutoff)
        .exclude(status__in=[*KEEP_STATUSES, "draft"])
        .exclude(candidate_profile_snapshot__contains={"erased": True})
        .select_related("job")
    )


def run_for(organisation: Any, *, dry_run: bool) -> RetentionRun:
    from .erasure import _erase_application

    run = RetentionRun.objects.create(organisation=organisation, started_at=now(), dry_run=dry_run)
    counts: Counter[str] = Counter()
    for app in due_applications(organisation).iterator():
        if is_held(
            organisation.pk,
            application_id=app.pk,
            candidate_id=app.candidate_user_id,
            job_id=app.job_id,
        ):
            counts["held"] += 1
            continue
        counts["due"] += 1
        if dry_run:
            continue
        with transaction.atomic():
            _erase_application(app, counts)
    run.counts = dict(counts)
    run.finished_at = now()
    run.save(update_fields=["counts", "finished_at", "updated_at"])
    audit.record(
        action="privacy.retention_run",
        actor_type="system",
        target=("retention_run", str(run.pk)),
        organisation=organisation.pk,
        after={"dry_run": dry_run, **dict(counts)},
    )
    return run


def run_all(*, dry_run: bool) -> list[RetentionRun]:
    from apps.organisations.models import Organisation

    orgs = Organisation.objects.filter(~Q(status="pending_verification"))
    runs = [run_for(org, dry_run=dry_run) for org in orgs]
    if dry_run:
        _report(runs)
    return runs


def _report(runs: list[RetentionRun]) -> None:
    from django.conf import settings

    from apps.notifications import delivery as notifications

    from .rights import handlers

    for run in runs:
        due = run.counts.get("due", 0)
        if not due:
            continue
        with transaction.atomic():
            for admin in handlers(run.organisation_id):
                notifications.notify(
                    admin,
                    "retention_report",
                    {
                        "organisation_name": run.organisation.name,
                        "due_count": str(due),
                        "held_count": str(run.counts.get("held", 0)),
                        "privacy_url": f"{settings.FRONTEND_URL}/hr/settings/privacy",
                    },
                    dedupe_key=f"retention_report:{run.pk}:{admin.pk}",
                    organisation=run.organisation_id,
                )
