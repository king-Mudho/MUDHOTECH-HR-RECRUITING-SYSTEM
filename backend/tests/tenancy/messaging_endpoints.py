"""HR clarification and message endpoints for the cross-tenant suite and role matrix (P05-T06)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from tests.tenancy.registry import Ctx, Endpoint


def messaging_setup(ctx: Ctx) -> None:
    from apps.applications.models import Status
    from apps.messaging.models import ClarificationRequest
    from tests.tenancy.applications_endpoints import applications_setup

    applications_setup(ctx)
    app = ctx.objects["application"]
    type(app).objects.unscoped().filter(pk=app.pk).update(status=Status.UNDER_REVIEW)
    # a second, already-waiting application whose request can be cancelled
    from apps.accounts.tests.factories import UserFactory
    from apps.applications.tests.factories import make_application
    from apps.core.time import now

    waiting = make_application(
        ctx.objects["live_job"], UserFactory(), status=Status.NEEDS_INFORMATION
    )
    ctx.objects["waiting"] = waiting
    ctx.objects["clarification"] = ClarificationRequest.objects.create(
        organisation_id=waiting.organisation_id,
        application=waiting,
        questions=[{"id": "q1", "prompt": "Year?", "allow_upload": False}],
        due_at=now() + timedelta(days=2),
        previous_status=Status.UNDER_REVIEW,
    )


def _app(c: Ctx) -> str:
    return f"/api/v1/hr/applications/{c.objects['application'].pk}"


def _due(c: Ctx) -> str:
    from apps.core.time import now

    return (now() + timedelta(days=2)).isoformat()


def ep(name: str, method: str, path: Any, action: str, **kw: Any) -> Endpoint:
    return Endpoint(name, method, path, action, org_header=True, setup=messaging_setup, **kw)


MESSAGING_ENDPOINTS: list[Endpoint] = [
    ep(
        "hr-clarification-templates",
        "get",
        lambda c: "/api/v1/hr/clarification-templates/",
        "applications.view",
        targets_object=False,
    ),
    ep(
        "hr-application-clarifications",
        "get",
        lambda c: f"{_app(c)}/clarifications/",
        "applications.view",
    ),
    ep(
        "hr-application-clarifications",
        "post",
        lambda c: f"{_app(c)}/clarifications/",
        "applications.transition",
        success=201,
        data=lambda c: {"questions": [{"prompt": "When can you start?"}], "due_at": _due(c)},
    ),
    ep(
        "hr-application-clarification-cancel",
        "post",
        lambda c: (
            f"/api/v1/hr/applications/{c.objects['waiting'].pk}"
            f"/clarifications/{c.objects['clarification'].pk}/cancel/"
        ),
        "applications.transition",
    ),
    ep("hr-application-messages", "get", lambda c: f"{_app(c)}/messages/", "applications.view"),
    ep(
        "hr-application-messages",
        "post",
        lambda c: f"{_app(c)}/messages/",
        "applications.view",
        success=201,
        data=lambda c: {"body": "Thank you for applying."},
    ),
]
