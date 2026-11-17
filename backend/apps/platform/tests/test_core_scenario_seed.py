"""seed_core_scenario (P08-T13): synthetic applications through the real submission services."""

from __future__ import annotations

from typing import Any

import pytest

from apps.applications.models import Application
from apps.core.models import OutboxEvent
from apps.organisations.models import OrganisationPolicy
from apps.platform import core_scenario
from apps.platform.demo_seed import seed as seed_demo

pytestmark = pytest.mark.django_db
PASSWORD = "Synthetic-Demo-Seed-2026"


def test_seed_submits_applications_idempotently(s3: Any) -> None:
    seed_demo(PASSWORD)
    result = core_scenario.seed(3, PASSWORD, delay_minutes=1)
    assert len(result.submitted) == 3
    apps = Application.objects.unscoped().filter(pk__in=result.submitted)
    assert set(apps.values_list("status", flat=True)) == {"submitted"}
    assert all(a.reference and a.consent_record_id for a in apps)
    assert all(a.documents.count() == 1 for a in apps)
    assert OutboxEvent.objects.filter(event_type="application.submitted").count() >= 3
    job_org = apps.first().organisation_id  # type: ignore[union-attr]
    assert OrganisationPolicy.objects.get(organisation_id=job_org).notification_delay_minutes == 1
    zone = apps.first().candidate_user.timezone  # type: ignore[union-attr]
    assert zone in core_scenario.DAYTIME_ZONES
    again = core_scenario.seed(3, PASSWORD)
    assert again.submitted == [] and again.skipped == 3
