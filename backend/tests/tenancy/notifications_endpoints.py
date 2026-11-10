"""HR notification template endpoints for the cross-tenant suite and role matrix (P05-T01)."""

from __future__ import annotations

from typing import Any

from tests.tenancy.registry import Ctx, Endpoint

BODY = "Hello {{ recipient_name }}, we received your application for {{ job_title }}."


def templates_setup(ctx: Ctx) -> None:
    from apps.notifications import services

    services.save_template(
        ctx.team.org,
        actor=ctx.team.hr_manager,
        key="application_received",
        subject="Received: {{ job_title }}",
        body_md=BODY,
    )
    ctx.objects["template"] = services.effective_template(ctx.team.org, "application_received")


def _base(c: Ctx) -> str:
    return "/api/v1/hr/notification-templates"


def _one(c: Ctx) -> str:
    return f"{_base(c)}/{c.objects['template'].pk}"


def ep(name: str, method: str, path: Any, **kw: Any) -> Endpoint:
    return Endpoint(
        name, method, path, "notifications.manage", org_header=True, setup=templates_setup, **kw
    )


NOTIFICATION_ENDPOINTS: list[Endpoint] = [
    ep("hr-notification-templates", "get", lambda c: f"{_base(c)}/", targets_object=False),
    ep(
        "hr-notification-templates",
        "post",
        lambda c: f"{_base(c)}/",
        success=201,
        targets_object=False,
        data=lambda c: {"key": "not_selected", "subject": "Update", "body_md": BODY},
    ),
    ep("hr-notification-template", "get", lambda c: f"{_one(c)}/"),
    ep(
        "hr-notification-template-preview",
        "post",
        lambda c: f"{_one(c)}/preview/",
        data=lambda c: {"context": {}},
    ),
    ep("hr-notification-template-history", "get", lambda c: f"{_one(c)}/history/"),
    ep(
        "hr-notification-templates-revert",
        "post",
        lambda c: f"{_base(c)}/revert/",
        success=204,
        targets_object=False,
        data=lambda c: {"key": "application_received"},
    ),
]
