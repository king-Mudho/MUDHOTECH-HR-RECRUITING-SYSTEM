"""Subscription lifecycle (P14-T06/T07, EC-BIL-04).

``on_invoice_paid`` - paying an invoice settles the subscription: a plan change paid for takes
effect, and a subscription in grace (``past_due``) or ``read_only`` becomes ``active`` again
immediately (reactivation on payment).
"""

from __future__ import annotations

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
