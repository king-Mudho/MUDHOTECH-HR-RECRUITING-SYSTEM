"""P15-T05/T06: outbound webhooks (HMAC signature, retries, replay, minimal payload, SSRF guard) and
the public API (scoped keys, rate limit) + job feeds."""

from __future__ import annotations

import json
import time
import uuid
from datetime import timedelta
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Status
from apps.applications.tests.factories import make_application, published_job
from apps.core.models import OutboxEvent
from apps.core.time import now
from apps.integrations import webhooks
from apps.integrations.adapters import base
from apps.integrations.models import DeliveryStatus, WebhookDelivery
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


def staff(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


def event(org: Any, kind: str = "application.status_changed", **payload: Any) -> OutboxEvent:
    return OutboxEvent.objects.create(
        event_type=kind,
        aggregate_type="application",
        aggregate_id="x",
        organisation_id=org.pk,
        payload={
            "application_id": str(uuid.uuid4()),
            "from": "submitted",
            "to": "shortlisted",
            **payload,
        },
        dedupe_key=f"test:{uuid.uuid4()}",
        available_at=now(),
    )


def test_signature_roundtrip_and_tolerance() -> None:
    body = b'{"id":"1"}'
    header = webhooks.sign("whsec_test", body, int(time.time()))
    assert webhooks.verify("whsec_test", body, header)
    assert not webhooks.verify("whsec_other", body, header)
    assert not webhooks.verify("whsec_test", b'{"id":"2"}', header)
    old = webhooks.sign("whsec_test", body, int(time.time()) - 3600)
    assert not webhooks.verify("whsec_test", body, old)  # replay outside the window


def test_endpoint_lifecycle_delivery_retry_and_replay(monkeypatch: Any) -> None:
    team = make_org_with_team()
    admin = staff(team.admin, team.org)
    created = admin.post(
        "/api/v1/hr/webhooks/",
        {"url": "https://hooks.example.test/mhrs", "events": ["application.status_changed"]},
        format="json",
    )
    assert created.status_code == 201
    secret = created.json()["secret"]
    assert secret.startswith("whsec_")
    assert "secret" not in admin.get("/api/v1/hr/webhooks/").json()["endpoints"][0]
    bad = admin.post(
        "/api/v1/hr/webhooks/",
        {"url": "http://insecure.test", "events": ["job.published"]},
        format="json",
    )
    assert bad.status_code == 400
    assert staff(team.hr_manager, team.org).get("/api/v1/hr/webhooks/").status_code == 403

    base.SANDBOX_OUTBOX.clear()
    ev = event(team.org, email="leak@example.test", candidate_name="Leak")
    assert webhooks.enqueue(ev) == 1
    assert webhooks.enqueue(ev) == 0  # exactly once per endpoint and event
    sent = base.SANDBOX_OUTBOX[-1]
    payload = json.loads(sent["body"])
    assert (
        payload["type"] == "application.status_changed" and payload["data"]["to"] == "shortlisted"
    )
    assert "leak" not in sent["body"].decode().lower()  # only ids and statuses
    d = WebhookDelivery.objects.for_org(team.org).get()
    assert d.status == DeliveryStatus.SUCCEEDED and d.attempts == 1

    # a failing receiver: retried with backoff, then failed; replay sends again
    monkeypatch.setattr(webhooks, "_post", lambda url, body, headers: 500)
    d2 = WebhookDelivery.objects.for_org(team.org).get(
        pk=webhooks.attempt(
            WebhookDelivery.objects.create(
                organisation=team.org,
                endpoint=d.endpoint,
                event_id=uuid.uuid4(),
                event_type="application.status_changed",
                payload={"id": "y"},
                next_attempt_at=now(),
            ).pk
        ).pk
    )
    assert d2.status == DeliveryStatus.PENDING and d2.next_attempt_at > now()
    assert d2.last_error == "HTTP 500"
    for _ in range(webhooks.MAX_ATTEMPTS):
        WebhookDelivery.objects.filter(pk=d2.pk).update(next_attempt_at=now() - timedelta(1))
        webhooks.retry_due()
    d2.refresh_from_db()
    assert d2.status == DeliveryStatus.FAILED and d2.attempts == webhooks.MAX_ATTEMPTS
    monkeypatch.setattr(webhooks, "_post", lambda url, body, headers: 204)
    replayed = admin.post(f"/api/v1/hr/webhooks/deliveries/{d2.pk}/replay/")
    assert replayed.status_code == 200 and replayed.json()["status"] == "succeeded"
    other = make_org_with_team()
    assert (
        staff(other.admin, other.org)
        .post(f"/api/v1/hr/webhooks/deliveries/{d2.pk}/replay/")
        .status_code
        == 404
    )


def test_ssrf_guard_blocks_private_addresses(settings: Any) -> None:
    settings.INTEGRATIONS_SANDBOX = False
    with pytest.raises(Exception) as err:
        webhooks._public_host("https://127.0.0.1/hook")
    assert "public address" in str(err.value)


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/hook",
        "https://10.0.0.5/hook",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]/hook",
        "https://localhost/hook",
        "https://api.localhost/hook",
    ],
)
def test_ssrf_guard_refuses_literal_private_hosts_in_sandbox_too(settings: Any, url: str) -> None:
    """Sandbox skips DNS lookups but never accepts an obviously private target (E2E 2026-11-20)."""
    settings.INTEGRATIONS_SANDBOX = True
    with pytest.raises(Exception) as err:
        webhooks._public_host(url)
    assert "public address" in str(err.value)
    webhooks._public_host("https://hooks.example.com/mhrs")  # names are not resolved in sandbox


def test_public_api_scopes_and_feeds() -> None:
    team = make_org_with_team()
    job = published_job(organisation=team.org)
    make_application(job, UserFactory(), status=Status.UNDER_REVIEW)
    admin = staff(team.admin, team.org)
    made = admin.post(
        "/api/v1/hr/api-keys/", {"name": "ATS sync", "scopes": ["jobs:read"]}, format="json"
    )
    assert made.status_code == 201
    token = made.json()["key"]
    assert token.startswith("mhrs_") and "key" not in admin.get("/api/v1/hr/api-keys/").json()[0]
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    jobs = client.get("/api/v1/public-api/jobs/")
    assert jobs.status_code == 200 and [j["id"] for j in jobs.json()] == [str(job.pk)]
    assert client.get("/api/v1/public-api/applications/").status_code == 403  # scope
    both = admin.post(
        "/api/v1/hr/api-keys/",
        {"name": "Reports", "scopes": ["applications:read"]},
        format="json",
    ).json()
    reader = APIClient()
    reader.credentials(HTTP_AUTHORIZATION=f"Bearer {both['key']}")
    rows = reader.get("/api/v1/public-api/applications/").json()
    assert len(rows) == 1 and set(rows[0]) == {
        "id",
        "reference",
        "job_id",
        "status",
        "submitted_at",
        "updated_at",
    }
    admin.delete(f"/api/v1/hr/api-keys/{made.json()['id']}/")
    assert client.get("/api/v1/public-api/jobs/").status_code in (401, 403)
    forged = APIClient()
    forged.credentials(HTTP_AUTHORIZATION="Bearer mhrs_deadbeef_nope")
    assert forged.get("/api/v1/public-api/jobs/").status_code in (401, 403)
    # feeds: public, open vacancies of that organisation only
    from apps.jobs.models import Job

    Job.objects.unscoped().filter(pk=job.pk).update(closes_at=now() + timedelta(days=10))
    xml = APIClient().get(f"/api/v1/feeds/{team.org.slug}/jobs.xml")
    assert xml.status_code == 200 and xml["Content-Type"].startswith("application/xml")
    assert f"<referencenumber>{job.pk}</referencenumber>" in xml.content.decode()
    feed = APIClient().get(f"/api/v1/feeds/{team.org.slug}/jobs.json").json()
    assert [j["id"] for j in feed] == [str(job.pk)]
    assert APIClient().get("/api/v1/feeds/unknown-org/jobs.json").json() == []
