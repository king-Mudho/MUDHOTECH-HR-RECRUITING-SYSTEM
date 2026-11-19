"""Billing background work: metering consumers and the daily usage roll-up (P14-T04)."""

from __future__ import annotations

from celery import shared_task

from apps.core.models import OutboxEvent
from apps.core.outbox import idempotent_consumer
from apps.core.tasks import BaseTask

from . import metering
from .models import Metric


@idempotent_consumer("billing.meter_evaluation", events=["screening.completed"])
def meter_evaluation(event: OutboxEvent) -> None:
    if event.organisation_id:
        metering.increment(event.organisation_id, Metric.AI_EVALUATIONS_MONTH)


@idempotent_consumer("billing.meter_application", events=["application.submitted"])
def meter_application(event: OutboxEvent) -> None:
    if event.organisation_id:
        metering.increment(event.organisation_id, Metric.APPLICATIONS_MONTH)


@shared_task(name="apps.billing.tasks.usage_rollup", base=BaseTask)
def usage_rollup() -> int:
    return metering.rollup_all()


@shared_task(name="apps.billing.tasks.issue_due_invoices", base=BaseTask)
def issue_due_invoices() -> int:
    from . import invoicing

    return invoicing.run_monthly()


@shared_task(name="apps.billing.tasks.poll_payments", base=BaseTask)
def poll_payments() -> dict[str, int]:
    from . import payments

    return payments.poll_due()
