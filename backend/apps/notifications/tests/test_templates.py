"""Notification templates and the safe renderer (P05-T01)."""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.core.exceptions import DomainError
from apps.notifications import registry, services
from apps.notifications.models import NotificationTemplate
from apps.notifications.renderer import (
    TemplateRenderError,
    TemplateValidationError,
    render,
    validate,
)
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db

RECEIPT_BODY = (
    "Hello {{ recipient_name }},\n\n"
    "We received your application for **{{ job_title }}** at {{ organisation_name }}.\n"
    "Your reference is {{ reference }}.\n\n"
    "[View your application]({{ application_url }})"
)


def default_receipt() -> NotificationTemplate:
    return services.save_template(
        None,
        actor=None,
        key="application_received",
        subject="We received your application for {{ job_title }}",
        body_md=RECEIPT_BODY,
    )


def ctx(**over: Any) -> dict[str, Any]:
    return {**registry.sample_context("application_received"), **over}


# ------------------------------------------------------------------------------ renderer
def test_validate_rejects_unknown_variables_and_template_syntax() -> None:
    allowed = registry.get("application_received").allowed
    assert validate("Hi {{ recipient_name }}", "Ref {{reference}}", allowed) == [
        "recipient_name",
        "reference",
    ]
    with pytest.raises(TemplateValidationError) as exc:
        validate("Hi {{ password }}", "{% load os %} {{ user.email }}", allowed)
    assert "Unknown variables: password." in exc.value.errors["subject"][0]
    assert any("Only {{ variable }}" in e for e in exc.value.errors["body_md"])
    with pytest.raises(TemplateValidationError) as exc:
        validate("Line one\nLine two", "   ", allowed)
    assert set(exc.value.errors) == {"subject", "body_md"}


def test_render_escapes_values_and_sanitises_markdown_html() -> None:
    out = render(
        "Update for {{ job_title }}",
        "Hello {{ recipient_name }}\n\n<script>alert(1)</script>\n\n[Open]({{ portal_url }})",
        {
            "job_title": "Dev",
            "recipient_name": "<img src=x onerror=1>",
            "portal_url": "https://x.test/a",
        },
        brand="MHRS",
    )
    assert out.subject == "Update for Dev"
    assert "<script" not in out.html and "onerror=1>" not in out.html
    assert "&lt;img src=x onerror=1&gt;" in out.html
    assert 'href="https://x.test/a"' in out.html and 'rel="noopener noreferrer"' in out.html
    assert "Open (https://x.test/a)" in out.text  # plain-text alternative keeps the link
    assert "Replies to this address are not read" in out.text and "<p>" not in out.text


def test_render_blocks_dangerous_link_schemes() -> None:
    out = render("S", "[Click]({{ portal_url }})", {"portal_url": "javascript:alert(1)"}, brand="B")
    assert "javascript:" not in out.html


def test_missing_value_fails_safe() -> None:
    with pytest.raises(TemplateRenderError):
        render("S {{ job_title }}", "Body", {}, brand="B")


def test_every_sample_context_covers_its_variables() -> None:
    for key, kind in registry.KINDS.items():
        assert set(registry.sample_context(key)) == set(kind.allowed), key


# ------------------------------------------------------------------------------ services
def test_saving_creates_versions_and_audits() -> None:
    team = make_org_with_team()
    default = default_receipt()
    first = services.save_template(
        team.org,
        actor=team.hr_manager,
        key="application_received",
        subject="Thanks for applying, {{ recipient_name }}",
        body_md=RECEIPT_BODY,
    )
    second = services.save_template(
        team.org,
        actor=team.hr_manager,
        key="application_received",
        subject="Application received: {{ job_title }}",
        body_md=RECEIPT_BODY,
    )
    first.refresh_from_db()
    assert (first.version, first.active, second.version, second.active) == (1, False, 2, True)
    assert second.variables == sorted(
        {"recipient_name", "job_title", "organisation_name", "reference", "application_url"}
    )
    assert services.effective_template(team.org, "application_received") == second
    assert services.effective_template(make_org_with_team().org, "application_received") == default
    assert AuditEvent.objects.filter(
        action="notification_template.saved", target_id=str(second.pk)
    ).exists()
    services.revert_to_default(team.org, actor=team.hr_manager, key="application_received")
    assert services.effective_template(team.org, "application_received") == default


def test_save_validation_errors_are_field_level() -> None:
    team = make_org_with_team()
    with pytest.raises(DomainError) as exc:
        services.save_template(
            team.org,
            actor=team.hr_manager,
            key="application_received",
            subject="Your score is {{ score }}",
            body_md="x",
        )
    assert exc.value.code == "validation_error" and "subject" in exc.value.details
    with pytest.raises(DomainError):
        services.save_template(team.org, actor=None, key="nope", subject="S", body_md="B")


def test_override_that_cannot_render_falls_back_to_default() -> None:
    """EC-NOT-05: a value the override needs is missing -> the platform default is used."""
    team = make_org_with_team()
    default_receipt()
    services.save_template(
        team.org,
        actor=team.hr_manager,
        key="application_received",
        subject="Received",
        body_md="Track it here: {{ application_url }}",
    )
    context = ctx()
    context.pop("application_url")
    default_body = RECEIPT_BODY.replace("[View your application]({{ application_url }})", "")
    NotificationTemplate.objects.filter(organisation__isnull=True).update(body_md=default_body)
    rendered, used = services.render_for(team.org, "application_received", context)
    assert used.organisation_id is None and "Software Developer" in rendered.text


# ------------------------------------------------------------------------------ API
def hr(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


def test_api_list_save_preview_history_revert() -> None:
    team = make_org_with_team()
    default = default_receipt()
    c = hr(team.hr_manager, team.org)
    rows = c.get("/api/v1/hr/notification-templates/").json()
    assert [r["id"] for r in rows] == [str(default.pk)] and rows[0]["is_default"] is True
    assert "application_url" in rows[0]["allowed_variables"]
    bad = c.post(
        "/api/v1/hr/notification-templates/",
        {"key": "application_received", "subject": "{{ score }}", "body_md": "x"},
        format="json",
    )
    assert bad.status_code == 400 and "subject" in bad.json()["error"]["details"]
    made = c.post(
        "/api/v1/hr/notification-templates/",
        {
            "key": "application_received",
            "subject": "Got it: {{ job_title }}",
            "body_md": RECEIPT_BODY,
        },
        format="json",
    )
    assert made.status_code == 201 and made.json()["version"] == 1
    tid = made.json()["id"]
    preview = c.post(
        f"/api/v1/hr/notification-templates/{tid}/preview/",
        {"context": {"job_title": "Accountant"}},
        format="json",
    ).json()
    assert preview["subject"] == "Got it: Accountant" and "MHRS-" in preview["text"]
    assert len(c.get(f"/api/v1/hr/notification-templates/{tid}/history/").json()) == 2
    assert (
        c.post(
            "/api/v1/hr/notification-templates/revert/",
            {"key": "application_received"},
            format="json",
        ).status_code
        == 204
    )
    assert c.get("/api/v1/hr/notification-templates/").json()[0]["id"] == str(default.pk)


def test_api_permissions_and_isolation() -> None:
    team, other = make_org_with_team(), make_org_with_team()
    default_receipt()
    theirs = services.save_template(
        other.org, actor=other.hr_manager, key="application_received", subject="S", body_md="B"
    )
    assert hr(team.recruiter, team.org).get("/api/v1/hr/notification-templates/").status_code == 403
    c = hr(team.admin, team.org)
    assert c.get(f"/api/v1/hr/notification-templates/{theirs.pk}/").status_code == 404
    assert (
        c.post(
            f"/api/v1/hr/notification-templates/{theirs.pk}/preview/", {}, format="json"
        ).status_code
        == 404
    )
