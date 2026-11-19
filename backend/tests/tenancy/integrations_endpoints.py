"""Integrations, webhooks and API keys (P15) for the cross-tenant suite and the role matrix."""

from __future__ import annotations

from typing import Any

from tests.tenancy.registry import Ctx, Endpoint


def webhook_setup(ctx: Ctx) -> None:
    import uuid

    from apps.core.time import now
    from apps.integrations.models import WebhookDelivery, WebhookEndpoint

    endpoint = WebhookEndpoint.objects.create(
        organisation=ctx.team.org,
        url="https://hooks.example.test/x",
        secret="whsec_test",
        events=["job.published"],
    )
    ctx.objects["webhook"] = endpoint
    ctx.objects["delivery"] = WebhookDelivery.objects.create(
        organisation=ctx.team.org,
        endpoint=endpoint,
        event_id=uuid.uuid4(),
        event_type="job.published",
        payload={"id": "x"},
        next_attempt_at=now(),
    )


def key_setup(ctx: Ctx) -> None:
    from apps.integrations.models import ApiKey

    ctx.objects["api_key"] = ApiKey.objects.create(
        organisation=ctx.team.org, name="k", prefix=ctx.team.org.pk.hex[:12], key_hash="x" * 64
    )


def ep(name: str, method: str, path: Any, action: str, **kw: Any) -> Endpoint:
    return Endpoint(name, method, path, action, org_header=True, **kw)


INTEGRATION_ENDPOINTS: list[Endpoint] = [
    ep(
        "hr-integrations",
        "get",
        lambda c: "/api/v1/hr/integrations/",
        "org.view",
        targets_object=False,
    ),
    ep(
        "hr-webhooks",
        "get",
        lambda c: "/api/v1/hr/webhooks/",
        "integrations.manage",
        targets_object=False,
        setup=webhook_setup,
    ),
    ep(
        "hr-webhooks-create",
        "post",
        lambda c: "/api/v1/hr/webhooks/",
        "integrations.manage",
        success=201,
        targets_object=False,
        data=lambda c: {"url": "https://hooks.example.test/y", "events": ["job.published"]},
    ),
    ep(
        "hr-webhook-update",
        "patch",
        lambda c: f"/api/v1/hr/webhooks/{c.objects['webhook'].pk}/",
        "integrations.manage",
        setup=webhook_setup,
        data=lambda c: {"active": False},
    ),
    ep(
        "hr-webhook-replay",
        "post",
        lambda c: f"/api/v1/hr/webhooks/deliveries/{c.objects['delivery'].pk}/replay/",
        "integrations.manage",
        setup=webhook_setup,
    ),
    ep(
        "hr-api-keys",
        "get",
        lambda c: "/api/v1/hr/api-keys/",
        "integrations.manage",
        targets_object=False,
        setup=key_setup,
    ),
    ep(
        "hr-api-keys-create",
        "post",
        lambda c: "/api/v1/hr/api-keys/",
        "integrations.manage",
        success=201,
        targets_object=False,
        data=lambda c: {"name": "Sync", "scopes": ["jobs:read"]},
    ),
    ep(
        "hr-api-key-revoke",
        "delete",
        lambda c: f"/api/v1/hr/api-keys/{c.objects['api_key'].pk}/",
        "integrations.manage",
        setup=key_setup,
    ),
]
