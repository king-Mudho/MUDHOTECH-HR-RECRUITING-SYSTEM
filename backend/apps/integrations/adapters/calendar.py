"""Calendar adapters (P15-T02): Google Calendar and Microsoft 365 (Graph), per staff member.

Both use the staff member's OAuth refresh token (stored encrypted on the connection) to obtain a
short-lived access token, then create/update/cancel the interview event and read free/busy for
panel conflict checks. OAuth client ids/secrets are platform settings supplied by the owner;
sandbox mode answers locally.
"""

from __future__ import annotations

import urllib.parse
from datetime import datetime
from typing import Any

from django.conf import settings

from .base import BaseAdapter, IntegrationError


class CalendarAdapter(BaseAdapter):
    token_url = ""
    events_url = ""

    def access_token(self) -> str:
        if self.sandbox:
            return "sandbox-token"
        reply = self.form_post(
            self.token_url,
            {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": str(self.credentials.get("refresh_token", "")),
                "grant_type": "refresh_token",
            },
        )
        token = reply.get("access_token")
        if not token:
            raise IntegrationError(f"{self.connection.provider}: token refresh failed")
        return str(token)

    def form_post(self, url: str, fields: dict[str, str]) -> dict[str, Any]:
        import json
        import urllib.error
        import urllib.request

        req = urllib.request.Request(  # noqa: S310 - fixed https provider endpoints
            url,
            data=urllib.parse.urlencode(fields).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310  # nosec B310 - fixed https endpoints
                return dict(json.loads(resp.read().decode() or "{}"))
        except (urllib.error.URLError, ValueError) as exc:
            raise IntegrationError(f"{self.connection.provider}: token endpoint error") from exc

    @property
    def client_id(self) -> str:
        return str(settings.CALENDAR_OAUTH.get(self.connection.provider, {}).get("client_id", ""))

    @property
    def client_secret(self) -> str:
        conf = settings.CALENDAR_OAUTH.get(self.connection.provider, {})
        return str(conf.get("client_secret", ""))

    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token()}"}

    # implemented per provider
    def event_body(self, event: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

    def upsert_event(self, event: dict[str, Any], external_id: str = "") -> str:
        body = self.event_body(event)
        if external_id:
            reply = self.request(
                "PATCH",
                f"{self.events_url}/{external_id}",
                body=body,
                headers=self.auth(),
                sandbox_reply={"id": external_id},
            )
        else:
            reply = self.request(
                "POST",
                self.events_url,
                body=body,
                headers=self.auth(),
                sandbox_reply={"id": f"sandbox-{event['uid']}"},
            )
        return str(reply.get("id", external_id))

    def cancel_event(self, external_id: str) -> None:
        self.request(
            "DELETE", f"{self.events_url}/{external_id}", headers=self.auth(), sandbox_reply={}
        )

    def busy(self, start: datetime, end: datetime) -> list[tuple[str, str]]:  # pragma: no cover
        raise NotImplementedError

    def ping(self) -> dict[str, Any]:
        self.access_token()
        return {"ok": True}


class GoogleCalendarAdapter(CalendarAdapter):
    token_url = "https://oauth2.googleapis.com/token"  # noqa: S105 - an endpoint, not a secret
    events_url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

    def event_body(self, event: dict[str, Any]) -> dict[str, Any]:
        return {
            "summary": event["title"],
            "description": event.get("description", ""),
            "location": event.get("location", ""),
            "start": {"dateTime": event["start"], "timeZone": event["timezone"]},
            "end": {"dateTime": event["end"], "timeZone": event["timezone"]},
            "iCalUID": f"{event['uid']}@mhrs",
        }

    def busy(self, start: datetime, end: datetime) -> list[tuple[str, str]]:
        reply = self.request(
            "POST",
            "https://www.googleapis.com/calendar/v3/freeBusy",
            body={
                "timeMin": start.isoformat(),
                "timeMax": end.isoformat(),
                "items": [{"id": "primary"}],
            },
            headers=self.auth(),
            sandbox_reply={"calendars": {"primary": {"busy": []}}},
        )
        slots = reply.get("calendars", {}).get("primary", {}).get("busy", [])
        return [(b["start"], b["end"]) for b in slots]


class MicrosoftCalendarAdapter(CalendarAdapter):
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"  # noqa: S105
    events_url = "https://graph.microsoft.com/v1.0/me/events"

    def event_body(self, event: dict[str, Any]) -> dict[str, Any]:
        return {
            "subject": event["title"],
            "body": {"contentType": "text", "content": event.get("description", "")},
            "location": {"displayName": event.get("location", "")},
            "start": {"dateTime": event["start"], "timeZone": event["timezone"]},
            "end": {"dateTime": event["end"], "timeZone": event["timezone"]},
            "transactionId": event["uid"],
        }

    def busy(self, start: datetime, end: datetime) -> list[tuple[str, str]]:
        reply = self.request(
            "GET",
            "https://graph.microsoft.com/v1.0/me/calendarView?"
            + urllib.parse.urlencode(
                {"startDateTime": start.isoformat(), "endDateTime": end.isoformat()}
            ),
            headers=self.auth(),
            sandbox_reply={"value": []},
        )
        return [
            (e["start"]["dateTime"], e["end"]["dateTime"])
            for e in reply.get("value", [])
            if e.get("showAs", "busy") != "free"
        ]
