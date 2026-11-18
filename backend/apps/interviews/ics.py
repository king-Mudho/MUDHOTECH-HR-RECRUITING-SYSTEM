"""iCalendar (RFC 5545) for interview invitations (P12-T02, EC-INT-02).

Times are written in the zone the interview was arranged in (``DTSTART;TZID=Africa/Harare:...``)
with a ``VTIMEZONE`` describing that zone's offset on the interview date, plus ``DTSTAMP`` in UTC.
``UID`` is stable per interview and ``SEQUENCE`` increases on every reschedule/cancel, so calendars
update the same event instead of adding a second one. A cancelled interview is sent as
``METHOD:CANCEL`` / ``STATUS:CANCELLED``. No personal data beyond what the candidate already knows
is included (no scores, no panel names).
"""

from __future__ import annotations

from datetime import datetime

from django.conf import settings

from apps.core import time as mhrs_time

from .models import Interview, InterviewMode, InterviewStatus
from .scheduling import zone

PRODID = "-//MudhoTech Solutions//MUDHOTECH HR RECRUITING SYSTEM//EN"


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Lines longer than 75 octets continue on the next line after CRLF + space (RFC 5545 3.1)."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts: list[str] = []
    current = b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(current) + len(b) > (75 if not parts else 74):
            parts.append(current.decode("utf-8"))
            current = b""
        current += b
    parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


def _local(dt: datetime, tz_name: str) -> str:
    return dt.astimezone(zone(tz_name)).strftime("%Y%m%dT%H%M%S")


def _offset(dt: datetime, tz_name: str) -> str:
    return dt.astimezone(zone(tz_name)).strftime("%z")


def interview_ics(interview: Interview) -> str:
    if interview.starts_at is None or interview.ends_at is None:
        raise ValueError("Only interviews with a time have a calendar entry.")
    app = interview.application
    tz = interview.timezone
    cancelled = interview.status == InterviewStatus.CANCELLED
    summary = f"{interview.stage}: {app.job.title} ({app.organisation.name})"
    where = (
        interview.location
        if interview.mode == InterviewMode.IN_PERSON
        else (
            "Video call - link in your account"
            if interview.mode == InterviewMode.VIDEO
            else "Phone call"
        )
    )
    url = f"{settings.FRONTEND_URL}/candidate/applications/{app.pk}#interviews"
    description = (
        f"{interview.stage} for {app.job.title} with {app.organisation.name}.\nDetails: {url}"
    )
    if interview.instructions:
        description += f"\n\n{interview.instructions}"
    offset = _offset(interview.starts_at, tz)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        f"METHOD:{'CANCEL' if cancelled else 'REQUEST'}",
        "BEGIN:VTIMEZONE",
        f"TZID:{tz}",
        "BEGIN:STANDARD",
        f"DTSTART:{_local(interview.starts_at, tz)}",
        f"TZOFFSETFROM:{offset}",
        f"TZOFFSETTO:{offset}",
        f"TZNAME:{interview.starts_at.astimezone(zone(tz)).tzname() or tz}",
        "END:STANDARD",
        "END:VTIMEZONE",
        "BEGIN:VEVENT",
        f"UID:interview-{interview.pk}@mhrs",
        f"SEQUENCE:{interview.sequence}",
        f"DTSTAMP:{mhrs_time.now().astimezone(zone('UTC')).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART;TZID={tz}:{_local(interview.starts_at, tz)}",
        f"DTEND;TZID={tz}:{_local(interview.ends_at, tz)}",
        f"SUMMARY:{_escape(summary)}",
        f"LOCATION:{_escape(where)}",
        f"DESCRIPTION:{_escape(description)}",
        f"URL:{url}",
        f"STATUS:{'CANCELLED' if cancelled else 'CONFIRMED'}",
        "TRANSP:OPAQUE",
    ]
    if not cancelled:
        lines += [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            "DESCRIPTION:Interview reminder",
            "TRIGGER:-PT1H",
            "END:VALARM",
        ]
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
