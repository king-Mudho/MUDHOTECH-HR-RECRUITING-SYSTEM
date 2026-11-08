"""Server-authoritative time (EC-OPS-06).

All business logic (deadlines, expiries, SLAs) must call :func:`now` - never trust client clocks and
never call ``datetime.now()`` directly. Hosts run NTP (chrony); this single seam also makes time
controllable in tests.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone


def now() -> datetime:
    """Return the current timezone-aware UTC datetime from the server clock."""
    return timezone.now()


def display_tz() -> ZoneInfo:
    return ZoneInfo(settings.DISPLAY_TIME_ZONE)


def to_tz(value: datetime, tz_name: str | None = None) -> datetime:
    """Convert an aware datetime to the given IANA zone (default: display zone, Africa/Harare)."""
    if timezone.is_naive(value):
        raise ValueError("Naive datetimes are not allowed; store and pass aware UTC datetimes.")
    return value.astimezone(ZoneInfo(tz_name) if tz_name else display_tz())
