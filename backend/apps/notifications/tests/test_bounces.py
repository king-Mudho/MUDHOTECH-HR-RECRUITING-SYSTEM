"""SES bounce/complaint webhook (P05-T04, EC-NOT-01)."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from django.core import mail
from django.db import transaction
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditEvent
from apps.notifications import bounces, delivery
from apps.notifications.models import Channel, EmailSuppression, Notification, NotificationStatus

pytestmark = pytest.mark.django_db

TOPIC = "arn:aws:sns:af-south-1:123456789012:mhrs-ses-feedback"
CERT_URL = "https://sns.af-south-1.amazonaws.com/SimpleNotificationService-test.pem"
URL = "/api/v1/webhooks/ses/"

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sns.amazonaws.com")])
CERT_PEM = (
    x509.CertificateBuilder()
    .subject_name(_name)
    .issuer_name(_name)
    .public_key(KEY.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.now(UTC) - timedelta(days=1))
    .not_valid_after(datetime.now(UTC) + timedelta(days=1))
    .sign(KEY, hashes.SHA256())
    .public_bytes(serialization.Encoding.PEM)
)


def sns(feedback: dict[str, Any] | None = None, *, key: Any = KEY, **over: Any) -> bytes:
    message: dict[str, Any] = {
        "Type": "Notification",
        "MessageId": "m-1",
        "TopicArn": TOPIC,
        "Message": json.dumps(feedback or {}),
        "Timestamp": "2026-11-10T10:00:00.000Z",
        "SignatureVersion": "2",
        "SigningCertURL": CERT_URL,
        **over,
    }
    signature = key.sign(bounces.canonical_string(message), padding.PKCS1v15(), hashes.SHA256())
    message["Signature"] = base64.b64encode(signature).decode()
    return json.dumps(message).encode()


def bounce(email: str, bounce_type: str = "Permanent", message_id: str = "") -> dict[str, Any]:
    return {
        "notificationType": "Bounce",
        "bounce": {
            "bounceType": bounce_type,
            "bounceSubType": "General",
            "bouncedRecipients": [{"emailAddress": email, "diagnosticCode": "550 no such user"}],
        },
        "mail": {"commonHeaders": {"messageId": message_id}},
    }


@pytest.fixture(autouse=True)
def sns_setup(settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    settings.SES_SNS_TOPIC_ARNS = [TOPIC]
    monkeypatch.setattr(bounces, "fetch_certificate", lambda url: CERT_PEM)


def post(body: bytes) -> Any:
    return APIClient().post(URL, data=body, content_type="text/plain; charset=UTF-8")


def test_hard_bounce_suppresses_address_marks_notification_and_flags_user() -> None:
    user = UserFactory(email="Bouncy@Example.test")
    with transaction.atomic():
        rows = delivery.notify(
            user,
            "application_received",
            {
                "organisation_name": "Acme",
                "job_title": "Dev",
                "reference": "R1",
                "application_url": "https://x.test/a",
            },
            dedupe_key="b1",
        )
    n = next(r for r in rows if r.channel == Channel.EMAIL)
    assert delivery.deliver(n.pk) == NotificationStatus.SENT
    res = post(sns(bounce("bouncy@example.test", message_id=delivery.message_id(n))))
    assert res.status_code == 200 and res.json() == {"result": "suppressed:1"}
    row = EmailSuppression.objects.get(email="bouncy@example.test")
    assert row.reason == "bounce" and "550" in row.detail
    n.refresh_from_db()
    assert n.status == NotificationStatus.FAILED and n.last_error == "bounced"  # staff can see it
    event = AuditEvent.objects.get(action="email.suppressed")
    assert "bouncy" not in json.dumps([event.target_id, event.after])  # no address in the trail
    # the same message again changes nothing; later emails are suppressed, the banner flag is on
    assert post(sns(bounce("bouncy@example.test"))).json() == {"result": "suppressed:0"}
    with transaction.atomic():
        again = delivery.notify(
            user, "not_selected", {"organisation_name": "Acme", "job_title": "Dev"}, dedupe_key="b2"
        )
    later = next(r for r in again if r.channel == Channel.EMAIL)
    assert delivery.deliver(later.pk) == NotificationStatus.SUPPRESSED and len(mail.outbox) == 1
    client = APIClient()
    client.force_login(user)
    assert client.get("/api/v1/me/").json()["email_delivery_problem"] is True
    assert Notification.objects.filter(recipient_user=user, channel="inapp").count() == 2


def test_complaint_suppresses_and_soft_bounce_does_not() -> None:
    complaint = {
        "notificationType": "Complaint",
        "complaint": {
            "complainedRecipients": [{"emailAddress": "c@example.test"}],
            "complaintFeedbackType": "abuse",
        },
    }
    assert post(sns(complaint)).json() == {"result": "suppressed:1"}
    assert EmailSuppression.objects.get(email="c@example.test").reason == "complaint"
    assert post(sns(bounce("soft@example.test", "Transient"))).json() == {"result": "suppressed:0"}
    assert not EmailSuppression.objects.filter(email="soft@example.test").exists()
    other = APIClient()
    other.force_login(UserFactory())
    assert other.get("/api/v1/me/").json()["email_delivery_problem"] is False


@pytest.mark.parametrize(
    "case",
    ["bad_signature", "foreign_topic", "cert_not_amazon", "tampered", "garbage", "no_allowlist"],
)
def test_unverifiable_messages_are_refused(case: str, settings: Any) -> None:
    body = sns(bounce("victim@example.test"))
    if case == "bad_signature":
        body = sns(bounce("victim@example.test"), key=rsa.generate_private_key(65537, 2048))
    elif case == "foreign_topic":
        body = sns(bounce("victim@example.test"), TopicArn="arn:aws:sns:us-east-1:1:evil")
    elif case == "cert_not_amazon":
        body = sns(bounce("victim@example.test"), SigningCertURL="https://evil.example/cert.pem")
    elif case == "tampered":
        message = json.loads(body)
        message["Message"] = json.dumps(bounce("someone-else@example.test"))
        body = json.dumps(message).encode()
    elif case == "garbage":
        body = b"not json"
    elif case == "no_allowlist":
        settings.SES_SNS_TOPIC_ARNS = []
    res = post(body)
    assert res.status_code == 403 and res.json()["error"]["code"] == "invalid_signature"
    assert not EmailSuppression.objects.exists()


def test_subscription_confirmation_only_calls_amazon(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []
    monkeypatch.setattr(bounces, "confirm_subscription", lambda m: called.append(m["SubscribeURL"]))
    ok = sns(
        Type="SubscriptionConfirmation",
        Token="t",
        SubscribeURL="https://sns.af-south-1.amazonaws.com/?Action=ConfirmSubscription",
    )
    assert post(ok).json() == {"result": "subscribed"} and len(called) == 1
    monkeypatch.undo()
    with pytest.raises(bounces.InvalidSnsMessageError):
        bounces.confirm_subscription({"SubscribeURL": "https://evil.example/confirm"})
    assert not bounces._is_sns_url("http://sns.af-south-1.amazonaws.com/x")
    assert not bounces._is_sns_url("https://sns.af-south-1.amazonaws.com.evil.example/x")
