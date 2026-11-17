"""Privacy endpoints (P09-T02) for the cross-tenant suite and role matrix."""

from __future__ import annotations

from typing import Any

from tests.tenancy.registry import Ctx, Endpoint


def privacy_setup(ctx: Ctx) -> None:
    from datetime import timedelta

    from apps.accounts.tests.factories import UserFactory
    from apps.core.time import now
    from apps.privacy.models import LegalHold, RightsRequest

    org = ctx.team.org
    ctx.objects["rights_request"] = RightsRequest.objects.create(
        user=UserFactory(),
        organisation=org,
        type="access",
        status="received",
        reference=f"RR-T-{str(org.pk)[:6]}",
        due_at=now() + timedelta(days=30),
    )
    ctx.objects["hold"] = LegalHold.objects.create(
        organisation=org,
        target_type="candidate",
        target_id=org.pk,
        reason="Tribunal case",
        placed_by=ctx.team.admin,
        placed_at=now(),
    )


def support_setup(ctx: Ctx) -> None:
    from datetime import timedelta

    from apps.accounts.models import PlatformRole
    from apps.accounts.tests.factories import UserFactory
    from apps.core.time import now
    from apps.organisations.models import SupportAccessGrant

    ctx.objects["grant"] = SupportAccessGrant.objects.create(
        platform_user=UserFactory(platform_role=PlatformRole.PLATFORM_SUPPORT),
        organisation=ctx.team.org,
        reason="Investigating a stuck shortlist",
        requested_at=now(),
        duration_minutes=60,
        approved_at=now(),
        expires_at=now() + timedelta(hours=1),
    )


def ep(name: str, method: str, path: Any, **kw: Any) -> Endpoint:
    return Endpoint(
        name, method, path, "privacy.manage", org_header=True, setup=privacy_setup, **kw
    )


PRIVACY_ENDPOINTS: list[Endpoint] = [
    ep(
        "hr-privacy-requests", "get", lambda c: "/api/v1/hr/privacy/requests/", targets_object=False
    ),
    ep(
        "hr-privacy-request-action",
        "post",
        lambda c: f"/api/v1/hr/privacy/requests/{c.objects['rights_request'].pk}/action/",
        data=lambda c: {"action": "start"},
    ),
    ep("hr-legal-holds", "get", lambda c: "/api/v1/hr/legal-holds/", targets_object=False),
    ep(
        "hr-legal-holds",
        "post",
        lambda c: "/api/v1/hr/legal-holds/",
        success=201,
        data=lambda c: {
            "target_type": "job",
            "target_id": "8f7c5d2e-1a2b-4c3d-9e8f-0a1b2c3d4e5f",
            "reason": "Pending litigation",
        },
        targets_object=False,
    ),
    ep(
        "hr-legal-hold-release",
        "post",
        lambda c: f"/api/v1/hr/legal-holds/{c.objects['hold'].pk}/release/",
    ),
    Endpoint(
        "hr-support-access",
        "get",
        lambda c: "/api/v1/hr/support-access/",
        "members.manage",
        org_header=True,
        targets_object=False,
        setup=support_setup,
    ),
    Endpoint(
        "hr-support-access-revoke",
        "post",
        lambda c: f"/api/v1/hr/support-access/{c.objects['grant'].pk}/revoke/",
        "members.manage",
        org_header=True,
        setup=support_setup,
    ),
]
