"""P14-T05: invoicing - monthly invoices with a price snapshot (EC-BIL-05), USD/ZWG, tax fields,
sequential numbers, PDF with seller details, admin email, free/custom plans not invoiced."""

from __future__ import annotations

import io
import unicodedata
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.billing import entitlements, invoicing
from apps.billing.models import Invoice, Plan, Subscription, SubscriptionStatus
from apps.core.time import now
from apps.notifications.models import Notification
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


def staff(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


def paid(org: Any, code: str = "starter", currency: str = "USD", ended: bool = True) -> Any:
    sub = entitlements.subscription_for(org.pk)
    start = now() - timedelta(days=31)
    Subscription.objects.for_org(org).filter(pk=sub.pk).update(
        plan=Plan.objects.get(code=code),
        status=SubscriptionStatus.ACTIVE,
        currency=currency,
        current_period_start=start,
        current_period_end=now() - timedelta(minutes=1) if ended else now() + timedelta(days=5),
    )
    return Subscription.objects.for_org(org).select_related("plan", "organisation").get()


def pdf_text(data: bytes) -> str:
    import pymupdf

    doc = pymupdf.open(stream=io.BytesIO(data), filetype="pdf")
    return unicodedata.normalize("NFKC", "".join(page.get_text() for page in doc))


def test_monthly_run_invoices_and_advances_the_period(s3: Any, settings: Any) -> None:
    settings.BILLING_TAX_RATE = "0.15"
    team = make_org_with_team()
    sub = paid(team.org)
    old_end = sub.current_period_end
    assert invoicing.run_monthly() == 1
    assert invoicing.run_monthly() == 0  # the period moved on
    invoice = Invoice.objects.for_org(team.org).get()
    assert invoice.number.startswith(f"MHRS-{now().year}-") and invoice.status == "open"
    assert invoice.subtotal == Decimal("49.00") and invoice.tax_amount == Decimal("7.35")
    assert invoice.amount == Decimal("56.35") and invoice.currency == "USD"
    assert invoice.snapshot["unit_price"] == "49.00" and invoice.snapshot["tax_rate"] == "0.15"
    sub.refresh_from_db()
    assert sub.current_period_start == old_end and sub.current_period_end > now()
    assert Notification.objects.filter(key="invoice_issued", recipient_user=team.admin).exists()


def test_price_snapshot_survives_price_changes(s3: Any) -> None:
    team = make_org_with_team()
    paid(team.org)
    invoicing.run_monthly()
    invoice = Invoice.objects.for_org(team.org).get()
    Plan.objects.filter(code="starter").update(price_usd=Decimal("99.00"))
    invoice.refresh_from_db()
    assert invoice.amount == Decimal("49.00") and invoice.snapshot["unit_price"] == "49.00"
    text = pdf_text(invoicing.render_pdf(invoice))
    assert "USD 49.00" in text and "USD 99.00" not in text


def test_zwg_and_unpriced_plans(s3: Any) -> None:
    team = make_org_with_team()
    sub = paid(team.org, currency="ZWG")  # no ZWG price set: invoiced manually
    assert invoicing.issue_invoice(sub, period_start=now(), period_end=now()) is None
    Plan.objects.filter(code="starter").update(price_zwg=Decimal("1300.00"))
    sub.refresh_from_db()
    invoice = invoicing.issue_invoice(sub, period_start=now(), period_end=now() + timedelta(30))
    assert invoice is not None and invoice.currency == "ZWG"
    assert invoice.amount == Decimal("1300.00")
    other = make_org_with_team()
    enterprise = paid(other.org, code="enterprise")
    assert invoicing.issue_invoice(enterprise, period_start=now(), period_end=now()) is None
    trial = entitlements.subscription_for(make_org_with_team().org.pk)
    assert invoicing.issue_invoice(trial, period_start=now(), period_end=now()) is None


def test_numbers_are_sequential(s3: Any) -> None:
    team = make_org_with_team()
    sub = paid(team.org)
    a = invoicing.issue_invoice(sub, period_start=now(), period_end=now() + timedelta(30))
    b = invoicing.issue_invoice(sub, period_start=now(), period_end=now() + timedelta(30))
    assert a is not None and b is not None
    assert int(b.number.rsplit("-", 1)[1]) == int(a.number.rsplit("-", 1)[1]) + 1


def test_pdf_and_api(s3: Any) -> None:
    team = make_org_with_team()
    paid(team.org)
    invoicing.run_monthly()
    invoice = Invoice.objects.for_org(team.org).get()
    admin = staff(team.admin, team.org)
    listing = admin.get("/api/v1/hr/billing/invoices/").json()
    assert listing[0]["number"] == invoice.number and listing[0]["lines"][0]["quantity"] == 1
    pdf = admin.get(f"/api/v1/hr/billing/invoices/{invoice.pk}/pdf/")
    assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf"
    text = pdf_text(pdf.content)
    assert "MudhoTech Solutions (Pvt) Ltd" in text and invoice.number in text
    assert staff(team.hr_manager, team.org).get("/api/v1/hr/billing/invoices/").status_code == 403
    other = make_org_with_team()
    foreign = staff(other.admin, other.org)
    assert foreign.get(f"/api/v1/hr/billing/invoices/{invoice.pk}/pdf/").status_code == 404
