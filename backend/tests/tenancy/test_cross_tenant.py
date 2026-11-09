"""Cross-tenant isolation over every registered staff endpoint (AC of FR-M02, objective O6)."""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent

from .registry import REGISTRY, Endpoint, build_ctx

pytestmark = pytest.mark.django_db


def call(client: APIClient, ep: Endpoint, ctx: Any, header_ctx: Any = None) -> Any:
    headers = ep.headers(header_ctx or ctx)
    return getattr(client, ep.method)(ep.path(ctx), ep.data(ctx), format="json", **headers)


@pytest.mark.parametrize("ep", REGISTRY, ids=str)
def test_member_of_other_org_gets_404(ep: Endpoint) -> None:
    victim = build_ctx(ep)
    attacker = build_ctx(ep)
    client = APIClient()
    client.force_login(attacker.team.admin)  # most privileged role in their own org
    resp = call(client, ep, victim, header_ctx=attacker if ep.targets_object else victim)
    assert resp.status_code == 404, (str(ep), resp.status_code, resp.content[:200])
    assert resp.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("ep", [e for e in REGISTRY if e.is_list], ids=str)
def test_lists_never_include_other_org_rows(ep: Endpoint) -> None:
    victim = build_ctx(ep)
    attacker = build_ctx(ep)
    client = APIClient()
    client.force_login(attacker.team.admin)
    rows = call(client, ep, attacker).json()["results"]
    victim_ids = {str(o.pk) for o in victim.objects.values() if hasattr(o, "pk")}
    assert not victim_ids & {str(r["id"]) for r in rows}


def test_x_org_id_of_foreign_org_is_404_and_audited() -> None:
    """EC-ORG-06 end to end through the API."""
    victim, attacker = build_ctx(), build_ctx()
    client = APIClient()
    client.force_login(attacker.team.recruiter)
    resp = client.get("/api/v1/me/", HTTP_X_ORG_ID=victim.org_id)
    assert resp.status_code == 404
    assert AuditEvent.objects.filter(
        action="tenant_violation_attempt", actor=attacker.team.recruiter
    ).exists()


def test_unauthenticated_requests_are_rejected() -> None:
    ctx = build_ctx()
    client = APIClient()
    for ep in REGISTRY:
        resp = call(client, ep, ctx)
        assert resp.status_code in (401, 403), str(ep)
