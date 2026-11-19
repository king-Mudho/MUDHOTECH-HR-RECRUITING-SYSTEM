"""P14-T06/T09: Paynow payments against a fake Paynow - signed messages, valid/invalid hash,
duplicate callbacks, pending -> paid, failed/cancelled, spoofed callbacks (EC-BIL-01), polling
backoff to manual check (EC-BIL-02), amount mismatch, manual bank payments, reactivation."""

from __future__ import annotations

import urllib.parse
from datetime import timedelta
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import PlatformRole
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditEvent
from apps.billing import entitlements, invoicing, payments, paynow
from apps.billing.models import (
    Invoice,
    Payment,
    PaymentStatus,
    Plan,
    Subscription,
    SubscriptionStatus,
)
from apps.core.time import now
from apps.notifications.models import Notification
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db

KEY = "test-integration-key"
POLL = "https://www.paynow.co.zw/interface/poll/?guid="


class FakePaynow:
    """Answers like Paynow: signed form-encoded replies; ``state`` drives what polls return."""

    def __init__(self) -> None:
        self.state: dict[str, dict[str, str]] = {}  # guid -> {status, amount, reference}
        self.requests: list[tuple[str, dict[str, str]]] = []

    def signed(self, fields: list[tuple[str, str]]) -> str:
        return urllib.parse.urlencode([*fields, ("hash", paynow.make_hash(fields, KEY))])

    def __call__(self, url: str, data: dict[str, str]) -> str:
        self.requests.append((url, data))
        if url.startswith(POLL):
            guid = url[len(POLL) :]
            s = self.state[guid]
            return self.signed(
                [
                    ("reference", s["reference"]),
                    ("paynowreference", "PN-778899"),
                    ("amount", s["amount"]),
                    ("status", s["status"]),
                    ("pollurl", url),
                ]
            )
        guid = f"g{len(self.state) + 1}"
        self.state[guid] = {
            "status": "Sent",
            "amount": data["amount"],
            "reference": data["reference"],
        }
        fields = [("status", "Ok")]
        if url.endswith("/remotetransaction"):
            fields.append(("instructions", "Dial *151*2*4# and enter your PIN"))
        else:
            fields.append(("browserurl", f"https://www.paynow.co.zw/Payment/ConfirmPayment/{guid}"))
        fields.append(("pollurl", POLL + guid))
        return self.signed(fields)


@pytest.fixture
def fake(settings: Any) -> Any:
    settings.PAYNOW_INTEGRATIONS = {"USD": {"id": "1201", "key": KEY}, "ZWG": {"id": "", "key": ""}}
    f = FakePaynow()
    paynow.set_transport(f)
    yield f
    paynow.set_transport(None)


@pytest.fixture
def world(s3: Any) -> dict[str, Any]:
    team = make_org_with_team()
    sub = entitlements.subscription_for(team.org.pk)
    Subscription.objects.for_org(team.org).filter(pk=sub.pk).update(
        plan=Plan.objects.get(code="starter"),
        status=SubscriptionStatus.PAST_DUE,
        grace_until=now() + timedelta(days=3),
    )
    sub.refresh_from_db()
    invoice = invoicing.issue_invoice(sub, period_start=now(), period_end=now() + timedelta(30))
    admin = APIClient()
    admin.force_login(team.admin)
    admin.credentials(HTTP_X_ORG_ID=str(team.org.pk))
    return {"team": team, "invoice": invoice, "admin": admin, "sub": sub}


def pay(world: dict[str, Any], **body: Any) -> Any:
    return world["admin"].post(
        f"/api/v1/hr/billing/invoices/{world['invoice'].pk}/pay/", body, format="json"
    )


def callback(fake: FakePaynow, payment: Payment, status: str, key: str = KEY) -> Any:
    fields = [
        ("reference", payment.reference),
        ("paynowreference", "PN-778899"),
        ("amount", f"{payment.amount:.2f}"),
        ("status", status),
        ("pollurl", payment.poll_url),
    ]
    body = urllib.parse.urlencode([*fields, ("hash", paynow.make_hash(fields, key))])
    return APIClient().post(
        "/api/v1/billing/paynow/result/", body, content_type="application/x-www-form-urlencoded"
    )


def guid(payment: Payment) -> str:
    return payment.poll_url[len(POLL) :]


def test_hash_roundtrip() -> None:
    fields = [("id", "1201"), ("reference", "INV-1"), ("amount", "49.00"), ("status", "Message")]
    signed = [*fields, ("hash", paynow.make_hash(fields, KEY))]
    assert paynow.verify(signed, KEY)
    assert not paynow.verify(signed, "wrong-key")
    tampered = [(k, "1.00" if k == "amount" else v) for k, v in signed]
    assert not paynow.verify(tampered, KEY)


def test_web_checkout_then_paid_via_verified_callback(fake: FakePaynow, world: Any) -> None:
    resp = pay(world, method="card")
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["redirect_url"].startswith("https://www.paynow.co.zw/Payment/")
    payment = Payment.objects.get(pk=body["payment"]["id"])
    assert payment.status == PaymentStatus.SENT and payment.amount == world["invoice"].amount
    sent = fake.requests[0][1]
    assert sent["amount"] == f"{world['invoice'].amount:.2f}" and sent["hash"]
    # Paynow reports paid: the callback alone is not trusted - the poll confirms it
    fake.state[guid(payment)]["status"] = "Paid"
    assert callback(fake, payment, "Paid").status_code == 200
    payment.refresh_from_db()
    world["invoice"].refresh_from_db()
    assert payment.status == PaymentStatus.PAID and payment.provider_reference == "PN-778899"
    assert world["invoice"].status == "paid" and world["invoice"].paid_at is not None
    world["sub"].refresh_from_db()
    assert world["sub"].status == SubscriptionStatus.ACTIVE and world["sub"].grace_until is None
    receipts = Notification.objects.filter(key="payment_received")
    assert receipts.filter(recipient_user=world["team"].admin).exists()
    count = receipts.count()
    callback(fake, payment, "Paid")  # duplicate delivery
    assert Notification.objects.filter(key="payment_received").count() == count
    assert Payment.objects.filter(status=PaymentStatus.PAID).count() == 1


def test_spoofed_callbacks_change_nothing(fake: FakePaynow, world: Any) -> None:
    payment = Payment.objects.get(pk=pay(world, method="card").json()["payment"]["id"])
    assert callback(fake, payment, "Paid", key="attacker-key").status_code == 200
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.SENT
    assert AuditEvent.objects.filter(action="billing.paynow_bad_hash").exists()
    # a correctly signed "Paid" (e.g. replayed) is still confirmed against the poll URL first
    callback(fake, payment, "Paid")
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.SENT  # Paynow still says Sent
    unknown = APIClient().post(
        "/api/v1/billing/paynow/result/",
        "reference=NOPE&status=Paid&hash=X",
        content_type="application/x-www-form-urlencoded",
    )
    assert unknown.status_code == 200
    assert AuditEvent.objects.filter(action="billing.paynow_unknown_reference").exists()


def test_mobile_money_polling_backoff_and_manual_check(fake: FakePaynow, world: Any) -> None:
    bad = pay(world, method="ecocash", phone="12345")
    assert bad.status_code == 400
    resp = pay(world, method="ecocash", phone="+263 77 123 4567")
    assert resp.status_code == 201 and "Dial" in resp.json()["instructions"]
    assert fake.requests[-1][1]["phone"] == "0771234567"
    assert fake.requests[-1][1]["method"] == "ecocash"
    payment = Payment.objects.get(pk=resp.json()["payment"]["id"])
    Payment.objects.filter(pk=payment.pk).update(next_poll_at=now() - timedelta(seconds=1))
    assert payments.poll_due() == {"polled": 1, "manual": 0}
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.SENT and payment.poll_attempts == 1
    assert payment.next_poll_at > now()  # backed off
    Payment.objects.filter(pk=payment.pk).update(
        created_at=now() - timedelta(minutes=16), next_poll_at=now() - timedelta(seconds=1)
    )
    assert payments.poll_due() == {"polled": 0, "manual": 1}
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.PENDING_MANUAL_CHECK


def test_pending_to_paid_by_poll_failed_and_cancelled(fake: FakePaynow, world: Any) -> None:
    payment = Payment.objects.get(
        pk=pay(world, method="onemoney", phone="0712345678").json()["payment"]["id"]
    )
    fake.state[guid(payment)]["status"] = "Paid"
    Payment.objects.filter(pk=payment.pk).update(next_poll_at=now() - timedelta(seconds=1))
    payments.poll_due()
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.PAID
    other_team = make_org_with_team()
    sub = entitlements.subscription_for(other_team.org.pk)
    Subscription.objects.for_org(other_team.org).filter(pk=sub.pk).update(
        plan=Plan.objects.get(code="starter"), status="active"
    )
    sub.refresh_from_db()
    for word, expected in (
        ("Failed", PaymentStatus.FAILED),
        ("Cancelled", PaymentStatus.CANCELLED),
    ):
        inv = invoicing.issue_invoice(sub, period_start=now(), period_end=now() + timedelta(30))
        admin = APIClient()
        admin.force_login(other_team.admin)
        admin.credentials(HTTP_X_ORG_ID=str(other_team.org.pk))
        p = Payment.objects.get(
            pk=admin.post(
                f"/api/v1/hr/billing/invoices/{inv.pk}/pay/", {"method": "card"}, format="json"
            ).json()["payment"]["id"]
        )
        fake.state[guid(p)]["status"] = word
        callback(fake, p, word)
        p.refresh_from_db()
        assert p.status == expected
        assert Invoice.objects.for_org(other_team.org).get(pk=inv.pk).status == "open"


def test_amount_mismatch_goes_to_manual_check(fake: FakePaynow, world: Any) -> None:
    payment = Payment.objects.get(pk=pay(world, method="card").json()["payment"]["id"])
    fake.state[guid(payment)].update(status="Paid", amount="1.00")
    callback(fake, payment, "Paid")
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.PENDING_MANUAL_CHECK
    assert Invoice.objects.get(pk=world["invoice"].pk).status == "open"


def test_not_configured_and_closed_invoices(world: Any, settings: Any) -> None:
    settings.PAYNOW_INTEGRATIONS = {"USD": {"id": "", "key": ""}}
    resp = pay(world, method="card")
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "payments_unavailable"
    hr = APIClient()
    hr.force_login(world["team"].hr_manager)
    hr.credentials(HTTP_X_ORG_ID=str(world["team"].org.pk))
    denied = hr.post(f"/api/v1/hr/billing/invoices/{world['invoice'].pk}/pay/", {"method": "card"})
    assert denied.status_code == 403


def test_manual_bank_payment_by_platform_admin(world: Any) -> None:
    url = f"/api/v1/platform/billing/invoices/{world['invoice'].pk}/manual-payment/"
    platform = APIClient()
    platform.force_login(UserFactory(platform_role=PlatformRole.PLATFORM_ADMIN))
    wrong = platform.post(url, {"amount": "1.00", "reference": "BANK-1"}, format="json")
    assert wrong.status_code == 400
    ok = platform.post(
        url, {"amount": str(world["invoice"].amount), "reference": "CABS-445566"}, format="json"
    )
    assert ok.status_code == 201 and ok.json()["status"] == "paid"
    assert Invoice.objects.get(pk=world["invoice"].pk).status == "paid"
    assert world["admin"].post(url, {"amount": "1", "reference": "x"}).status_code == 403
    again = platform.post(url, {"amount": str(world["invoice"].amount), "reference": "X"})
    assert again.status_code == 409
