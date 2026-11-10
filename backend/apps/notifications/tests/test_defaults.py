"""Platform default templates (P05-T02)."""

from __future__ import annotations

import re

import pytest

from apps.notifications import registry, services
from apps.notifications.defaults import DEFAULTS
from apps.notifications.models import Channel, NotificationTemplate

pytestmark = pytest.mark.django_db

FORBIDDEN = re.compile(
    r"\b(score|scored|scoring|rank|ranking|rejected|fail(ed)?|percent|%)\b", re.I
)


def test_every_notification_has_an_email_and_inapp_default_after_migrate() -> None:
    assert set(DEFAULTS) == set(registry.KINDS)
    for key in registry.KINDS:
        for channel in (Channel.EMAIL, Channel.INAPP):
            assert services.platform_default(key, channel) is not None, (key, channel)


@pytest.mark.parametrize("key", sorted(DEFAULTS))
def test_defaults_render_with_samples_and_carry_no_sensitive_details(key: str) -> None:
    """FR-M14-04 / EC-NOT: no scores, rankings or screening reasons; links to the portal."""
    email = services.platform_default(key, Channel.EMAIL)
    assert email is not None
    rendered = services.render_template(email, registry.sample_context(key))
    assert not FORBIDDEN.search(email.subject + email.body_md), key
    assert "{{" not in rendered.text and "{{" not in rendered.html
    assert rendered.subject and len(rendered.subject) <= 120
    inapp = services.platform_default(key, Channel.INAPP)
    assert inapp is not None and "\n" not in inapp.body_md.strip() and len(inapp.body_md) <= 160


def test_not_selected_is_respectful_and_human_decided() -> None:
    body = DEFAULTS["not_selected"].body_md
    assert "made by a person" in body and "Thank you" in body


def test_sync_is_idempotent_and_versions_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    before = NotificationTemplate.objects.filter(organisation__isnull=True).count()
    assert services.sync_platform_defaults()["created"] == 0
    assert NotificationTemplate.objects.filter(organisation__isnull=True).count() == before
    from apps.notifications import defaults

    changed = dict(defaults.DEFAULTS)
    old = changed["draft_abandoned"]
    changed["draft_abandoned"] = defaults.DefaultTemplate(
        old.subject, old.body_md + "\n\nThanks.", old.inapp
    )
    monkeypatch.setattr(defaults, "DEFAULTS", changed)
    assert services.sync_platform_defaults()["created"] == 1
    current = services.platform_default("draft_abandoned")
    assert current is not None and current.version == 2 and current.body_md.endswith("Thanks.")
