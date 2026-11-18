"""P12-T02: scheduling, self-booking, reschedule/cancel, no-show, reminders, ICS (EC-INT-01..03)."""

from __future__ import annotations

import threading
from datetime import timedelta
from typing import Any

import pytest
from django.db import connection

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application, Status
from apps.applications.tests.factories import make_application, published_job
from apps.audit.models import AuditEvent
from apps.core import time as mhrs_time
from apps.core.exceptions import DomainError, PermissionDeniedError
from apps.interviews import scheduling
from apps.interviews.ics import _escape, interview_ics
from apps.interviews.models import Interview, InterviewSlot, InterviewStatus
from apps.notifications.models import Notification
from apps.organisations.models import Membership
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx() -> dict[str, Any]:
    team = make_org_with_team()
    job = published_job(organisation=team.org)
    app = make_application(job, status=Status.SHORTLISTED)
    lead = Membership.objects.for_org(team.org).get(user=team.hr_manager)
    member = Membership.objects.for_org(team.org).get(user=team.recruiter)
    return {"team": team, "job": job, "app": app, "lead": lead, "member": member}


def soon(hours: float = 48) -> Any:
    return (mhrs_time.now() + timedelta(hours=hours)).replace(microsecond=0)


def schedule(ctx: dict[str, Any], **kw: Any) -> scheduling.Scheduled:
    args: dict[str, Any] = {
        "actor": ctx["team"].recruiter,
        "stage": "Technical interview",
        "mode": "video",
        "panel": [(ctx["lead"], "lead"), (ctx["member"], "member")],
    }
    if "slots" not in kw and "starts_at" not in kw:
        args["starts_at"] = soon()
    args.update(kw)
    return scheduling.create_interview(ctx["app"], **args)


def keys(user: Any) -> list[str]:
    return list(Notification.objects.filter(recipient_user=user).values_list("key", flat=True))


def test_fixed_time_schedules_moves_application_and_invites(ctx: dict[str, Any]) -> None:
    result = schedule(ctx)
    iv = result.interview
    assert iv.status == InterviewStatus.SCHEDULED and iv.ends_at - iv.starts_at == timedelta(
        minutes=45
    )
    ctx["app"].refresh_from_db()
    assert ctx["app"].status == Status.INTERVIEW
    assert "interview_invitation" in keys(ctx["app"].candidate_user)
    assert iv.panelists.count() == 2 and result.conflicts == []
    assert AuditEvent.objects.filter(action="interviews.created").exists()
    # a second interview for the same application (next stage) is fine while in interview
    second = schedule(ctx, stage="Final interview", starts_at=soon(96))
    assert second.interview.status == InterviewStatus.SCHEDULED


def test_panelist_double_booking_is_a_warning(ctx: dict[str, Any]) -> None:
    """EC-INT-01: warn, never block."""
    at = soon()
    schedule(ctx, starts_at=at)
    other_app = make_application(ctx["job"], status=Status.SHORTLISTED)
    result = scheduling.create_interview(
        other_app,
        actor=ctx["team"].recruiter,
        stage="Technical interview",
        mode="phone",
        panel=[(ctx["lead"], "lead")],
        starts_at=at + timedelta(minutes=30),
    )
    assert result.interview.status == InterviewStatus.SCHEDULED
    assert [c["membership_id"] for c in result.conflicts] == [str(ctx["lead"].pk)]


@pytest.mark.parametrize(
    ("kw", "code"),
    [
        ({"panel": []}, "validation_error"),
        ({"starts_at": soon(), "slots": [soon(50)]}, "validation_error"),
        ({"starts_at": mhrs_time.now() - timedelta(hours=1)}, "validation_error"),
        ({"timezone": "Mars/Olympus_Mons"}, "validation_error"),
        ({"mode": "in_person"}, "validation_error"),  # no address
        ({"stage": "  "}, "validation_error"),
    ],
)
def test_validation(ctx: dict[str, Any], kw: dict[str, Any], code: str) -> None:
    with pytest.raises(DomainError) as err:
        schedule(ctx, **kw)
    assert err.value.code == code


def test_only_shortlisted_applications_and_only_staff(ctx: dict[str, Any]) -> None:
    Application.objects.unscoped().filter(pk=ctx["app"].pk).update(status=Status.UNDER_REVIEW)
    with pytest.raises(DomainError) as err:
        schedule(ctx)
    assert err.value.code == "invalid_state"
    Application.objects.unscoped().filter(pk=ctx["app"].pk).update(status=Status.SHORTLISTED)
    with pytest.raises(PermissionDeniedError):
        schedule(ctx, actor=UserFactory())
    outsider = make_org_with_team()
    with pytest.raises(PermissionDeniedError):
        schedule(ctx, actor=outsider.recruiter)


def test_self_booking(ctx: dict[str, Any]) -> None:
    times = [soon(48), soon(50), soon(72)]
    iv = schedule(ctx, slots=times).interview
    assert iv.status == InterviewStatus.PROPOSED and iv.starts_at is None
    slots = list(InterviewSlot.objects.for_org(ctx["team"].org).filter(interview=iv))
    assert [s.starts_at for s in slots] == times
    candidate = ctx["app"].candidate_user
    with pytest.raises(PermissionDeniedError):
        scheduling.book_slot(iv, slots[0].pk, candidate=UserFactory())
    booked = scheduling.book_slot(iv, slots[1].pk, candidate=candidate)
    assert booked.status == InterviewStatus.SCHEDULED and booked.starts_at == times[1]
    assert "interview_booked" in keys(ctx["team"].hr_manager)  # the lead is told (in-app)
    with pytest.raises(DomainError) as err:
        scheduling.book_slot(iv, slots[2].pk, candidate=candidate)
    assert err.value.code == "interview_not_bookable"


def test_past_slot_cannot_be_booked(ctx: dict[str, Any]) -> None:
    iv = schedule(ctx, slots=[soon(48)]).interview
    slot = iv.slots.get()
    InterviewSlot.objects.filter(pk=slot.pk).update(
        starts_at=mhrs_time.now() - timedelta(hours=2), ends_at=mhrs_time.now() - timedelta(hours=1)
    )
    with pytest.raises(DomainError) as err:
        scheduling.book_slot(iv, slot.pk, candidate=ctx["app"].candidate_user)
    assert err.value.code == "slot_in_past"


@pytest.mark.django_db(transaction=True)
def test_two_concurrent_bookings_only_one_wins() -> None:
    team = make_org_with_team()
    app = make_application(published_job(organisation=team.org), status=Status.SHORTLISTED)
    lead = Membership.objects.for_org(team.org).get(user=team.hr_manager)
    iv = scheduling.create_interview(
        app,
        actor=team.recruiter,
        stage="Technical",
        mode="video",
        panel=[(lead, "lead")],
        slots=[soon(48), soon(50)],
    ).interview
    slot_ids = list(iv.slots.values_list("pk", flat=True))
    barrier, results = threading.Barrier(2), []

    def book(slot_id: Any) -> None:
        try:
            barrier.wait()
            scheduling.book_slot(iv, slot_id, candidate=app.candidate_user)
            results.append("ok")
        except DomainError as exc:
            results.append(exc.code)
        finally:
            connection.close()

    threads = [threading.Thread(target=book, args=(s,)) for s in slot_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ["interview_not_bookable", "ok"]
    assert InterviewSlot.objects.for_org(team.org).filter(interview=iv, booked=True).count() == 1


def test_reschedule_needs_reason_bumps_sequence_and_rearms_reminders(ctx: dict[str, Any]) -> None:
    iv = schedule(ctx).interview
    Interview.objects.filter(pk=iv.pk).update(reminder_24h_sent_at=mhrs_time.now())
    with pytest.raises(DomainError):
        scheduling.reschedule(iv, actor=ctx["team"].recruiter, reason="no", starts_at=soon(96))
    new = soon(96)
    moved = scheduling.reschedule(
        iv, actor=ctx["team"].recruiter, reason="Panel member unavailable", starts_at=new
    ).interview
    assert moved.starts_at == new and moved.sequence == 1 and moved.reminder_24h_sent_at is None
    assert "interview_rescheduled" in keys(ctx["app"].candidate_user)
    # back to offering times
    offered = scheduling.reschedule(
        iv,
        actor=ctx["team"].recruiter,
        reason="Let the candidate choose",
        slots=[soon(120), soon(122)],
    ).interview
    assert offered.status == InterviewStatus.PROPOSED and offered.slots.count() == 2


def test_cancel(ctx: dict[str, Any]) -> None:
    iv = schedule(ctx).interview
    done = scheduling.cancel(iv, actor=ctx["team"].recruiter, reason="Position on hold this week")
    assert done.status == InterviewStatus.CANCELLED and done.sequence == 1
    assert "interview_cancelled" in keys(ctx["app"].candidate_user)
    with pytest.raises(DomainError):
        scheduling.cancel(iv, actor=ctx["team"].recruiter, reason="Again, twice")


def test_no_show_is_recorded_not_a_rejection(ctx: dict[str, Any]) -> None:
    """EC-INT-03."""
    iv = schedule(ctx).interview
    with pytest.raises(DomainError):  # not started yet
        scheduling.mark_no_show(iv, actor=ctx["team"].recruiter)
    Interview.objects.filter(pk=iv.pk).update(
        starts_at=mhrs_time.now() - timedelta(minutes=30),
        ends_at=mhrs_time.now() + timedelta(minutes=15),
    )
    done = scheduling.mark_no_show(iv, actor=ctx["team"].recruiter, note="Did not join the call")
    assert done.status == InterviewStatus.NO_SHOW
    ctx["app"].refresh_from_db()
    assert ctx["app"].status == Status.INTERVIEW  # still in the process; HR decides later
    assert AuditEvent.objects.filter(action="interviews.no_show").exists()


def test_reminders_24h_and_1h_once_each(ctx: dict[str, Any]) -> None:
    iv = schedule(ctx, starts_at=soon(30)).interview
    now = mhrs_time.now()
    assert scheduling.send_due_reminders(now) == 0  # 30 h ahead: nothing yet
    assert (
        scheduling.send_due_reminders(now + timedelta(hours=7)) == 1
    )  # 23 h before -> 24 h reminder
    assert scheduling.send_due_reminders(now + timedelta(hours=8)) == 0  # not twice
    assert (
        scheduling.send_due_reminders(now + timedelta(hours=29, minutes=30)) == 1
    )  # 30 min before
    assert scheduling.send_due_reminders(now + timedelta(hours=29, minutes=40)) == 0
    reminders = Notification.objects.filter(
        recipient_user=ctx["app"].candidate_user, key="interview_reminder"
    )
    assert reminders.filter(channel="email").count() == 2  # one 24 h + one 1 h (each also in-app)
    iv.refresh_from_db()
    assert iv.reminder_24h_sent_at and iv.reminder_1h_sent_at


def test_short_notice_booking_gets_only_the_1h_reminder(ctx: dict[str, Any]) -> None:
    schedule(ctx, starts_at=soon(0.75))
    assert scheduling.send_due_reminders() == 1
    assert Notification.objects.filter(dedupe_key__contains=":24h:").count() == 0
    assert Notification.objects.filter(dedupe_key__contains=":1h:").count() == 2  # email + in-app


def test_messages_show_the_arranged_timezone_and_offset(ctx: dict[str, Any]) -> None:
    """EC-INT-02."""
    at = mhrs_time.now().replace(
        year=2030, month=1, day=15, hour=8, minute=0, second=0, microsecond=0
    )
    assert scheduling.format_when(at, "Africa/Harare") == (
        "Tuesday 15 January 2030, 10:00 (Africa/Harare, UTC+02:00)"
    )
    assert "(Europe/London, UTC+00:00)" in scheduling.format_when(at, "Europe/London")


def test_ics(ctx: dict[str, Any]) -> None:
    iv = schedule(ctx, starts_at=soon(48), timezone="Africa/Harare").interview
    iv.refresh_from_db()
    ics = interview_ics(iv)
    assert ics.endswith("\r\n") and "\n" not in ics.replace("\r\n", "")
    assert f"UID:interview-{iv.pk}@mhrs" in ics and "SEQUENCE:0" in ics and "METHOD:REQUEST" in ics
    assert "BEGIN:VTIMEZONE\r\nTZID:Africa/Harare" in ics and "TZOFFSETTO:+0200" in ics
    local = iv.starts_at.astimezone(scheduling.zone("Africa/Harare")).strftime("%Y%m%dT%H%M%S")
    assert f"DTSTART;TZID=Africa/Harare:{local}" in ics
    assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))
    assert f"SUMMARY:Technical interview: {ctx['job'].title}" in ics.replace("\r\n ", "")
    assert _escape("a,b;c\\d\ne") == "a\\,b\\;c\\\\d\\ne"  # RFC 5545 3.3.11
    cancelled = scheduling.cancel(
        iv, actor=ctx["team"].recruiter, reason="Position filled internally"
    )
    ics2 = interview_ics(cancelled)
    assert "METHOD:CANCEL" in ics2 and "STATUS:CANCELLED" in ics2 and "SEQUENCE:1" in ics2
    assert "VALARM" not in ics2
    proposed = schedule(ctx, slots=[soon(200)]).interview
    with pytest.raises(ValueError):
        interview_ics(proposed)
