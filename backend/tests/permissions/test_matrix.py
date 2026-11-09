"""Permission matrix: every role x every registered staff endpoint (docs/09 §2)."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from tests.tenancy.registry import Endpoint, build_ctx

from .matrix import CASES, expected_status

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(("ep", "role"), CASES, ids=lambda v: str(v))
def test_role_endpoint_matrix(ep: Endpoint, role: str) -> None:
    ctx = build_ctx(ep)
    client = APIClient()
    client.force_login(ctx.team.user_for(role))
    resp = getattr(client, ep.method)(ep.path(ctx), ep.data(ctx), format="json", **ep.headers(ctx))
    expected = expected_status(ep, role)
    assert resp.status_code == expected, (str(ep), role, resp.status_code, resp.content[:300])
    if expected == 403:
        assert resp.json()["error"]["code"] == "permission_denied"
