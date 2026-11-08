# PHASE 15 — External Integrations & Localisation

**Release:** v1.2 · **Modules:** M21, NFR-I18N · **Depends on:** Phase 14
**Read first:** `docs/01 M21`, `docs/03 integrations`, D-14

> STOP condition: provider accounts (Google/Microsoft OAuth apps, SMS aggregator, WhatsApp Business) need owner setup.
> Build adapters with mocks + sandbox modes; document setup steps.

## Tasks
- [ ] **P15-T01** — `apps.integrations` framework: provider registry, encrypted credentials per org, health status, credential rotation, integration audit; failures never affect core records (outbox-driven) (M21 AC).
- [ ] **P15-T02** — Calendar sync: Google Calendar & Microsoft 365 (OAuth per staff user) — create/update/cancel interview events, free/busy check for panel conflicts.
- [ ] **P15-T03** — Staff SSO: Google / Microsoft via allauth socialaccount, org domain restriction, MFA policy interplay.
- [ ] **P15-T04** — SMS (local aggregator adapter, D-14) and WhatsApp Business Cloud API adapter: explicit opt-in consent (purpose `sms`/`whatsapp`), approved templates only, STOP/opt-out handling, delivery receipts, cost metering → usage counters.
- [ ] **P15-T05** — Outbound webhooks: org-configured endpoints, event subscription (application.submitted, status_changed, shortlist.approved, offer.accepted, job.published), HMAC-SHA256 signatures + timestamp, retries with backoff, delivery log UI, replay.
- [ ] **P15-T06** — Public API v1 (API keys, scoped: `jobs:read`, `applications:read`), rate limited, documented OpenAPI subset; job syndication XML feed (Indeed-style) and JSON feed per org.
- [ ] **P15-T07** — Localisation: externalise all strings (lint for hard-coded text), add `sn` (Shona) and `nd` (Ndebele) message catalogues scaffolded (machine draft clearly marked for human translator review), locale switcher, email templates per locale.
- [ ] **P15-T08** — Tests: webhook signature verification sample code in docs; consent enforcement for SMS/WA; integration failure isolation.

## Exit criteria
- [ ] Each integration works in sandbox/mocked mode with docs in `docs/integrations/*.md`; failures isolated.
