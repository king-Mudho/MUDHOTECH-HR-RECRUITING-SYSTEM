"""Calendar sync (P15-T02).

* ``sync_interview`` (outbox consumer of ``interview.changed``) - for every panelist who connected
  a calendar: create or update the interview event while it is scheduled, cancel it when the
  interview is cancelled or no longer has a time. Event details carry no candidate personal data
  beyond the application reference: the job, stage, time, mode/location and a link to the
  interview page.
* ``external_busy`` - busy times from connected calendars for the panel conflict warning
  (EC-INT-01 stays a warning; a failing calendar just adds nothing).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from django.conf import settings
from django.db import transaction

from apps.core.models import OutboxEvent
from apps.core.outbox import idempotent_consumer

from . import services
from .adapters.calendar import CalendarAdapter
from .models import CalendarEventLink


def _cal(adapter: Any) -> CalendarAdapter:
    return cast(CalendarAdapter, adapter)


def _event(interview: Any) -> dict[str, Any]:
    app = interview.application
    where = interview.location or (
        "Video call (link in MHRS)" if interview.mode == "video" else interview.get_mode_display()
    )
    return {
        "uid": str(interview.pk),
        "title": f"Interview: {app.job.title} ({interview.stage}) - {app.reference}",
        "description": (
            f"{interview.stage} interview for {app.job.title}, application {app.reference}.\n"
            f"Details and scorecard: {settings.FRONTEND_URL}/hr/interviews/{interview.pk}"
        ),
        "location": where,
        "start": interview.starts_at.isoformat(),
        "end": interview.ends_at.isoformat(),
        "timezone": interview.timezone,
    }


def sync_interview(interview_id: Any) -> dict[str, int]:
    from apps.interviews.models import Interview, InterviewStatus

    out = {"upserted": 0, "cancelled": 0, "failed": 0}
    iv = (
        Interview.objects.unscoped()  # outbox consumer: system context
        .select_related("application__job")
        .filter(pk=interview_id)
        .first()
    )
    if iv is None:
        return out
    user_ids = list(iv.panelists.values_list("membership__user_id", flat=True))
    live = iv.status == InterviewStatus.SCHEDULED and iv.starts_at and iv.ends_at
    for conn in services.user_connections(iv.organisation_id, user_ids, "calendar"):
        link = CalendarEventLink.objects.unscoped().filter(interview=iv, connection=conn).first()
        if live:
            event = _event(iv)
            existing = link.external_id if link else ""

            def upsert(adapter: Any, e: dict[str, Any] = event, ext: str = existing) -> str:
                return _cal(adapter).upsert_event(e, ext)

            external = services.call(conn, upsert)
            if external is None:
                out["failed"] += 1
                continue
            with transaction.atomic():
                CalendarEventLink.objects.unscoped().update_or_create(
                    interview=iv,
                    connection=conn,
                    defaults={
                        "organisation_id": iv.organisation_id,
                        "external_id": str(external),
                        "synced_sequence": iv.sequence,
                        "cancelled": False,
                    },
                )
            out["upserted"] += 1
        elif link is not None and not link.cancelled:

            def cancel(adapter: Any, ext: str = link.external_id) -> bool:
                _cal(adapter).cancel_event(ext)
                return True

            done = services.call(conn, cancel)
            if done is None:
                out["failed"] += 1
                continue
            CalendarEventLink.objects.unscoped().filter(pk=link.pk).update(
                cancelled=True, synced_sequence=iv.sequence
            )
            out["cancelled"] += 1
    return out


@idempotent_consumer("integrations.calendar_sync", events=["interview.changed"])
def on_interview_changed(event: OutboxEvent) -> None:
    sync_interview(event.payload.get("interview_id"))


def external_busy(memberships: list[Any], start: datetime, end: datetime) -> list[dict[str, Any]]:
    if not memberships:
        return []
    by_user = {m.user_id: m for m in memberships}
    out: list[dict[str, Any]] = []
    for conn in services.user_connections(
        memberships[0].organisation_id, list(by_user), "calendar"
    ):
        busy = services.call(conn, lambda adapter: _cal(adapter).busy(start, end)) or []
        member = by_user.get(conn.owner_user_id)
        for s, e in busy:
            out.append(
                {
                    "membership_id": str(member.pk) if member else "",
                    "interview_id": None,
                    "starts_at": s,
                    "ends_at": e,
                    "source": conn.provider,
                }
            )
    return out
