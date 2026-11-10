"""Shared fixtures for the jobs test-suite."""

from __future__ import annotations

import pytest

from apps.core.time import now
from apps.organisations.models import OrganisationPolicy
from apps.organisations.tests.factories import OrgTeam, make_org_with_team


@pytest.fixture
def team() -> OrgTeam:
    t = make_org_with_team()
    t.org.verified_at = now()
    t.org.save(update_fields=["verified_at"])
    OrganisationPolicy.objects.filter(organisation=t.org).update(
        privacy_notice="We process your application data to assess suitability for the role."
    )
    return t
