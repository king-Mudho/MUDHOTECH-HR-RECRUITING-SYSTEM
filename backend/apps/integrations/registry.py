"""Integration providers (P15-T01). Each provider names its adapter, whether it is connected per
organisation or per staff member, and the credential fields it needs (validated on connect)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Provider:
    key: str
    name: str
    kind: str  # calendar | messaging
    adapter: str  # dotted path of the adapter class
    per_user: bool = False
    credential_fields: tuple[str, ...] = ()
    config_fields: tuple[str, ...] = ()
    docs: str = ""
    extra: dict[str, str] = field(default_factory=dict)


PROVIDERS: dict[str, Provider] = {
    p.key: p
    for p in (
        Provider(
            "google_calendar",
            "Google Calendar",
            "calendar",
            "apps.integrations.adapters.calendar.GoogleCalendarAdapter",
            per_user=True,
            credential_fields=("refresh_token",),
            docs="docs/integrations/calendar.md",
        ),
        Provider(
            "microsoft_calendar",
            "Microsoft 365 Calendar",
            "calendar",
            "apps.integrations.adapters.calendar.MicrosoftCalendarAdapter",
            per_user=True,
            credential_fields=("refresh_token",),
            docs="docs/integrations/calendar.md",
        ),
        Provider(
            "sms",
            "SMS (local aggregator)",
            "messaging",
            "apps.integrations.adapters.messaging.SmsAggregatorAdapter",
            credential_fields=("api_key",),
            config_fields=("sender_id",),
            docs="docs/integrations/sms-whatsapp.md",
        ),
        Provider(
            "whatsapp",
            "WhatsApp Business (Cloud API)",
            "messaging",
            "apps.integrations.adapters.messaging.WhatsAppCloudAdapter",
            credential_fields=("access_token",),
            config_fields=("phone_number_id",),
            docs="docs/integrations/sms-whatsapp.md",
        ),
    )
}


def get(key: str) -> Provider:
    try:
        return PROVIDERS[key]
    except KeyError as exc:
        raise KeyError(f"Unknown provider {key!r}") from exc
