"""Delivery pipeline (P05-T03): dedupe, replay safety, suppression, quiet hours, retries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest import mock

import pytest
from django.core import mail
from django.db import transaction

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Status
from apps.applications.tests.factories import make_application
from apps.core.models import DeadLetter, OutboxEvent
from apps.core.outbox import relay_batch
from apps.core.time import now
from apps.notifications import delivery, services
from apps.notifications.models import (
    Channel,
    EmailSuppression,
    Notification,
    NotificationStatus,
)
from apps.notifications.tasks import send_due, send_notification
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db

DAYTIME = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)  # 12:00 in Harare
NIGHT = datetime(2026, 11, 10, 21, 30, tzinfo=UTC)  # 23:30 in Harare

CONTEXT = {
    "organisation_name": "Acme",
    "job_title": "Software Developer",
    "reference": "MHRS-ACME1A2B-2026-000001",
    "application_url": "https://mhrs.example/candidate/applications/1",
}


def queue(
    user: Any, key: str = "application_received", dedupe: str = "k1", **kw: Any
) -> list[Notification]:
    with transaction.atomic():
        return delivery.notify(
            user, key, {**CONTEXT, **kw.pop("context", {})}, dedupe_key=dedupe, **kw
        )


def email_of(rows: list[Notification]) -> Notification:
    return next(n for n in rows if n.channel == Channel.EMAIL)


@pytest.fixture
def user() -> Any:
    return UserFactory(first_name="Tendai")


def test_notify_creates_email_and_inapp_once(user: Any) -> None:
    """EC-NOT-03: the same dedupe key never creates a second message."""
    first = queue(user)
    assert {n.channel for n in first} == {"email", "inapp"}
    assert queue(user) == []
    assert Notification.objects.filter(recipient_user=user).count() == 2
    assert OutboxEvent.objects.filter(event_type=delivery.EVENT).count() == 1
    inapp = next(n for n in first if n.channel == Channel.INAPP)
    assert inapp.status == NotificationStatus.DELIVERED
    assert "MHRS-ACME1A2B-2026-000001" in delivery.render_inapp(inapp)


def test_deliver_sends_branded_email_with_stable_message_id(user: Any) -> None:
    n = email_of(queue(user))
    assert delivery.deliver(n.pk) == NotificationStatus.SENT
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.to == [user.email] and "Software Developer" in msg.subject
    assert msg.extra_headers["Message-ID"] == f"<{n.pk}@mhrs.local>"
    assert "Hello Tendai" in msg.body and "text/html" in msg.alternatives[0][1]
    n.refresh_from_db()
    assert n.sent_at is not None and n.attempts == 1 and n.template is not None


def test_replayed_event_and_duplicate_tasks_never_send_twice(
    user: Any, django_capture_on_commit_callbacks: Any
) -> None:
    """Exit criterion: replaying events never sends duplicates."""
    with django_capture_on_commit_callbacks(execute=True):
        n = email_of(queue(user))
    with django_capture_on_commit_callbacks(execute=True):
        relay_batch()
    assert len(mail.outbox) == 1
    event = OutboxEvent.objects.get(event_type=delivery.EVENT)
    OutboxEvent.objects.filter(pk=event.pk).update(status="pending", published_at=None)
    with django_capture_on_commit_callbacks(execute=True):
        relay_batch()  # the broker redelivers / the relay publishes again
    send_notification.apply(args=[str(n.pk)])
    send_notification.apply(args=[str(n.pk)])
    assert len(mail.outbox) == 1


def test_worker_killed_mid_send_is_recovered_with_the_same_message_id(user: Any) -> None:
    """Exit criterion: a worker dying after claiming the row neither loses the email nor creates
    a different message - the resend carries the same Message-ID."""
    n = email_of(queue(user))
    killed = mock.patch.object(delivery.EmailMultiAlternatives, "send", side_effect=SystemExit)
    with killed, pytest.raises(SystemExit):
        delivery.deliver(n.pk)
    n.refresh_from_db()
    assert n.status == NotificationStatus.SENDING and mail.outbox == []
    assert delivery.deliver(n.pk) == "skipped"  # claimed: nobody else sends it meanwhile
    Notification.objects.filter(pk=n.pk).update(updated_at=now() - timedelta(minutes=20))
    assert send_due() == 0  # re-queued (not a scheduled row), picked up by the retrying task
    n.refresh_from_db()
    assert n.status == NotificationStatus.QUEUED
    assert delivery.deliver(n.pk) == NotificationStatus.SENT
    assert [m.extra_headers["Message-ID"] for m in mail.outbox] == [f"<{n.pk}@mhrs.local>"]


@pytest.mark.parametrize("case", ["inactive", "unverified", "suppressed", "withdrawn"])
def test_suppression_rules(case: str) -> None:
    """EC-NOT-01 / EC-NOT-04 / EC-ACC-07; "withdrawn" also covers the notification part of
    EC-REV-07 (withdrawn after the decision, before the message goes out -> suppressed)."""
    user = UserFactory(verified=case != "unverified")
    context: dict[str, Any] = {}
    key = "shortlisted"
    if case == "inactive":
        user.is_active = False
        user.save(update_fields=["is_active"])
    if case == "suppressed":
        EmailSuppression.objects.create(email=user.email.upper(), reason="bounce", at=now())
    if case == "withdrawn":
        app = make_application(user=user, status=Status.SUBMITTED)
        type(app).objects.unscoped().filter(pk=app.pk).update(status=Status.WITHDRAWN)
        context = {"application_id": str(app.pk)}
    n = email_of(queue(user, key=key, context=context))
    with mock.patch.object(delivery, "now", return_value=DAYTIME):
        assert delivery.deliver(n.pk) == NotificationStatus.SUPPRESSED
    n.refresh_from_db()
    assert mail.outbox == [] and n.last_error


def test_withdrawal_confirmation_still_reaches_a_withdrawn_applicant(user: Any) -> None:
    app = make_application(user=user, status=Status.SUBMITTED)
    type(app).objects.unscoped().filter(pk=app.pk).update(status=Status.WITHDRAWN)
    n = email_of(
        queue(
            user, key="application_withdrawn_confirmation", context={"application_id": str(app.pk)}
        )
    )
    assert delivery.deliver(n.pk) == NotificationStatus.SENT


def test_quiet_hours_defer_non_urgent_candidate_email_until_morning(user: Any) -> None:
    """EC-NOT-09: 20:00-07:00 in the candidate's timezone; urgent messages go at once."""
    later = email_of(queue(user, key="shortlisted", dedupe="s"))
    urgent = email_of(queue(user, key="application_received", dedupe="r"))
    with mock.patch.object(delivery, "now", return_value=NIGHT):
        assert delivery.deliver(later.pk) == "deferred"
        assert delivery.deliver(urgent.pk) == NotificationStatus.SENT
    later.refresh_from_db()
    assert later.status == NotificationStatus.QUEUED
    assert later.scheduled_for == datetime(2026, 11, 11, 5, 0, tzinfo=UTC)  # 07:00 Harare
    assert len(mail.outbox) == 1
    with mock.patch.object(
        delivery, "now", return_value=later.scheduled_for + timedelta(minutes=1)
    ):
        assert send_due() == 1  # eager task delivers it
    assert len(mail.outbox) == 2
    staff = email_of(
        queue(
            UserFactory(),
            key="recruiter_digest",
            dedupe="d",
            context={
                "new_applications": "3",
                "processing_done": "2",
                "dashboard_url": "https://x.test/hr",
            },
        )
    )
    with mock.patch.object(delivery, "now", return_value=NIGHT):
        assert delivery.deliver(staff.pk) == NotificationStatus.SENT  # staff mail is not held


def test_provider_outage_requeues_then_dead_letters_after_retries(user: Any) -> None:
    """EC-NOT-02: a provider failure keeps the row queued for the retrying task (backoff for
    about 24 h); when retries are exhausted a dead letter is written and the row is failed."""
    n = email_of(queue(user))
    outage = mock.patch.object(
        delivery.EmailMultiAlternatives, "send", side_effect=OSError("smtp down")
    )
    with outage, pytest.raises(delivery.DeliveryError):
        delivery.deliver(n.pk)
    n.refresh_from_db()
    assert n.status == NotificationStatus.QUEUED and "smtp down" in n.last_error
    assert send_notification.autoretry_for == (delivery.DeliveryError,)
    assert send_notification.max_retries == 13 and send_notification.retry_backoff_max == 4 * 3600
    backoff = sum(min(60 * 2**i, 4 * 3600) for i in range(13))
    assert backoff >= 24 * 3600  # keeps trying for at least a day
    send_notification.on_failure(
        delivery.DeliveryError("smtp down"), "task-1", [str(n.pk)], {}, None
    )
    n.refresh_from_db()
    assert n.status == NotificationStatus.FAILED
    assert DeadLetter.objects.filter(
        task_name="apps.notifications.tasks.send_notification"
    ).exists()
    assert delivery.deliver(n.pk) == "skipped"  # a failed row is not resent by a late task


def test_org_override_is_used_and_unrenderable_override_falls_back() -> None:
    team = make_org_with_team()
    user = UserFactory()
    services.save_template(
        team.org,
        actor=team.hr_manager,
        key="application_received",
        subject="Acme got it",
        body_md="Thanks {{ recipient_name }}. Ref {{ reference }}.",
    )
    n = email_of(queue(user, organisation=team.org))
    assert delivery.deliver(n.pk) == NotificationStatus.SENT
    assert mail.outbox[0].subject == "Acme got it"
    services.save_template(
        team.org,
        actor=team.hr_manager,
        key="not_selected",
        subject="Update",
        body_md="See {{ portal_url }} and {{ job_title }}",
    )
    with transaction.atomic():
        rows = delivery.notify(
            user,
            "not_selected",
            {"organisation_name": "Acme", "job_title": "Dev"},
            dedupe_key="ns",
            organisation=team.org,
        )
    with mock.patch.object(delivery, "now", return_value=DAYTIME):
        assert delivery.deliver(email_of(rows).pk) == NotificationStatus.SENT


def test_ec_not_06_emails_do_not_invite_replies_and_point_to_portal_messages(user: Any) -> None:
    """EC-NOT-06: sent from the no-reply address with no Reply-To; auto-responders are told not
    to answer; the footer says replies are not read and links to the portal messages."""
    n = email_of(queue(user))
    assert delivery.deliver(n.pk) == NotificationStatus.SENT
    msg = mail.outbox[0]
    assert msg.reply_to == [] and "Reply-To" not in msg.extra_headers
    assert "no-reply@" in msg.from_email
    assert msg.extra_headers["Auto-Submitted"] == "auto-generated"
    assert msg.extra_headers["X-Auto-Response-Suppress"] == "All"
    assert "Replies to this address are not read" in msg.body
    assert "Sign in to read and send messages: http://localhost:3000" in msg.body
    assert 'href="http://localhost:3000"' in msg.alternatives[0][0]
