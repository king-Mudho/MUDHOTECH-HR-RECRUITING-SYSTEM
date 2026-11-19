"""Plan entitlements (P14-T03, docs/01 M20, EC-BIL-03/04).

``check(org, metric)`` is called by the staff actions that consume a plan limit:

* publishing / scheduling / resuming a vacancy -> ``active_vacancies``
* inviting a member -> ``seats`` (active staff + open invitations)
* starting a screening run -> ``ai_evaluations_month``
* organisation-owned staff uploads -> ``storage_gb``

and raises ``PlanLimitError`` (an upgrade prompt for the UI) when the action would exceed the plan.
A subscription in ``read_only`` or ``cancelled`` blocks those staff actions too.

**Candidates are never blocked** (EC-BIL-03): applying to an already-published vacancy, uploading
a CV (also through assisted applications) and submitting never call ``check``. When the monthly
AI-evaluation allowance is used up, new applications are still accepted and routed to human
review instead of being screened (``ai_evaluations_available``).

Usage is computed from the source data (published vacancies, memberships, evaluations, stored
documents) so a limit can never drift from reality; ``apps.billing.metering`` keeps the monthly
counters for reporting and invoices.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum

from apps.core.exceptions import DomainError
from apps.core.time import now

from .models import Metric, Plan, Subscription, SubscriptionStatus

TRIAL_DAYS = 30
GB = 1024**3
BLOCKING_STATUSES = (SubscriptionStatus.READ_ONLY, SubscriptionStatus.CANCELLED)
# document purposes that belong to candidates: never limited
CANDIDATE_PURPOSES = ("cv", "supporting", "message_attachment")


class PlanLimitError(DomainError):
    def __init__(self, metric: str, limit: int, used: float, plan: Plan) -> None:
        super().__init__(
            "plan_limit_reached",
            f"Your {plan.name} plan allows {limit} {Metric(metric).label.lower()}. "
            "Upgrade the plan to continue.",
            403,
            {"metric": metric, "limit": limit, "used": used, "plan": plan.code},
        )


class BillingReadOnlyError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "billing_read_only",
            "This organisation is read-only until the overdue invoice is paid. "
            "Published vacancies stay open to candidates until their closing date.",
            403,
        )


def month_start() -> Any:
    return now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def subscription_for(organisation_id: Any) -> Subscription:
    """The organisation's subscription; a 30-day trial is started the first time it is needed."""
    org_id = getattr(organisation_id, "pk", organisation_id)
    sub = Subscription.objects.for_org(org_id).select_related("plan").first()
    if sub is not None:
        return sub
    trial = Plan.objects.filter(is_trial=True, active=True).order_by("order").first()
    if trial is None:  # plans are seeded on migrate; recreate if someone deleted them
        from .plans import seed_default_plans

        seed_default_plans()
        trial = Plan.objects.get(code="trial")
    moment = now()
    try:
        with transaction.atomic():
            sub = Subscription.objects.create(
                organisation_id=org_id,
                plan=trial,
                status=SubscriptionStatus.TRIALING,
                trial_ends_at=moment + timedelta(days=TRIAL_DAYS),
                current_period_start=moment,
                current_period_end=moment + timedelta(days=TRIAL_DAYS),
            )
    except IntegrityError:  # created concurrently
        sub = Subscription.objects.for_org(org_id).select_related("plan").get()
    return sub


def usage(organisation_id: Any, metric: str) -> float:
    org_id = getattr(organisation_id, "pk", organisation_id)
    if metric == Metric.ACTIVE_VACANCIES:
        from apps.jobs.models import Job, JobStatus

        return Job.objects.for_org(org_id).filter(status=JobStatus.PUBLISHED).count()
    if metric == Metric.SEATS:
        from apps.organisations.models import Invitation, Membership

        members = Membership.objects.for_org(org_id).filter(status=Membership.Status.ACTIVE)
        pending = Invitation.objects.for_org(org_id).filter(
            accepted_at__isnull=True, revoked_at__isnull=True, expires_at__gt=now()
        )
        return members.count() + pending.count()
    if metric == Metric.AI_EVALUATIONS_MONTH:
        from apps.screening.models import Evaluation

        return Evaluation.objects.for_org(org_id).filter(created_at__gte=month_start()).count()
    if metric == Metric.APPLICATIONS_MONTH:
        from apps.applications.models import Application

        return Application.objects.for_org(org_id).filter(submitted_at__gte=month_start()).count()
    if metric == Metric.STORAGE_GB:
        from apps.applications.models import ApplicationDocument
        from apps.documents.models import Document

        linked = ApplicationDocument.objects.for_org(org_id).values("document_id")
        total = Document.objects.filter(
            Q(organisation_id=org_id) | Q(pk__in=linked), deleted_at__isnull=True
        ).aggregate(n=Sum("size_bytes"))["n"]
        return round(int(total or 0) / GB, 3)
    raise ValueError(metric)


def limit_for(sub: Subscription, metric: str) -> int | None:
    value = (sub.plan.limits or {}).get(metric)
    return None if value is None else int(value)


def check(organisation_id: Any, metric: str, *, increment: float = 1, exclude: int = 0) -> None:
    """Raise when the staff action would exceed the plan (``exclude`` discounts rows the action
    replaces, e.g. an invitation re-sent to the same address)."""
    if not settings.BILLING_ENFORCE:
        return
    sub = subscription_for(organisation_id)
    if sub.status in BLOCKING_STATUSES:
        raise BillingReadOnlyError()
    limit = limit_for(sub, metric)
    if limit is None:
        return
    used = usage(organisation_id, metric) - exclude
    if used + increment > limit:
        raise PlanLimitError(metric, limit, used, sub.plan)


def assert_writable(organisation_id: Any) -> None:
    if settings.BILLING_ENFORCE and subscription_for(organisation_id).status in BLOCKING_STATUSES:
        raise BillingReadOnlyError()


def ai_evaluations_available(organisation_id: Any) -> bool:
    """For automatic screening after a submission: never blocks the candidate - when this is
    False the application goes to human review instead."""
    if not settings.BILLING_ENFORCE:
        return True
    sub = subscription_for(organisation_id)
    limit = limit_for(sub, Metric.AI_EVALUATIONS_MONTH)
    return limit is None or usage(organisation_id, Metric.AI_EVALUATIONS_MONTH) < limit


def summary(organisation_id: Any) -> dict[str, Any]:
    sub = subscription_for(organisation_id)
    return {
        "metrics": [
            {
                "metric": m.value,
                "label": m.label,
                "used": usage(organisation_id, m.value),
                "limit": limit_for(sub, m.value),
            }
            for m in Metric
        ]
    }
