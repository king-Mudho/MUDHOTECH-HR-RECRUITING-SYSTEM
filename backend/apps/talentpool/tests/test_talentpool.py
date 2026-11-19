"""P13-T01: talent pool consent lifecycle - per-employer opt-in, reconfirmation, reminders,
expiry, leaving and deletion, erasure; the candidate API only touches the person's own data."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Status
from apps.applications.tests.factories import make_application, published_job
from apps.applications.tests.test_submit import ready_draft, submit
from apps.audit.models import AuditEvent
from apps.core.exceptions import NotFoundError
from apps.core.time import now
from apps.notifications.models import Notification
from apps.organisations.tests.factories import make_org_with_team
from apps.privacy.erasure import erase
from apps.privacy.models import ConsentRecord, Purpose
from apps.talentpool import services
from apps.talentpool.models import EntryStatus, TalentPoolEntry

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx() -> dict[str, Any]:
    team, other = make_org_with_team(), make_org_with_team()
    user = UserFactory()
    app = make_application(published_job(organisation=team.org), user, status=Status.UNDER_REVIEW)
    return {"team": team, "other": other, "user": user, "app": app}


def login(user: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    return c


def test_join_needs_an_application_to_that_employer(ctx: dict[str, Any]) -> None:
    with pytest.raises(NotFoundError):
        services.join(ctx["user"], ctx["other"].org.pk)
    entry = services.join(ctx["user"], ctx["team"].org.pk, ip="196.4.81.77")
    assert entry.status == EntryStatus.ACTIVE and entry.source_application_id == ctx["app"].pk
    assert timedelta(days=360) < entry.expires_at - now() < timedelta(days=370)
    consent = entry.consent_record
    assert consent.purpose == Purpose.TALENT_POOL and consent.granted
    assert consent.organisation_id == ctx["team"].org.pk and consent.notice_version.startswith(
        "org-"
    )
    assert consent.ip_trunc == "196.4.81.0/24"
    assert AuditEvent.objects.filter(action="talent_pool.joined").exists()


def test_rejoin_while_active_is_a_reconfirmation(ctx: dict[str, Any]) -> None:
    first = services.join(ctx["user"], ctx["team"].org.pk)
    TalentPoolEntry.objects.unscoped().filter(pk=first.pk).update(
        expires_at=now() + timedelta(days=10), reminder_sent_at=now()
    )
    again = services.join(ctx["user"], ctx["team"].org.pk)
    assert again.pk == first.pk and again.reconfirmed_at is not None
    assert again.reminder_sent_at is None and again.expires_at > now() + timedelta(days=300)
    assert again.consent_record_id != first.consent_record_id  # every decision is a new record
    assert ConsentRecord.objects.filter(user=ctx["user"], purpose="talent_pool").count() == 2


def test_only_consented_active_entries_are_searchable(ctx: dict[str, Any]) -> None:
    org = ctx["team"].org
    services.join(ctx["user"], org.pk)
    assert services.searchable(org.pk).count() == 1
    assert services.searchable(ctx["other"].org.pk).count() == 0  # never across employers
    expired_user = UserFactory()
    make_application(published_job(organisation=org), expired_user, status=Status.SUBMITTED)
    lapsed = services.join(expired_user, org.pk)
    TalentPoolEntry.objects.unscoped().filter(pk=lapsed.pk).update(expires_at=now())
    assert list(services.searchable(org.pk)) == [
        TalentPoolEntry.objects.for_org(org).get(candidate_user=ctx["user"])
    ]


def test_leave_withdraws_consent_and_delete_removes_entry(ctx: dict[str, Any]) -> None:
    org = ctx["team"].org
    services.join(ctx["user"], org.pk)
    left = services.leave(ctx["user"], org.pk)
    assert left is not None and left.status == EntryStatus.WITHDRAWN and left.left_at
    assert services.searchable(org.pk).count() == 0
    assert not ConsentRecord.objects.filter(
        user=ctx["user"], purpose="talent_pool", withdrawn_at__isnull=True
    ).exists()
    services.join(ctx["user"], org.pk)  # coming back is a fresh opt-in
    assert services.searchable(org.pk).count() == 1
    assert services.leave(ctx["user"], org.pk, delete=True) is None
    assert not TalentPoolEntry.objects.for_org(org).exists()
    assert ConsentRecord.objects.filter(user=ctx["user"], purpose="talent_pool").count() == 2
    with pytest.raises(NotFoundError):
        services.leave(ctx["user"], org.pk)


def test_reminder_30_days_before_then_expiry(ctx: dict[str, Any]) -> None:
    entry = services.join(ctx["user"], ctx["team"].org.pk)
    assert services.send_reconfirmation_reminders() == 0  # a year away
    TalentPoolEntry.objects.unscoped().filter(pk=entry.pk).update(
        expires_at=now() + timedelta(days=20)
    )
    assert services.send_reconfirmation_reminders() == 1
    assert services.send_reconfirmation_reminders() == 0  # once
    assert Notification.objects.filter(
        recipient_user=ctx["user"], key="talent_pool_reconfirm"
    ).exists()
    TalentPoolEntry.objects.unscoped().filter(pk=entry.pk).update(expires_at=now())
    assert services.expire_due() == 1
    entry.refresh_from_db()
    assert entry.status == EntryStatus.EXPIRED  # never extended without the candidate


def test_opt_in_at_the_end_of_an_application() -> None:
    job = published_job()
    user = UserFactory()
    app = ready_draft(job, user)
    resp = submit(login(user), app, join_talent_pool=True)
    assert resp.status_code == 201, resp.content
    entry = TalentPoolEntry.objects.for_org(job.organisation).get(candidate_user=user)
    assert entry.source_application_id == app.pk and entry.status == EntryStatus.ACTIVE
    other = ready_draft(published_job(), UserFactory())
    assert submit(login(other.candidate_user), other).status_code == 201
    assert not TalentPoolEntry.objects.unscoped().filter(candidate_user=other.candidate_user)


def test_candidate_api(ctx: dict[str, Any]) -> None:
    me = login(ctx["user"])
    org_id = str(ctx["team"].org.pk)
    rows = me.get("/api/v1/candidate/talent-pools/").json()
    assert [(r["organisation_id"], r["status"]) for r in rows] == [(org_id, "none")]
    joined = me.post("/api/v1/candidate/talent-pools/", {"organisation_id": org_id}, format="json")
    assert joined.status_code == 200 and joined.json()["status"] == "active"
    foreign = me.post(
        "/api/v1/candidate/talent-pools/",
        {"organisation_id": str(ctx["other"].org.pk)},
        format="json",
    )
    assert foreign.status_code == 404
    stranger = login(UserFactory())
    assert stranger.get("/api/v1/candidate/talent-pools/").json() == []
    assert (
        stranger.post(
            f"/api/v1/candidate/talent-pools/{org_id}/leave/", {}, format="json"
        ).status_code
        == 404
    )
    left = me.post(f"/api/v1/candidate/talent-pools/{org_id}/leave/", {}, format="json")
    assert left.status_code == 200 and left.json()["status"] == "withdrawn"
    gone = me.post(
        f"/api/v1/candidate/talent-pools/{org_id}/leave/", {"delete": True}, format="json"
    )
    assert gone.status_code == 200 and gone.json()["status"] == "none"
    assert APIClient().get("/api/v1/candidate/talent-pools/").status_code in (401, 403)


def test_erasure_removes_pool_entries(ctx: dict[str, Any]) -> None:
    services.join(ctx["user"], ctx["team"].org.pk)
    counts = erase(ctx["user"], ctx["team"].org.pk)
    assert counts["talent_pool"] == 1
    assert not TalentPoolEntry.objects.unscoped().filter(candidate_user=ctx["user"]).exists()


def test_withdrawing_the_consent_elsewhere_ends_the_membership(ctx: dict[str, Any]) -> None:
    entry = services.join(ctx["user"], ctx["team"].org.pk)
    me = login(ctx["user"])
    resp = me.post(f"/api/v1/privacy/consents/{entry.consent_record_id}/withdraw/")
    assert resp.status_code == 200
    assert services.searchable(ctx["team"].org.pk).count() == 0
    assert me.get("/api/v1/candidate/talent-pools/").json()[0]["status"] == "withdrawn"
