"""Payments (P14-T06, EC-BIL-01/02).

* ``start_payment`` - an organisation admin pays an open invoice: web checkout (card) returns a
  Paynow URL; EcoCash/OneMoney push a prompt to the payer's phone.
* ``handle_result`` - the result-URL callback: the hash is verified with the integration key and
  then the status is **re-read from Paynow's poll URL** before anything is marked paid (EC-BIL-01).
* ``poll_due`` - beat: pending payments are polled with backoff for up to 15 minutes, then marked
  ``pending_manual_check`` (EC-BIL-02).
* ``apply_status`` - idempotent: a payment is applied once; a paid amount that differs from the
  invoice goes to manual check; paying settles the invoice and reactivates a lapsed subscription.
* ``record_manual_payment`` - platform admins record bank transfers.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings
from django.db import transaction

from apps.audit import services as audit
from apps.core.exceptions import DomainError, NotFoundError
from apps.core.time import now

from . import paynow
from .models import (
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentMethod,
    PaymentProvider,
    PaymentStatus,
)

POLL_DELAYS = (15, 30, 60, 120, 180, 240, 300)  # seconds between polls
POLL_WINDOW = timedelta(minutes=15)
PENDING = (PaymentStatus.CREATED, PaymentStatus.SENT)
PAID_WORDS = ("paid", "awaiting delivery", "delivered")
FAILED_WORDS = ("failed", "disputed")
CANCELLED_WORDS = ("cancelled",)


def _reference(invoice: Invoice) -> str:
    n = Payment.objects.unscoped().filter(invoice=invoice).count() + 1
    return f"{invoice.number}-{n}"


def start_payment(
    membership: Any, invoice_id: Any, *, method: str, phone: str = ""
) -> tuple[Payment, dict[str, str]]:
    if method not in (PaymentMethod.CARD, PaymentMethod.ECOCASH, PaymentMethod.ONEMONEY):
        raise DomainError("validation_error", "Choose a payment method.", details={"method": ["?"]})
    invoice = (
        Invoice.objects.for_org(membership.organisation_id)
        .select_related("organisation")
        .filter(pk=invoice_id)
        .first()
    )
    if invoice is None:
        raise NotFoundError()
    if invoice.status != InvoiceStatus.OPEN:
        raise DomainError("invoice_not_open", "This invoice is not open for payment.", 409)
    mobile = method in (PaymentMethod.ECOCASH, PaymentMethod.ONEMONEY)
    msisdn = paynow.local_msisdn(phone) if mobile else None
    with transaction.atomic():
        payment = Payment.objects.create(
            organisation_id=invoice.organisation_id,
            invoice=invoice,
            provider=PaymentProvider.PAYNOW,
            method=method,
            reference=_reference(invoice),
            amount=invoice.amount,
            currency=invoice.currency,
            initiated_by=membership.user,
        )
    reply = paynow.initiate(
        invoice.currency,
        reference=payment.reference,
        amount=f"{invoice.amount:.2f}",
        description=f"Invoice {invoice.number}",
        email=membership.user.email,
        return_url=f"{settings.FRONTEND_URL}/hr/settings/billing?payment={payment.pk}",
        result_url=f"{settings.PAYNOW_RESULT_URL_BASE}/api/v1/billing/paynow/result/",
        phone=msisdn,
        method=method if mobile else None,
    )
    Payment.objects.for_org(payment.organisation_id).filter(pk=payment.pk).update(
        status=PaymentStatus.SENT,
        poll_url=reply.get("pollurl", ""),
        raw={"initiate": paynow.sanitise(reply)},
        next_poll_at=now() + timedelta(seconds=POLL_DELAYS[0]),
    )
    payment.refresh_from_db()
    audit.record(
        actor=membership.user,
        action="billing.payment_started",
        target=payment,
        organisation=payment.organisation_id,
        after={"method": method, "amount": str(payment.amount), "invoice": invoice.number},
    )
    return payment, {
        "redirect_url": reply.get("browserurl", "") if not mobile else "",
        "instructions": reply.get("instructions", ""),
    }


def _word(status: str) -> str:
    return (status or "").strip().lower()


def apply_status(payment_id: Any, reply: dict[str, str], *, source: str) -> Payment:
    """Idempotent application of a verified provider status."""
    from .lifecycle import on_invoice_paid

    with transaction.atomic():
        payment = (
            Payment.objects.unscoped()  # provider callback: no request organisation
            .select_for_update()
            .select_related("invoice")
            .get(pk=payment_id)
        )
        word = _word(reply.get("status", ""))
        raw = dict(payment.raw or {})
        raw[f"{source}:{now().isoformat()}"] = paynow.sanitise(reply)
        payment.raw = raw
        if payment.status == PaymentStatus.PAID:
            payment.save(update_fields=["raw", "updated_at"])
            return payment  # already applied (duplicate callback or poll)
        if word in PAID_WORDS:
            try:
                paid_amount = Decimal(reply.get("amount", "") or "0")
            except InvalidOperation:
                paid_amount = Decimal("0")
            if paid_amount != payment.amount:
                payment.status = PaymentStatus.PENDING_MANUAL_CHECK
                payment.save(update_fields=["status", "raw", "updated_at"])
                audit.record(
                    actor=None,
                    actor_type="system",
                    action="billing.payment_amount_mismatch",
                    target=payment,
                    organisation=payment.organisation_id,
                    after={"expected": str(payment.amount), "reported": str(paid_amount)},
                )
                return payment
            payment.status = PaymentStatus.PAID
            payment.paid_at = now()
            payment.provider_reference = reply.get("paynowreference", "")[:100]
            payment.save(
                update_fields=["status", "paid_at", "provider_reference", "raw", "updated_at"]
            )
            _settle(payment)
            on_invoice_paid(payment.invoice)
        elif word in FAILED_WORDS or word in CANCELLED_WORDS:
            payment.status = (
                PaymentStatus.CANCELLED if word in CANCELLED_WORDS else PaymentStatus.FAILED
            )
            payment.next_poll_at = None
            payment.save(update_fields=["status", "next_poll_at", "raw", "updated_at"])
        else:
            payment.save(update_fields=["raw", "updated_at"])
        audit.record(
            actor=None,
            actor_type="system",
            action="billing.payment_status",
            target=payment,
            organisation=payment.organisation_id,
            after={"status": payment.status, "source": source},
        )
    return payment


def _settle(payment: Payment) -> None:
    from apps.notifications import delivery as notifications
    from apps.organisations.models import Membership, Role

    invoice = Invoice.objects.unscoped().select_for_update().get(pk=payment.invoice_id)
    if invoice.status != InvoiceStatus.PAID:
        invoice.status = InvoiceStatus.PAID
        invoice.paid_at = payment.paid_at or now()
        invoice.save(update_fields=["status", "paid_at", "updated_at"])
    org = invoice.organisation
    for m in (
        Membership.objects.for_org(invoice.organisation_id)
        .filter(status=Membership.Status.ACTIVE, role=Role.ORG_ADMIN)
        .select_related("user")
    ):
        notifications.notify(
            m.user,
            "payment_received",
            {
                "organisation_name": org.name,
                "invoice_number": invoice.number,
                "amount": f"{payment.currency} {payment.amount:,.2f}",
                "payment_reference": payment.provider_reference or payment.reference,
                "billing_url": f"{settings.FRONTEND_URL}/hr/settings/billing",
            },
            dedupe_key=f"payment_received:{payment.pk}:{m.user_id}",
            organisation=org,
        )


def handle_result(fields: list[tuple[str, str]]) -> Payment | None:
    """Result-URL callback. Returns None (and records it) when the message is not genuine."""
    data = {k.lower(): v for k, v in fields}
    payment = (
        Payment.objects.unscoped().filter(reference=data.get("reference", "")[:64]).first()
        if data.get("reference")
        else None
    )
    if payment is None:
        audit.record(
            actor=None,
            actor_type="system",
            action="billing.paynow_unknown_reference",
            target=("payment", data.get("reference", "")[:64] or "-"),
        )
        return None
    conf = paynow.integration(payment.currency)
    if not paynow.verify(fields, conf.key):
        audit.record(
            actor=None,
            actor_type="system",
            action="billing.paynow_bad_hash",
            target=payment,
            organisation=payment.organisation_id,
        )
        return None
    # EC-BIL-01: never trust the callback alone - confirm with Paynow's poll URL
    url = payment.poll_url or data.get("pollurl", "")
    confirmed = paynow.poll(payment.currency, url)
    return apply_status(payment.pk, confirmed, source="result")


def poll_due() -> dict[str, int]:
    moment = now()
    out = {"polled": 0, "manual": 0}
    due = Payment.objects.unscoped().filter(
        provider=PaymentProvider.PAYNOW, status__in=PENDING, next_poll_at__lte=moment
    )
    for payment in due:
        if moment - payment.created_at > POLL_WINDOW:
            Payment.objects.unscoped().filter(pk=payment.pk, status__in=PENDING).update(
                status=PaymentStatus.PENDING_MANUAL_CHECK, next_poll_at=None
            )
            out["manual"] += 1
            continue
        attempts = payment.poll_attempts + 1
        delay = POLL_DELAYS[min(attempts, len(POLL_DELAYS) - 1)]
        Payment.objects.unscoped().filter(pk=payment.pk).update(
            poll_attempts=attempts, next_poll_at=moment + timedelta(seconds=delay)
        )
        try:
            reply = paynow.poll(payment.currency, payment.poll_url)
        except DomainError:
            continue  # unreachable or unverifiable: try again later
        apply_status(payment.pk, reply, source="poll")
        out["polled"] += 1
    return out


def record_manual_payment(actor: Any, invoice_id: Any, *, amount: Any, reference: str) -> Payment:
    invoice = Invoice.objects.unscoped().filter(pk=invoice_id).first()
    if invoice is None:
        raise NotFoundError()
    if invoice.status != InvoiceStatus.OPEN:
        raise DomainError("invoice_not_open", "This invoice is not open for payment.", 409)
    try:
        value = Decimal(str(amount)).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise DomainError("validation_error", "Invalid amount.") from exc
    if value != invoice.amount:
        raise DomainError(
            "validation_error",
            f"The amount must equal the invoice total ({invoice.currency} {invoice.amount}).",
            details={"amount": ["Must equal the invoice total."]},
        )
    with transaction.atomic():
        payment = Payment.objects.create(
            organisation_id=invoice.organisation_id,
            invoice=invoice,
            provider=PaymentProvider.MANUAL,
            method=PaymentMethod.BANK,
            reference=_reference(invoice),
            provider_reference=reference.strip()[:100],
            amount=value,
            currency=invoice.currency,
            status=PaymentStatus.CREATED,
            initiated_by=actor,
        )
        audit.record(
            actor=actor,
            action="billing.manual_payment_recorded",
            target=payment,
            organisation=invoice.organisation_id,
            after={"amount": str(value), "bank_reference": reference.strip()[:100]},
        )
    return apply_status(
        payment.pk,
        {"status": "Paid", "amount": str(value), "paynowreference": reference.strip()[:100]},
        source="manual",
    )
