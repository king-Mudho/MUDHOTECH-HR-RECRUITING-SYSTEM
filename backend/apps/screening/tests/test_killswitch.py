"""AI kill-switch (P09-T11): with AI off every application goes to manual review, no AI output."""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import PlatformRole
from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application, Status
from apps.audit.models import AuditEvent
from apps.core import flags
from apps.organisations.models import OrganisationPolicy
from apps.screening import killswitch, services
from apps.screening.models import Evaluation

pytestmark = pytest.mark.django_db


def admin_client(role: str = PlatformRole.PLATFORM_ADMIN) -> APIClient:
    c = APIClient()
    c.force_login(UserFactory(verified=True, platform_role=role))
    return c


def assert_manual(app: Application) -> None:
    app.refresh_from_db()
    assert app.status == Status.UNDER_REVIEW
    assert app.ai_band == "manual_review_requested"
    assert app.score is None and app.coverage is None and app.essentials_met is None
    assert not Evaluation.objects.for_org(app.organisation_id).filter(application=app).exists()


@pytest.fixture(autouse=True)
def _fresh_flags() -> Any:
    flags.invalidate(killswitch.FLAG)
    yield
    flags.invalidate(killswitch.FLAG)


def test_ai_is_on_by_default(read_app: Application) -> None:
    assert killswitch.platform_enabled() and killswitch.ai_allowed(read_app.organisation)
    assert services.evaluate_application(read_app.pk) is not None


def test_platform_switch_routes_every_application_to_manual_review(read_app: Application) -> None:
    killswitch.set_platform(False, actor=None, reason="Incident: model drift")
    assert services.evaluate_application(read_app.pk) is None
    assert_manual(read_app)
    event = AuditEvent.objects.filter(action="screening.ai_disabled").get()
    assert event.after == {"band": "manual_review_requested"}
    # switching back on re-enables screening (HR starts a run when they want it)
    killswitch.set_platform(True, actor=None, reason="Incident resolved")
    app = Application.objects.unscoped().get(pk=read_app.pk)
    assert killswitch.ai_allowed(app.organisation)


def test_organisation_override_and_policy_switch_one_tenant(read_app: Application) -> None:
    org = read_app.organisation
    killswitch.set_for_organisation(org, False, actor=None, reason="Customer asked to pause AI")
    assert not killswitch.ai_allowed(org) and killswitch.platform_enabled()
    killswitch.set_for_organisation(org, None, actor=None, reason="Override removed again")
    assert killswitch.ai_allowed(org)

    OrganisationPolicy.objects.filter(organisation=org).update(ai_enabled=False)
    app = Application.objects.unscoped().select_related("organisation").get(pk=read_app.pk)
    assert services.evaluate_application(app.pk) is None
    assert_manual(app)


def test_switch_hides_previous_ai_output(read_app: Application) -> None:
    assert services.evaluate_application(read_app.pk) is not None
    read_app.refresh_from_db()
    assert read_app.score is not None and read_app.status == Status.UNDER_REVIEW
    killswitch.set_platform(False, actor=None, reason="Pause AI for an audit")
    assert services.evaluate_application(read_app.pk, trigger="manual", force=True) is None
    read_app.refresh_from_db()
    assert read_app.ai_band == "manual_review_requested" and read_app.score is None


def test_llm_and_suggestions_respect_the_switch(read_app: Application, settings: Any) -> None:
    from apps.jobs import suggestions

    settings.LLM_PROVIDER = "anthropic"
    OrganisationPolicy.objects.filter(organisation=read_app.organisation).update(llm_enabled=True)
    flags.set_flag("llm", True)
    flags.set_flag(suggestions.FLAG, True)
    flags.invalidate("llm")
    flags.invalidate(suggestions.FLAG)
    killswitch.set_platform(False, actor=None, reason="Pause all AI features")
    app = Application.objects.unscoped().select_related("organisation").get(pk=read_app.pk)
    assert not services.llm_service(app).enabled
    assert not suggestions.enabled_for(app.job)
    flags.invalidate("llm")
    flags.invalidate(suggestions.FLAG)


def test_platform_api_requires_admin_and_a_reason(read_app: Application) -> None:
    url = "/api/v1/platform/ai/"
    support = admin_client(PlatformRole.PLATFORM_SUPPORT)
    state = support.get(url)
    assert state.status_code == 200 and state.json()["platform_enabled"] is True
    assert {m["kind"] for m in state.json()["models"]} >= {"rules", "embedding", "llm"}
    assert support.post(url, {"enabled": False, "reason": "x" * 12}).status_code == 403
    assert APIClient().get(url).status_code in (401, 403)

    admin = admin_client()
    assert admin.post(url, {"enabled": False, "reason": "short"}, format="json").status_code == 400
    res = admin.post(url, {"enabled": False, "reason": "Incident 42: drift"}, format="json")
    assert res.status_code == 200 and res.json()["platform_enabled"] is False
    assert AuditEvent.objects.filter(action="ai.kill_switch").count() == 1

    org = read_app.organisation
    res = admin.post(
        f"{url}organisations/{org.pk}/",
        {"enabled": False, "reason": "Tenant asked to pause"},
        format="json",
    )
    assert res.status_code == 200
    assert res.json()["disabled_organisations"] == [{"id": str(org.pk), "name": org.name}]
    missing = admin.post(
        f"{url}organisations/00000000-0000-0000-0000-000000000000/",
        {"enabled": False, "reason": "Tenant asked to pause"},
        format="json",
    )
    assert missing.status_code == 404


def test_hr_cannot_reach_the_platform_switch(vacancy: Any) -> None:
    hr = APIClient()
    hr.force_login(vacancy.team.hr_manager)
    res = hr.post(
        "/api/v1/platform/ai/", {"enabled": False, "reason": "not allowed here"}, format="json"
    )
    assert res.status_code == 403


def test_shell_command_for_the_runbook(read_app: Application) -> None:
    from io import StringIO

    from django.core.management import CommandError, call_command

    with pytest.raises(CommandError):
        call_command("ai_switch", "off")
    out = StringIO()
    call_command("ai_switch", "off", reason="Incident 7: drift", stdout=out)
    assert "platform: OFF" in out.getvalue() and not killswitch.platform_enabled()
    org = str(read_app.organisation_id)
    call_command("ai_switch", "on", reason="Incident 7 resolved", stdout=StringIO())
    call_command("ai_switch", "off", reason="Tenant paused AI", org=org, stdout=out)
    assert not killswitch.ai_allowed(org)
    call_command("ai_switch", "inherit", reason="Tenant resumed AI", org=org, stdout=StringIO())
    assert killswitch.ai_allowed(org)
