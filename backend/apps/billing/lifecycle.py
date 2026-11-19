"""Subscription lifecycle (P14-T06/T07, EC-BIL-04).

``on_invoice_paid`` - paying an invoice settles the subscription: a plan change paid for takes
effect, and a subscription in grace (``past_due``) or ``read_only`` becomes ``active`` again
immediately (reactivation on payment).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from apps.audit import services as audit
from apps.core.time import now

from .models import Invoice, Plan, Subscription, SubscriptionStatus


def on_invoice_paid(invoice: Invoice) -> None:
    from .invoicing import add_months

    if invoice.subscription_id is None:
        return
    sub = Subscription.objects.unscoped().select_for_update().get(pk=invoice.subscription_id)
    before: dict[str, Any] = {"status": sub.status, "plan": sub.plan_id}
    plan_code = (invoice.snapshot or {}).get("plan")
    changed = []
    if plan_code and plan_code != sub.plan.code:
        plan = Plan.objects.filter(code=plan_code).first()
        if plan is not None:
            sub.plan = plan
            changed.append("plan")
    if sub.status != SubscriptionStatus.ACTIVE:
        sub.status = SubscriptionStatus.ACTIVE
        sub.grace_until = None
        changed += ["status", "grace_until"]
    moment = now()
    if sub.current_period_end is None or sub.current_period_end <= moment or "plan" in changed:
        sub.current_period_start = moment
        sub.current_period_end = add_months(moment)
        changed += ["current_period_start", "current_period_end"]
    if sub.trial_ends_at and sub.trial_ends_at > moment:
        sub.trial_ends_at = moment  # a paid plan ends the trial
        changed.append("trial_ends_at")
    if not changed:
        return
    sub.save(update_fields=[*sorted(set(changed)), "updated_at"])
    audit.record(
        actor=None,
        actor_type="system",
        action="billing.subscription_settled",
        target=sub,
        organisation=sub.organisation_id,
        before=before,
        after={"status": sub.status, "plan": str(sub.plan_id), "invoice": invoice.number},
    )


# --- dunning (P14-T07) ----------------------------------------------------------------------------
GRACE_DAYS = 7
REMIND_BEFORE_DUE = timedelta(days=3)
TRIAL_REMIND_BEFORE = timedelta(days=5)


def _admins(organisation_id: Any) -> Any:
    from apps.organisations.models import Membership, Role

    return (
        Membership.objects.for_org(organisation_id)
        .filter(status=Membership.Status.ACTIVE, role=Role.ORG_ADMIN)
        .select_related("user", "organisation")
    )


def _tell(organisation_id: Any, key: str, context: dict[str, str], dedupe: str) -> None:
    from django.conf import settings

    from apps.notifications import delivery as notifications

    for m in _admins(organisation_id):
        notifications.notify(
            m.user,
            key,
            {
                "organisation_name": m.organisation.name,
                "billing_url": f"{settings.FRONTEND_URL}/hr/settings/billing",
                **context,
            },
            dedupe_key=f"{dedupe}:{m.user_id}",
            organisation=m.organisation,
        )


def _day(moment: Any) -> str:
    return f"{moment.day} {moment:%B %Y}" if moment else ""


def sweep() -> dict[str, int]:
    """Daily: reminders before due, overdue -> grace (past_due), grace over -> read_only;
    trials end the same way. Public vacancies are never touched (EC-BIL-04)."""
    moment = now()
    out = {"due_soon": 0, "overdue": 0, "read_only": 0, "trial_ending": 0, "trial_ended": 0}
    open_invoices = Invoice.objects.unscoped().filter(status="open", due_at__isnull=False)
    for inv in open_invoices.filter(due_at__gt=moment, due_at__lte=moment + REMIND_BEFORE_DUE):
        _tell(
            inv.organisation_id,
            "invoice_due_soon",
            {
                "invoice_number": inv.number,
                "amount": f"{inv.currency} {inv.amount:,.2f}",
                "due_date": _day(inv.due_at),
            },
            f"invoice_due_soon:{inv.pk}",
        )
        out["due_soon"] += 1
    for inv in open_invoices.filter(due_at__lte=moment).select_related("subscription"):
        sub = inv.subscription
        if sub is None or sub.status != SubscriptionStatus.ACTIVE:
            continue
        grace = max(inv.due_at, moment) + timedelta(days=GRACE_DAYS)
        Subscription.objects.unscoped().filter(pk=sub.pk, status=SubscriptionStatus.ACTIVE).update(
            status=SubscriptionStatus.PAST_DUE, grace_until=grace, updated_at=moment
        )
        _record(sub, "billing.subscription_past_due", {"invoice": inv.number})
        _tell(
            inv.organisation_id,
            "invoice_overdue",
            {
                "invoice_number": inv.number,
                "amount": f"{inv.currency} {inv.amount:,.2f}",
                "grace_date": _day(grace),
            },
            f"invoice_overdue:{inv.pk}",
        )
        out["overdue"] += 1
    trials = Subscription.objects.unscoped().filter(status=SubscriptionStatus.TRIALING)
    for sub in trials.filter(
        trial_ends_at__gt=moment, trial_ends_at__lte=moment + TRIAL_REMIND_BEFORE
    ):
        _tell(
            sub.organisation_id,
            "trial_ending",
            {"trial_end": _day(sub.trial_ends_at)},
            f"trial_ending:{sub.pk}",
        )
        out["trial_ending"] += 1
    for sub in trials.filter(trial_ends_at__lte=moment):
        grace = moment + timedelta(days=GRACE_DAYS)
        Subscription.objects.unscoped().filter(
            pk=sub.pk, status=SubscriptionStatus.TRIALING
        ).update(status=SubscriptionStatus.PAST_DUE, grace_until=grace, updated_at=moment)
        _record(sub, "billing.trial_ended", {})
        _tell(
            sub.organisation_id, "trial_ended", {"grace_date": _day(grace)}, f"trial_ended:{sub.pk}"
        )
        out["trial_ended"] += 1
    for sub in Subscription.objects.unscoped().filter(
        status=SubscriptionStatus.PAST_DUE, grace_until__lte=moment
    ):
        Subscription.objects.unscoped().filter(
            pk=sub.pk, status=SubscriptionStatus.PAST_DUE
        ).update(status=SubscriptionStatus.READ_ONLY, updated_at=moment)
        _record(sub, "billing.subscription_read_only", {})
        _tell(
            sub.organisation_id, "subscription_read_only", {}, f"read_only:{sub.pk}:{moment.date()}"
        )
        out["read_only"] += 1
    return out


def _record(sub: Subscription, action: str, after: dict[str, Any]) -> None:
    audit.record(
        actor=None,
        actor_type="system",
        action=action,
        target=sub,
        organisation=sub.organisation_id,
        after=after,
    )
