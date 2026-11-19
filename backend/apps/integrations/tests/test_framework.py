"""P15-T01: integrations framework - per-person vs organisation connections, encrypted write-only
credentials, health recording, failure isolation, rotation, audit, tenant isolation."""

from __future__ import annotations

from typing import Any

import pytest
from django.db import connection as db
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.integrations import services
from apps.integrations.adapters.base import IntegrationError
from apps.integrations.models import ConnectionStatus, IntegrationConnection
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


def staff(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


def connect(client: APIClient, provider: str, **extra: Any) -> Any:
    body = {"provider": provider, "credentials": {"refresh_token": "1//0gSecretRefreshToken"}}
    body.update(extra)
    return client.post("/api/v1/hr/integrations/", body, format="json")


def test_personal_calendar_and_admin_only_org_providers() -> None:
    team = make_org_with_team()
    panelist = staff(team.panelist, team.org)
    resp = connect(panelist, "google_calendar")
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["personal"] is True and body["credentials_hint"] == "…oken"
    assert "credentials" not in body and "refresh_token" not in str(body)
    assert connect(panelist, "google_calendar").status_code == 409  # one per person
    hr = staff(team.hr_manager, team.org)
    sms = hr.post(
        "/api/v1/hr/integrations/",
        {"provider": "sms", "credentials": {"api_key": "sk_live_12345678"}},
        format="json",
    )
    assert sms.status_code == 403
    admin = staff(team.admin, team.org)
    ok = admin.post(
        "/api/v1/hr/integrations/",
        {
            "provider": "sms",
            "credentials": {"api_key": "sk_live_12345678"},
            "config": {"sender_id": "ACME"},
        },
        format="json",
    )
    assert ok.status_code == 201
    missing = admin.post(
        "/api/v1/hr/integrations/", {"provider": "whatsapp", "credentials": {}}, format="json"
    )
    assert missing.status_code == 400
    # providers listed: staff only see personal ones; admins see all
    assert {p["key"] for p in hr.get("/api/v1/hr/integrations/").json()["providers"]} == {
        "google_calendar",
        "microsoft_calendar",
    }
    # another person's calendar is not visible to colleagues
    assert all(not c["personal"] for c in hr.get("/api/v1/hr/integrations/").json()["connections"])
    assert AuditEvent.objects.filter(action="integrations.connected").count() == 2


def test_credentials_encrypted_at_rest() -> None:
    team = make_org_with_team()
    connect(staff(team.panelist, team.org), "google_calendar")
    conn = IntegrationConnection.objects.for_org(team.org).get()
    with db.cursor() as cur:
        cur.execute(
            "SELECT credentials FROM integrations_integrationconnection WHERE id = %s", [conn.pk]
        )
        raw = cur.fetchone()[0]
    assert "SecretRefreshToken" not in raw
    assert "SecretRefreshToken" in conn.credentials  # decrypted by the field


def test_health_and_failure_isolation() -> None:
    team = make_org_with_team()
    conn = IntegrationConnection.objects.get(
        pk=connect(staff(team.panelist, team.org), "google_calendar").json()["id"]
    )

    def boom(adapter: Any) -> Any:
        raise IntegrationError("google_calendar: HTTP 500")

    for _ in range(services.FAILURES_BEFORE_ERROR):
        assert services.call(conn, boom) is None  # never raises into the caller
    conn.refresh_from_db()
    assert conn.status == ConnectionStatus.ERROR and conn.last_error.endswith("HTTP 500")
    assert AuditEvent.objects.filter(action="integrations.call_failed").count() == 3
    assert services.call(conn, lambda adapter: "ok") == "ok"
    conn.refresh_from_db()
    assert conn.status == ConnectionStatus.ACTIVE and conn.consecutive_failures == 0
    assert conn.last_success_at is not None


def test_rotate_test_and_disconnect() -> None:
    team = make_org_with_team()
    me = staff(team.panelist, team.org)
    conn_id = connect(me, "microsoft_calendar").json()["id"]
    rotated = me.post(
        f"/api/v1/hr/integrations/{conn_id}/rotate/",
        {"credentials": {"refresh_token": "M.R3_newRefreshTokenValue"}},
        format="json",
    )
    assert rotated.status_code == 200 and rotated.json()["credentials_hint"] == "…alue"
    tested = me.post(f"/api/v1/hr/integrations/{conn_id}/test/")
    assert tested.status_code == 200 and tested.json()["last_success_at"]  # sandbox ping
    other = make_org_with_team()
    assert (
        staff(other.admin, other.org).delete(f"/api/v1/hr/integrations/{conn_id}/").status_code
        == 404
    )
    colleague = staff(team.recruiter, team.org)
    assert colleague.delete(f"/api/v1/hr/integrations/{conn_id}/").status_code == 404
    assert me.delete(f"/api/v1/hr/integrations/{conn_id}/").status_code == 204
    assert AuditEvent.objects.filter(action="integrations.credentials_rotated").exists()
    assert AuditEvent.objects.filter(action="integrations.disconnected").exists()
