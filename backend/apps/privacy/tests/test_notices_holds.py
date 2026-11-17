"""Privacy notices and legal holds (P09-T01, EC-PRV-09, EC-PRV-01)."""

from __future__ import annotations

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditEvent
from apps.core.exceptions import DomainError, NotFoundError
from apps.organisations.models import OrganisationPolicy
from apps.organisations.tests.factories import make_org_with_team
from apps.privacy import services
from apps.privacy.models import LegalHold, PrivacyNotice

pytestmark = pytest.mark.django_db


def test_each_notice_version_keeps_its_wording() -> None:
    team = make_org_with_team()
    OrganisationPolicy.objects.filter(organisation=team.org).update(privacy_notice="Version one")
    v1, text1 = services.privacy_notice_version(team.org)
    old = services.record(
        UserFactory(),
        "application_processing",
        granted=True,
        notice_version=v1,
        organisation=team.org,
    )
    OrganisationPolicy.objects.filter(organisation=team.org).update(privacy_notice="Version two")
    v2, _ = services.privacy_notice_version(team.org)
    assert v1 != v2  # new applications get the new version (EC-PRV-09)
    assert services.privacy_notice_version(team.org)[0] == v2  # idempotent
    notices = dict(
        PrivacyNotice.objects.filter(organisation=team.org).values_list("version", "text")
    )
    assert notices == {v1: "Version one", v2: "Version two"}
    old.refresh_from_db()
    assert old.notice_version == v1  # earlier consent stays linked to the wording it saw
    assert text1 == "Version one"


def test_legal_holds_cover_targets_until_released() -> None:
    team = make_org_with_team()
    app_id = "4b1d6f8e-0a65-4c33-9c41-0b3c29f2a111"
    with pytest.raises(DomainError):
        services.place_hold(
            team.org.pk, team.admin, target_type="application", target_id=app_id, reason=""
        )
    hold = services.place_hold(
        team.org.pk,
        team.admin,
        target_type="application",
        target_id=app_id,
        reason="Tribunal case 12/2026",
    )
    assert services.is_held(team.org.pk, application_id=app_id)
    assert not services.is_held(team.org.pk, application_id="5b1d6f8e-0a65-4c33-9c41-0b3c29f2a111")
    other = make_org_with_team()
    assert not services.is_held(other.org.pk, application_id=app_id)  # tenant scoped
    services.release_hold(team.org.pk, team.admin, hold.pk)
    assert not services.is_held(team.org.pk, application_id=app_id)
    with pytest.raises(NotFoundError):
        services.release_hold(team.org.pk, team.admin, hold.pk)
    actions = set(AuditEvent.objects.filter(organisation=team.org).values_list("action", flat=True))
    assert {"privacy.legal_hold_placed", "privacy.legal_hold_released"} <= actions
    assert LegalHold.objects.for_org(team.org).get(pk=hold.pk).released_by == team.admin
