"""P15-T04: SMS/WhatsApp - explicit opt-in, approved templates, STOP handling, receipts, metering,
failures isolated."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import pytest
from django.db import transaction
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.billing.models import UsageCounter
from apps.integrations import messaging, services
from apps.integrations.adapters import base
from apps.integrations.models import IntegrationConnection
from apps.notifications import delivery
from apps.notifications.models import Notification
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


@pytest.fixture
def world() -> dict[str, Any]:
    team = make_org_with_team()
    for provider, creds, config in (
        ("sms", {"api_key": "sk_test_12345678"}, {"sender_id": "ACME"}),
        ("whatsapp", {"access_token": "EAAG_test_token"}, {"phone_number_id": "1234567890"}),
    ):
        IntegrationConnection.objects.create(
            organisation=team.org,
            provider=provider,
            credentials=json.dumps(creds),
            config=config,
        )
    user = UserFactory(phone_e164="+263771234567")
    base.SANDBOX_OUTBOX.clear()
    return {"team": team, "user": user}


def invite(world: dict[str, Any], dedupe: str = "inv-1") -> list[Notification]:
    with transaction.atomic():
        return delivery.notify(
            world["user"],
            "interview_invitation",
            {
                "organisation_name": "Acme",
                "job_title": "Developer",
                "interview_stage": "Technical",
                "interview_when": "Tue 10:00",
                "interview_mode": "Video",
                "interview_where": "Online",
                "interview_url": "https://x.test",
                "reference": "R1",
            },
            dedupe_key=dedupe,
            organisation=world["team"].org,
        )


def mobile(world: dict[str, Any]) -> Any:
    return Notification.objects.filter(
        recipient_user=world["user"], channel__in=["sms", "whatsapp"]
    )


def test_no_messages_without_opt_in(world: dict[str, Any]) -> None:
    invite(world)
    assert not mobile(world).exists()


def test_opt_in_send_receipt_and_metering(world: dict[str, Any]) -> None:
    me = APIClient()
    me.force_login(world["user"])
    resp = me.put(
        "/api/v1/candidate/messaging-preferences/", {"sms": True, "whatsapp": True}, format="json"
    )
    assert resp.status_code == 200 and resp.json() == {"sms": True, "whatsapp": True}
    invite(world)
    rows = {n.channel: n for n in mobile(world)}
    assert set(rows) == {"sms", "whatsapp"}
    for n in rows.values():
        assert messaging.send(n.pk) == "sent"
    sms = [r for r in base.SANDBOX_OUTBOX if r["provider"] == "sms"][-1]
    assert "Acme" in sms["body"]["message"] and "STOP" in sms["body"]["message"]
    wa = [r for r in base.SANDBOX_OUTBOX if r["provider"] == "whatsapp"][-1]
    assert wa["body"]["type"] == "template"
    assert wa["body"]["template"]["name"] == "mhrs_interview_invitation"
    sent = Notification.objects.get(pk=rows["sms"].pk)
    assert messaging.record_receipt(sent.provider_message_id, "delivered") == 1
    assert Notification.objects.get(pk=sent.pk).status == "delivered"
    counters = dict(UsageCounter.objects.for_org(world["team"].org).values_list("metric", "value"))
    assert counters["sms_messages"] == 1 and counters["whatsapp_messages"] == 1


def test_stop_opts_out_and_consent_is_rechecked(world: dict[str, Any], settings: Any) -> None:
    settings.SMS_WEBHOOK_SECRET = "s3cret"
    messaging.set_preferences(world["user"], sms=True, whatsapp=True)
    invite(world)
    stop = APIClient().post(
        "/api/v1/integrations/sms/inbound/",
        {"from": "0771234567", "text": " stop "},
        format="json",
        HTTP_X_MHRS_WEBHOOK_SECRET="s3cret",
    )
    assert stop.status_code == 200
    assert messaging.has_consent(world["user"], "sms") is False
    sms = mobile(world).get(channel="sms")
    assert messaging.send(sms.pk) == "suppressed"  # withdrawn before sending
    forged = APIClient().post(
        "/api/v1/integrations/sms/inbound/", {"from": "0771234567", "text": "STOP"}, format="json"
    )
    assert forged.status_code == 403
    # WhatsApp STOP through Meta's signed webhook
    settings.WHATSAPP_APP_SECRET = "app-secret"
    body = json.dumps(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [{"from": "263771234567", "text": {"body": "STOP"}}]
                            }
                        }
                    ]
                }
            ]
        }
    ).encode()
    sig = "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
    ok = APIClient().post(
        "/api/v1/integrations/whatsapp/webhook/",
        body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=sig,
    )
    assert ok.status_code == 200 and messaging.has_consent(world["user"], "whatsapp") is False
    unsigned = APIClient().post(
        "/api/v1/integrations/whatsapp/webhook/", body, content_type="application/json"
    )
    assert unsigned.status_code == 403


def test_opt_in_needs_a_phone_and_failures_are_isolated(
    world: dict[str, Any], monkeypatch: Any
) -> None:
    nophone = UserFactory(phone_e164="")
    me = APIClient()
    me.force_login(nophone)
    resp = me.put(
        "/api/v1/candidate/messaging-preferences/", {"sms": True, "whatsapp": False}, format="json"
    )
    assert resp.status_code == 400
    messaging.set_preferences(world["user"], sms=True, whatsapp=False)
    invite(world, "inv-2")
    sms = mobile(world).get(channel="sms")

    def broken(self: Any, to: str, text: str, reference: str) -> Any:
        raise base.IntegrationError("sms: HTTP 502")

    from apps.integrations.adapters.messaging import SmsAggregatorAdapter

    monkeypatch.setattr(SmsAggregatorAdapter, "send", broken)
    assert messaging.send(sms.pk) == "failed"
    email = Notification.objects.get(
        recipient_user=world["user"], channel="email", key="interview_invitation"
    )
    assert email.status in ("queued", "sent")  # the email copy is unaffected
    conn = services.org_connection(world["team"].org.pk, "sms")
    assert conn is not None and conn.last_error.endswith("HTTP 502")
