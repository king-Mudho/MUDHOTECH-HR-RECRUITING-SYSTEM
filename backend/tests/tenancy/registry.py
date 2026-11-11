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
    # Context-scoped endpoints (``/hr/...``) take the organisation from ``X-Org-Id``. The
    # cross-tenant suite sends the *attacker's own* org id (a legitimate header) with a path to the
    # victim's object, so the object lookup itself must 404.
    org_header: bool = False
    # Collection endpoints (list/create) name no victim object, so the cross-tenant suite sends the
    # victim's org id in the header instead (must 404 + audit as a tenant violation).
    targets_object: bool = True

    def headers(self, ctx: Ctx) -> dict[str, str]:
        return {"HTTP_X_ORG_ID": ctx.org_id} if self.org_header else {}

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
    from apps.taxonomy.models import Skill

    ctx.objects["custom_skill"] = Skill.objects.create(
        organisation=team.org,
        canonical_name="Legacy Payroll System",
        slug="legacy-payroll-system",
        category="business",
        taxonomy_version="org",
    )


def build_ctx(*endpoints: Endpoint, **org_kwargs: Any) -> Ctx:
    """Organisation + team + objects. With ``endpoints``, only their extra setups run (each once);
    without, every registered setup runs."""
    ctx = Ctx(team=make_org_with_team(**org_kwargs))
    base_setup(ctx)
    setups: list[Setup] = []
    for ep in endpoints or tuple(REGISTRY):
        if ep.setup is not None and ep.setup not in setups:
            setups.append(ep.setup)
    for setup in setups:
        setup(ctx)
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
    # taxonomy (organisation custom skills)
    Endpoint(
        "custom-skills",
        "get",
        lambda c: f"{_org(c)}/custom-skills/",
        "structure.view",
        is_list=True,
    ),
    Endpoint(
        "custom-skills",
        "post",
        lambda c: f"{_org(c)}/custom-skills/",
        "taxonomy.manage",
        success=201,
        data=lambda c: {"canonical_name": "In-house ERP", "category": "business"},
    ),
    Endpoint(
        "custom-skill",
        "delete",
        lambda c: f"{_org(c)}/custom-skills/{c.objects['custom_skill'].pk}/",
        "taxonomy.manage",
        success=204,
    ),
]


from tests.tenancy.jobs_endpoints import JOB_ENDPOINTS  # noqa: E402

REGISTRY.extend(JOB_ENDPOINTS)

from tests.tenancy.applications_endpoints import APPLICATION_ENDPOINTS  # noqa: E402

REGISTRY.extend(APPLICATION_ENDPOINTS)

from tests.tenancy.notifications_endpoints import NOTIFICATION_ENDPOINTS  # noqa: E402

REGISTRY.extend(NOTIFICATION_ENDPOINTS)

from tests.tenancy.messaging_endpoints import MESSAGING_ENDPOINTS  # noqa: E402

REGISTRY.extend(MESSAGING_ENDPOINTS)

from tests.tenancy.ats_endpoints import ATS_ENDPOINTS  # noqa: E402

REGISTRY.extend(ATS_ENDPOINTS)


def register(endpoint: Endpoint) -> Endpoint:
    REGISTRY.append(endpoint)
    return endpoint
