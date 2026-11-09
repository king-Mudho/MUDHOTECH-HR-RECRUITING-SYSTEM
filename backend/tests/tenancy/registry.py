"""Registry of organisation-scoped staff endpoints (docs/09 §2 "Tenancy" + "Permissions matrix").

Every new staff endpoint MUST be registered here (backend/CLAUDE.md rule 1). Two suites consume it:

* ``tests/tenancy/test_cross_tenant.py`` - a member of organisation B gets 404 for every endpoint
  pointed at organisation A (and A's objects never appear in B's lists).
* ``tests/permissions/test_matrix.py`` - every role gets the success status if the endpoint's RBAC
  action allows it (``apps.organisations.rbac``) and 403 otherwise.

Later phases append ``Endpoint`` entries and, if they need extra objects, a ``setup`` function that
adds them to ``ctx.objects``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from apps.organisations.models import Membership, Role
from apps.organisations.tests.factories import (
    DepartmentFactory,
    LocationFactory,
    OrgTeam,
    make_org_with_team,
)


@dataclass
class Ctx:
    team: OrgTeam
    objects: dict[str, Any] = field(default_factory=dict)

    @property
    def org_id(self) -> str:
        return str(self.team.org.pk)


Setup = Callable[[Ctx], None]
PathFn = Callable[[Ctx], str]
DataFn = Callable[[Ctx], dict[str, Any] | None]


@dataclass(frozen=True)
class Endpoint:
    name: str
    method: str
    path: PathFn
    action: str  # RBAC action in apps.organisations.rbac.ORG_ACTIONS
    success: int = 200
    data: DataFn = lambda ctx: None
    setup: Setup | None = None
    is_list: bool = False  # list endpoints: cross-tenant check also asserts exclusion

    def __str__(self) -> str:
        return f"{self.method.upper()} {self.name}"


def base_setup(ctx: Ctx) -> None:
    from apps.organisations import services

    team = ctx.team
    ctx.objects["department"] = DepartmentFactory(organisation=team.org, name="Engineering")
    ctx.objects["location"] = LocationFactory(organisation=team.org, name="Harare HQ")
    ctx.objects["target_membership"] = Membership.objects.for_org(team.org).get(user=team.panelist)
    ctx.objects["invitation"] = services.invite_member(
        org=team.org, actor=team.admin, email="pending@example.test", role=Role.RECRUITER
    ).invitation


def build_ctx(**org_kwargs: Any) -> Ctx:
    ctx = Ctx(team=make_org_with_team(**org_kwargs))
    base_setup(ctx)
    for ep in REGISTRY:
        if ep.setup is not None:
            ep.setup(ctx)
    return ctx


def _org(ctx: Ctx) -> str:
    return f"/api/v1/organisations/{ctx.org_id}"


REGISTRY: list[Endpoint] = [
    # organisation & policies
    Endpoint("organisation", "get", lambda c: f"{_org(c)}/", "org.view"),
    Endpoint(
        "organisation",
        "patch",
        lambda c: f"{_org(c)}/",
        "org.update",
        data=lambda c: {"city": "Kadoma"},
    ),
    Endpoint("policies", "get", lambda c: f"{_org(c)}/policies/", "policy.view"),
    Endpoint(
        "policies",
        "patch",
        lambda c: f"{_org(c)}/policies/",
        "policy.update",
        data=lambda c: {"lock_version": 1, "retention_months": 13},
    ),
    # structure
    Endpoint(
        "departments", "get", lambda c: f"{_org(c)}/departments/", "structure.view", is_list=True
    ),
    Endpoint(
        "departments",
        "post",
        lambda c: f"{_org(c)}/departments/",
        "structure.manage",
        success=201,
        data=lambda c: {"name": "Finance"},
    ),
    Endpoint(
        "department",
        "get",
        lambda c: f"{_org(c)}/departments/{c.objects['department'].pk}/",
        "structure.view",
    ),
    Endpoint(
        "department",
        "patch",
        lambda c: f"{_org(c)}/departments/{c.objects['department'].pk}/",
        "structure.manage",
        data=lambda c: {"name": "Platform Engineering"},
    ),
    Endpoint(
        "department",
        "delete",
        lambda c: f"{_org(c)}/departments/{c.objects['department'].pk}/",
        "structure.manage",
        success=204,
    ),
    Endpoint("locations", "get", lambda c: f"{_org(c)}/locations/", "structure.view", is_list=True),
    Endpoint(
        "locations",
        "post",
        lambda c: f"{_org(c)}/locations/",
        "structure.manage",
        success=201,
        data=lambda c: {"name": "Bulawayo", "city": "Bulawayo"},
    ),
    Endpoint(
        "location",
        "patch",
        lambda c: f"{_org(c)}/locations/{c.objects['location'].pk}/",
        "structure.manage",
        data=lambda c: {"city": "Gweru"},
    ),
    Endpoint(
        "location",
        "delete",
        lambda c: f"{_org(c)}/locations/{c.objects['location'].pk}/",
        "structure.manage",
        success=204,
    ),
    # team
    Endpoint("members", "get", lambda c: f"{_org(c)}/members/", "members.view", is_list=True),
    Endpoint(
        "member",
        "patch",
        lambda c: f"{_org(c)}/members/{c.objects['target_membership'].pk}/",
        "members.manage",
        data=lambda c: {"role": "auditor"},
    ),
    Endpoint(
        "member",
        "delete",
        lambda c: f"{_org(c)}/members/{c.objects['target_membership'].pk}/",
        "members.manage",
    ),
    Endpoint(
        "member-reset-mfa",
        "post",
        lambda c: f"{_org(c)}/members/{c.objects['target_membership'].pk}/reset-mfa/",
        "members.reset_mfa",
        data=lambda c: {"reason": "Lost phone; verified in person"},
    ),
    # invitations
    Endpoint(
        "invitations",
        "get",
        lambda c: f"{_org(c)}/invitations/",
        "invitations.manage",
        is_list=True,
    ),
    Endpoint(
        "invitations",
        "post",
        lambda c: f"{_org(c)}/invitations/",
        "invitations.manage",
        success=201,
        data=lambda c: {"email": "new.person@example.test", "role": "auditor"},
    ),
    Endpoint(
        "invitation-resend",
        "post",
        lambda c: f"{_org(c)}/invitations/{c.objects['invitation'].pk}/resend/",
        "invitations.manage",
    ),
    Endpoint(
        "invitation",
        "delete",
        lambda c: f"{_org(c)}/invitations/{c.objects['invitation'].pk}/",
        "invitations.manage",
    ),
]


def register(endpoint: Endpoint) -> Endpoint:
    REGISTRY.append(endpoint)
    return endpoint
