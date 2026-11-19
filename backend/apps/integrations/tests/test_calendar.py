"""P15-T02: calendar sync (sandbox) - events created on schedule/booking, updated on reschedule,
cancelled on cancel; free/busy adds conflict warnings; a failing calendar never affects the
interview."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import pytest

from apps.applications.models import Status
from apps.applications.tests.factories import make_application, published_job
from apps.core.models import OutboxEvent
from apps.core.time import now
from apps.integrations import calendar_sync
from apps.integrations.adapters import base
from apps.integrations.adapters.base import IntegrationError
from apps.integrations.adapters.calendar import GoogleCalendarAdapter
from apps.integrations.models import CalendarEventLink, IntegrationConnection
from apps.interviews import scheduling
from apps.interviews.models import InterviewStatus
from apps.organisations.models import Membership
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx() -> dict[str, Any]:
    team = make_org_with_team()
    app = make_application(published_job(organisation=team.org), status=Status.SHORTLISTED)
    lead = Membership.objects.for_org(team.org).get(user=team.hr_manager)
    panel = Membership.objects.for_org(team.org).get(user=team.panelist)
    conn = IntegrationConnection.objects.create(
        organisation=team.org,
        provider="google_calendar",
        owner_user=team.panelist,
        credentials=json.dumps({"refresh_token": "1//sandbox-token"}),
        credentials_hint="…oken",
    )
    base.SANDBOX_OUTBOX.clear()
    return {"team": team, "app": app, "lead": lead, "panel": panel, "conn": conn}


def schedule(ctx: dict[str, Any], hours: int = 48) -> Any:
    return scheduling.create_interview(
        ctx["app"],
        actor=ctx["team"].recruiter,
        stage="Technical",
        mode="video",
        panel=[(ctx["lead"], "lead"), (ctx["panel"], "member")],
        starts_at=now() + timedelta(hours=hours),
    ).interview


def test_event_lifecycle_follows_the_interview(ctx: dict[str, Any]) -> None:
    iv = schedule(ctx)
    assert OutboxEvent.objects.filter(event_type="interview.changed").count() == 1
    assert calendar_sync.sync_interview(iv.pk) == {"upserted": 1, "cancelled": 0, "failed": 0}
    link = CalendarEventLink.objects.for_org(ctx["team"].org).get()
    assert link.external_id == f"sandbox-{iv.pk}" and link.connection == ctx["conn"]
    sent = [r for r in base.SANDBOX_OUTBOX if r["method"] == "POST"][-1]
    assert sent["url"].endswith("/calendars/primary/events")
    assert ctx["app"].reference in sent["body"]["summary"]
    assert ctx["app"].candidate_user.email not in json.dumps(sent["body"])  # no contact details
    scheduling.reschedule(
        iv, actor=ctx["team"].recruiter, reason="Panel moved", starts_at=now() + timedelta(days=4)
    )
    iv.refresh_from_db()
    calendar_sync.sync_interview(iv.pk)
    assert base.SANDBOX_OUTBOX[-1]["method"] == "PATCH"
    scheduling.cancel(iv, actor=ctx["team"].recruiter, reason="Role filled internally")
    assert calendar_sync.sync_interview(iv.pk)["cancelled"] == 1
    assert base.SANDBOX_OUTBOX[-1]["method"] == "DELETE"
    link.refresh_from_db()
    assert link.cancelled is True


def test_failing_calendar_never_affects_the_interview(
    ctx: dict[str, Any], monkeypatch: Any
) -> None:
    def broken(self: Any, event: Any, external_id: str = "") -> str:
        raise IntegrationError("google_calendar: HTTP 503")

    monkeypatch.setattr(GoogleCalendarAdapter, "upsert_event", broken)
    iv = schedule(ctx)
    assert calendar_sync.sync_interview(iv.pk)["failed"] == 1
    iv.refresh_from_db()
    assert iv.status == InterviewStatus.SCHEDULED
    ctx["conn"].refresh_from_db()
    assert ctx["conn"].last_error.endswith("HTTP 503")


def test_free_busy_adds_conflict_warnings(ctx: dict[str, Any], monkeypatch: Any) -> None:
    start = now() + timedelta(hours=48)
    monkeypatch.setattr(
        GoogleCalendarAdapter,
        "busy",
        lambda self, s, e: [(start.isoformat(), (start + timedelta(hours=1)).isoformat())],
    )
    result = scheduling.create_interview(
        ctx["app"],
        actor=ctx["team"].recruiter,
        stage="Technical",
        mode="video",
        panel=[(ctx["lead"], "lead"), (ctx["panel"], "member")],
        starts_at=start,
    )
    external = [c for c in result.conflicts if c.get("source") == "google_calendar"]
    assert len(external) == 1 and external[0]["membership_id"] == str(ctx["panel"].pk)
    assert result.interview.status == InterviewStatus.SCHEDULED  # a warning, never a block
