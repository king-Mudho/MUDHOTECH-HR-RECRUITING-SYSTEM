"""Role x endpoint expectations, derived from the central RBAC matrix (apps.organisations.rbac).

``expected_status(endpoint, role)`` = the endpoint's success code when the role may perform the
endpoint's RBAC action, else 403. Keeping this derived (not hand-written) means the tests fail when
a view's declared action and the matrix disagree, and changing the matrix updates the expectations.
"""

from __future__ import annotations

from apps.organisations import rbac
from apps.organisations.models import Role
from tests.tenancy.registry import REGISTRY, Endpoint

ROLES: list[str] = list(Role.values)


def expected_status(endpoint: Endpoint, role: str) -> int:
    return endpoint.success if rbac.can(role, endpoint.action) else 403


CASES: list[tuple[Endpoint, str]] = [(ep, role) for ep in REGISTRY for role in ROLES]
