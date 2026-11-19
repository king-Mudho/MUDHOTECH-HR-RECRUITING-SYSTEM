"""Platform admin console reads and actions (P14-T01, docs/01 M20).

Platform scope: these functions read across organisations on purpose (platform staff only, enforced
in the views) and return aggregates or minimal identifiers - never CV content, answers or
screening detail. Every write is audited with the platform actor.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate

from apps.audit import services as audit
from apps.core.exceptions import DomainError, NotFoundError
from apps.core.time import now

KNOWN_FLAGS = {
    "ai.screening": "AI-assisted screening (platform kill-switch)",
    "jobs.ai_suggestions": "AI suggestions while writing vacancies",
}


# --- overview ---------------------------------------------------------------------------------
def _safe(fn: Any) -> Any:
    try:
        return fn()
    except Exception as exc:
        return {"error": type(exc).__name__}


def queue_health() -> dict[str, Any]:
    from apps.core import ops_metrics

    out: dict[str, Any] = {}
    for name, collector in (
        ("queues", ops_metrics._queue_depths),
        ("processing_backlog", ops_metrics._processing_backlog),
        ("outbox_lag", ops_metrics._outbox_lag),
        ("dead_letters", ops_metrics._dead_letters),
        ("email_failure_rate", ops_metrics._email_failure_rate),
    ):
        result = _safe(collector)
        if isinstance(result, dict):
            out[name] = result
        else:
            out[name] = [
                {"metric": m[0], "value": m[1], "unit": m[2], "dimensions": m[3]} for m in result
            ]
    return out


def overview() -> dict[str, Any]:
    from apps.applications.models import Application
    from apps.core.models import DeadLetter
    from apps.jobs.models import Job, JobStatus
    from apps.organisations.models import Organisation
    from apps.resumes.models import ExtractionRun, RunStatus

    moment = now()
    since = moment - timedelta(days=14)
    per_day = dict(
        Application.objects.unscoped()
        .filter(submitted_at__gte=since)
        .annotate(day=TruncDate("submitted_at"))
        .values_list("day")
        .annotate(n=Count("pk"))
        .values_list("day", "n")
    )
    days = [(moment - timedelta(days=i)).date() for i in range(13, -1, -1)]
    day_ago = moment - timedelta(hours=24)
    runs = ExtractionRun.objects.unscoped().filter(finished_at__gte=day_ago)
    runs_total = runs.count()
    return {
        "tenants": dict(
            Organisation.objects.values_list("status")
            .annotate(n=Count("pk"))
            .values_list("status", "n")
        ),
        "active_vacancies": Job.objects.unscoped().filter(status=JobStatus.PUBLISHED).count(),
        "applications_per_day": [{"day": d.isoformat(), "count": per_day.get(d, 0)} for d in days],
        "error_rates": {
            "dead_letters_open": DeadLetter.objects.filter(resolved_at__isnull=True).count(),
            "dead_letters_24h": DeadLetter.objects.filter(created_at__gte=day_ago).count(),
            "extraction_runs_24h": runs_total,
            "extraction_failure_rate_24h": round(
                runs.filter(status=RunStatus.FAILED).count() / runs_total, 4
            )
            if runs_total
            else None,
        },
        "health": queue_health(),
    }


# --- organisations ----------------------------------------------------------------------------
def organisation_detail(org_id: Any) -> dict[str, Any]:
    from apps.applications.models import Application, ApplicationDocument
    from apps.documents.models import Document
    from apps.jobs.models import Job, JobStatus
    from apps.organisations.models import Membership, Organisation
    from apps.screening.models import Evaluation

    org = Organisation.objects.filter(pk=org_id).first()
    if org is None:
        raise NotFoundError()
    month = now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    members = dict(
        Membership.objects.for_org(org.pk)
        .filter(status=Membership.Status.ACTIVE)
        .values_list("role")
        .annotate(n=Count("pk"))
        .values_list("role", "n")
    )
    linked = ApplicationDocument.objects.for_org(org.pk).values("document_id")
    storage = Document.objects.filter(
        Q(organisation_id=org.pk) | Q(pk__in=linked), deleted_at__isnull=True
    )
    return {
        "id": org.pk,
        "name": org.name,
        "slug": org.slug,
        "status": org.status,
        "verified_at": org.verified_at,
        "created_at": org.created_at,
        "members_by_role": members,
        "usage": {
            "active_vacancies": Job.objects.for_org(org.pk)
            .filter(status=JobStatus.PUBLISHED)
            .count(),
            "applications_this_month": Application.objects.for_org(org.pk)
            .filter(submitted_at__gte=month)
            .count(),
            "ai_evaluations_this_month": Evaluation.objects.for_org(org.pk)
            .filter(created_at__gte=month)
            .count(),
            "storage_bytes": int(storage.aggregate(n=Sum("size_bytes"))["n"] or 0),
        },
    }


# --- users ------------------------------------------------------------------------------------
def search_users(q: str, limit: int = 25) -> list[dict[str, Any]]:
    """Platform user search with minimal PII: email, name, platform role, memberships count."""
    from apps.accounts.models import User

    text = q.strip()
    if len(text) < 3:
        return []
    rows = (
        User.objects.filter(
            Q(email__icontains=text) | Q(first_name__icontains=text) | Q(last_name__icontains=text)
        )
        .annotate(memberships_count=Count("memberships", distinct=True))
        .order_by("email")[:limit]
    )
    return [
        {
            "id": u.pk,
            "email": u.email,
            "name": u.full_name,
            "platform_role": u.platform_role,
            "is_active": u.is_active,
            "memberships": u.memberships_count,
            "last_login": u.last_login,
        }
        for u in rows
    ]


# --- feature flags ----------------------------------------------------------------------------
def list_flags() -> list[dict[str, Any]]:
    from apps.core.models import FeatureFlag

    rows: dict[str, dict[str, Any]] = {
        key: {"key": key, "description": text, "global": None, "overrides": []}
        for key, text in KNOWN_FLAGS.items()
    }
    for f in FeatureFlag.objects.select_related("organisation").order_by("key"):
        slot = rows.setdefault(
            f.key, {"key": f.key, "description": f.description, "global": None, "overrides": []}
        )
        if f.organisation_id is None:
            slot["global"] = f.enabled
        else:
            slot["overrides"].append(
                {
                    "organisation_id": f.organisation_id,
                    "organisation_name": f.organisation.name if f.organisation else "",
                    "enabled": f.enabled,
                }
            )
    return list(rows.values())


def set_flag(actor: Any, key: str, enabled: bool, organisation_id: Any = None) -> None:
    from apps.core import flags

    if not key or len(key) > 100 or not all(c.isalnum() or c in "._-" for c in key):
        raise DomainError("validation_error", "Invalid flag key.", details={"key": ["Invalid."]})
    flags.set_flag(key, enabled, organisation_id)
    flags.invalidate(key)
    audit.record(
        actor=actor,
        action="platform.flag_set",
        target=("feature_flag", key),
        organisation=organisation_id,
        after={"enabled": enabled, "organisation_id": str(organisation_id or "")},
    )


# --- dead letters -----------------------------------------------------------------------------
def dead_letters(include_resolved: bool = False, limit: int = 100) -> Any:
    from apps.core.models import DeadLetter

    qs = DeadLetter.objects.order_by("-created_at")
    if not include_resolved:
        qs = qs.filter(resolved_at__isnull=True)
    return qs[:limit]
