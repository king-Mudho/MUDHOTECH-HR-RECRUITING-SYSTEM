# Integrations (Phase 15)

| Integration | Doc | Needs from the owner |
|---|---|---|
| Calendar sync (Google, Microsoft 365) | [calendar.md](calendar.md) | OAuth apps (client id/secret) |
| Staff SSO (Google, Microsoft) | [sso.md](sso.md) | Same OAuth apps |
| SMS / WhatsApp | [sms-whatsapp.md](sms-whatsapp.md) | Aggregator account (D-14), Meta WhatsApp Business + approved templates |
| Outbound webhooks | [webhooks.md](webhooks.md) | Nothing |
| Public API & job feeds | [public-api.md](public-api.md) | Nothing |
| Languages (Shona, Ndebele) | [localisation.md](localisation.md) | Human translators |

## Principles

- **Failures are isolated**: integration work runs from the transactional outbox after the business
  change is saved; a failing provider is recorded on the connection (health, last error, audit) and
  never changes or blocks core records.
- **Credentials** are encrypted at rest, write-only through the API (only a masked hint is shown) and
  can be rotated; every connect, rotation and disconnect is audited.
- **Sandbox mode** (`INTEGRATIONS_SANDBOX`, on by default except in production): adapters make no
  network calls and return simulated replies, so every flow works in development and tests.
- **Data minimisation**: webhooks and API keys never carry candidate contact details or documents.
