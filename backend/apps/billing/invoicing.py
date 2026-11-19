"""Invoicing (P14-T05, EC-BIL-05).

* ``issue_invoice`` - one invoice for one subscription period in the subscription's currency
  (USD or ZWG). The plan price, tax rate and seller details are **snapshotted** on the invoice so a
  later price or currency change never alters it. Plans without a price in that currency
  (Enterprise, or no ZWG price set) are invoiced manually by the platform team; free plans are
  never invoiced.
* ``render_pdf`` - the invoice PDF (PyMuPDF Story, every value escaped) with MudhoTech Solutions
  (Pvt) Ltd details and the configurable tax/VAT fields; stored in the private exports bucket and
  streamed to organisation admins.
* ``run_monthly`` (daily beat) - paid subscriptions whose period ended get the next period's
  invoice and the period advances; organisation admins are told by email.
"""

from __future__ import annotations

import calendar
import io
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from html import escape
from typing import Any

from django.conf import settings
from django.db import connection, transaction

from apps.audit import services as audit
from apps.core import storage
from apps.core.time import now

from .models import Invoice, InvoiceStatus, Plan, Subscription, SubscriptionStatus

CENT = Decimal("0.01")


def add_months(moment: datetime, months: int = 1) -> datetime:
    month = moment.month - 1 + months
    year = moment.year + month // 12
    month = month % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def seller() -> dict[str, str]:
    return {
        "name": settings.BILLING_SELLER_NAME,
        "address": settings.BILLING_SELLER_ADDRESS,
        "email": settings.BILLING_SELLER_EMAIL,
        "tax_number": settings.BILLING_SELLER_TAX_NUMBER,
    }


def next_number(year: int) -> str:
    """``MHRS-2026-000001``; serialised with a transaction-level advisory lock."""
    with connection.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", [7_140_000 + year])
    prefix = f"MHRS-{year}-"
    last = (
        Invoice.objects.unscoped()  # numbering is platform-wide
        .filter(number__startswith=prefix)
        .order_by("-number")
        .values_list("number", flat=True)
        .first()
    )
    seq = int(last.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{seq:06d}"


def issue_invoice(
    subscription: Subscription,
    *,
    period_start: datetime,
    period_end: datetime,
    plan: Plan | None = None,
    actor: Any = None,
) -> Invoice | None:
    plan = plan or subscription.plan
    unit = plan.price(subscription.currency)
    if unit is None or Decimal(str(unit)) <= 0:
        return None
    unit = Decimal(str(unit)).quantize(CENT)
    rate = Decimal(str(settings.BILLING_TAX_RATE))
    tax = (unit * rate).quantize(CENT, rounding=ROUND_HALF_UP)
    moment = now()
    with transaction.atomic():
        number = next_number(moment.year)
        description = (
            f"{plan.name} plan, {period_start:%d %b %Y} - "
            f"{(period_end - timedelta(days=1)):%d %b %Y}"
        )
        invoice = Invoice.objects.create(
            organisation_id=subscription.organisation_id,
            number=number,
            subscription=subscription,
            currency=subscription.currency,
            subtotal=unit,
            tax_amount=tax,
            amount=unit + tax,
            lines=[
                {
                    "description": description,
                    "quantity": 1,
                    "unit_price": str(unit),
                    "total": str(unit),
                }
            ],
            snapshot={
                "plan": plan.code,
                "plan_name": plan.name,
                "currency": subscription.currency,
                "unit_price": str(unit),
                "tax_rate": str(rate),
                "tax_label": settings.BILLING_TAX_LABEL,
                "seller": seller(),
                "organisation": subscription.organisation.name,
            },
            status=InvoiceStatus.OPEN,
            period_start=period_start.date(),
            period_end=(period_end - timedelta(days=1)).date(),
            issued_at=moment,
            due_at=moment + timedelta(days=settings.BILLING_DUE_DAYS),
        )
        audit.record(
            actor=actor,
            actor_type="human" if actor is not None else "system",
            action="billing.invoice_issued",
            target=invoice,
            organisation=subscription.organisation_id,
            after={"number": number, "amount": str(invoice.amount), "currency": invoice.currency},
        )
        transaction.on_commit(lambda: store_pdf(invoice.pk))
        _notify_admins(invoice)
    return invoice


def _notify_admins(invoice: Invoice) -> None:
    from apps.notifications import delivery as notifications
    from apps.organisations.models import Membership, Role

    org = invoice.organisation
    for m in (
        Membership.objects.for_org(invoice.organisation_id)
        .filter(status=Membership.Status.ACTIVE, role=Role.ORG_ADMIN)
        .select_related("user")
    ):
        notifications.notify(
            m.user,
            "invoice_issued",
            {
                "organisation_name": org.name,
                "invoice_number": invoice.number,
                "amount": f"{invoice.currency} {invoice.amount:,.2f}",
                "due_date": f"{invoice.due_at:%d %B %Y}" if invoice.due_at else "",
                "billing_url": f"{settings.FRONTEND_URL}/hr/settings/billing",
            },
            dedupe_key=f"invoice_issued:{invoice.pk}:{m.user_id}",
            organisation=org,
        )


def money(value: Any, currency: str) -> str:
    return f"{currency} {Decimal(str(value)):,.2f}"


def html(invoice: Invoice) -> str:
    snap = invoice.snapshot or {}
    sell = snap.get("seller") or seller()
    rows = "".join(
        f"<tr><td>{escape(str(line['description']))}</td>"
        f"<td class='n'>{escape(str(line['quantity']))}</td>"
        f"<td class='n'>{escape(money(line['unit_price'], invoice.currency))}</td>"
        f"<td class='n'>{escape(money(line['total'], invoice.currency))}</td></tr>"
        for line in invoice.lines
    )
    tax_label = escape(str(snap.get("tax_label") or "VAT"))
    rate = Decimal(str(snap.get("tax_rate") or "0")) * 100
    seller_lines = "<br/>".join(
        escape(v)
        for v in (
            sell.get("name", ""),
            sell.get("address", ""),
            sell.get("email", ""),
            f"Tax number: {sell['tax_number']}" if sell.get("tax_number") else "",
        )
        if v
    )
    due = f"{invoice.due_at:%d %B %Y}" if invoice.due_at else ""
    issued = f"{invoice.issued_at:%d %B %Y}" if invoice.issued_at else ""
    return (
        f"<p class='seller'>{seller_lines}</p>"
        f"<h1>Invoice {escape(invoice.number)}</h1>"
        f"<p>Billed to: <b>{escape(str(snap.get('organisation') or invoice.organisation.name))}</b>"
        f"<br/>Issued: {escape(issued)}<br/>Due: {escape(due)}"
        f"<br/>Status: {escape(invoice.get_status_display())}</p>"
        "<table><tr><th>Description</th><th class='n'>Qty</th><th class='n'>Unit price</th>"
        f"<th class='n'>Total</th></tr>{rows}"
        f"<tr><td colspan='3' class='n'>Subtotal</td>"
        f"<td class='n'>{escape(money(invoice.subtotal, invoice.currency))}</td></tr>"
        f"<tr><td colspan='3' class='n'>{tax_label} ({rate.normalize():f}%)</td>"
        f"<td class='n'>{escape(money(invoice.tax_amount, invoice.currency))}</td></tr>"
        f"<tr><td colspan='3' class='n'><b>Total due</b></td>"
        f"<td class='n'><b>{escape(money(invoice.amount, invoice.currency))}</b></td></tr></table>"
        "<p>Pay online from Settings &gt; Plan &amp; billing (EcoCash, OneMoney or card through "
        "Paynow), or by bank transfer quoting the invoice number.</p>"
        "<p class='muted'>MUDHOTECH HR RECRUITING SYSTEM</p>"
    )


CSS = (
    "body{font-family:sans-serif;font-size:10pt;line-height:1.4}h1{font-size:16pt}"
    ".seller{font-size:9pt;color:#333}.muted{color:#666;font-size:8pt}"
    "table{border-collapse:collapse;width:100%;margin:8pt 0}"
    "th,td{border:0.5pt solid #bbb;padding:4pt;text-align:left}td.n,th.n{text-align:right}"
)


def render_pdf(invoice: Invoice) -> bytes:
    import pymupdf

    story = pymupdf.Story(html=html(invoice), user_css=CSS)
    out = io.BytesIO()
    writer = pymupdf.DocumentWriter(out)
    page = pymupdf.paper_rect("a4")
    area = pymupdf.Rect(page.x0 + 54, page.y0 + 54, page.x1 - 54, page.y1 - 54)
    more = True
    while more:
        device = writer.begin_page(page)
        more, _ = story.place(area)
        story.draw(device)
        writer.end_page()
    writer.close()
    return out.getvalue()


def pdf_key(invoice: Invoice) -> str:
    return f"invoices/{invoice.organisation_id}/{invoice.number}.pdf"


def store_pdf(invoice_id: Any) -> None:
    invoice = (
        Invoice.objects.unscoped().select_related("organisation").filter(pk=invoice_id).first()
    )
    if invoice is None:
        return
    storage.put_bytes("exports", pdf_key(invoice), render_pdf(invoice), "application/pdf")


def pdf_bytes(invoice: Invoice) -> bytes:
    """The stored PDF, regenerated from the snapshot if it is missing."""
    try:
        return storage.get_bytes("exports", pdf_key(invoice))
    except Exception:
        data = render_pdf(invoice)
        storage.put_bytes("exports", pdf_key(invoice), data, "application/pdf")
        return data


def run_monthly() -> int:
    """Invoice every paid subscription whose period has ended and advance its period."""
    moment = now()
    issued = 0
    due = (
        Subscription.objects.unscoped()  # system sweep across organisations
        .filter(
            status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE],
            current_period_end__lte=moment,
        )
        .select_related("plan", "organisation")
    )
    for sub in due:
        with transaction.atomic():
            locked = Subscription.objects.unscoped().select_for_update().get(pk=sub.pk)
            if locked.current_period_end is None or locked.current_period_end > moment:
                continue
            start = locked.current_period_end
            end = add_months(start)
            locked.current_period_start, locked.current_period_end = start, end
            locked.save(update_fields=["current_period_start", "current_period_end", "updated_at"])
            if issue_invoice(locked, period_start=start, period_end=end) is not None:
                issued += 1
    return issued
