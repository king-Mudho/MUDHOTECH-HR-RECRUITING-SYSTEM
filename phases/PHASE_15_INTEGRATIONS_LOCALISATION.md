# PHASE 15 — External Integrations & Localisation

**Release:** v1.2 · **Modules:** M21, NFR-I18N · **Depends on:** Phase 14
**Read first:** `docs/01 M21`, `docs/03 integrations`, D-14

> STOP condition: provider accounts (Google/Microsoft OAuth apps, SMS aggregator, WhatsApp Business) need owner setup.
> Build adapters with mocks + sandbox modes; document setup steps.

## Tasks
- [x] **P15-T01** — `apps.integrations` framework: provider registry, encrypted credentials per org, health status, credential rotation, integration audit; failures never affect core records (outbox-driven) (M21 AC).
- [x] **P15-T02** — Calendar sync: Google Calendar & Microsoft 365 (OAuth per staff user) — create/update/cancel interview events, free/busy check for panel conflicts.
- [x] **P15-T03** — Staff SSO: Google / Microsoft via allauth socialaccount, org domain restriction, MFA policy interplay.
- [x] **P15-T04** — SMS (local aggregator adapter, D-14) and WhatsApp Business Cloud API adapter: explicit opt-in consent (purpose `sms`/`whatsapp`), approved templates only, STOP/opt-out handling, delivery receipts, cost metering → usage counters.
- [x] **P15-T05** — Outbound webhooks: org-configured endpoints, event subscription (application.submitted, status_changed, shortlist.approved, offer.accepted, job.published), HMAC-SHA256 signatures + timestamp, retries with backoff, delivery log UI, replay.
- [x] **P15-T06** — Public API v1 (API keys, scoped: `jobs:read`, `applications:read`), rate limited, documented OpenAPI subset; job syndication XML feed (Indeed-style) and JSON feed per org.
- [x] **P15-T07** — Localisation: externalise all strings (lint for hard-coded text), add `sn` (Shona) and `nd` (Ndebele) message catalogues scaffolded (machine draft clearly marked for human translator review), locale switcher, email templates per locale.
- [x] **P15-T08** — Tests: webhook signature verification sample code in docs; consent enforcement for SMS/WA; integration failure isolation.

## Exit criteria
- [x] Each integration works in sandbox/mocked mode with docs in `docs/integrations/*.md`; failures isolated.

## Exit evidence (2026-11-19)
- Sandbox/mocked: `apps/integrations/tests` - framework (encrypted write-only credentials, health,
  rotation, audit, tenant isolation), calendar sync (create/update/cancel, free/busy warnings),
  SMS/WhatsApp (opt-in, templates, STOP over SMS and signed WhatsApp webhook, receipts, metering),
  webhooks (signature, once-only, retries -> failed, replay, minimal payload, SSRF guard), public API
  (scopes, revocation, forged keys) and feeds; SSO rules in `apps/accounts/tests/test_sso.py`;
  `frontend/tests/{integrations,i18n}.test.tsx`.
- Failures isolated: calendar and SMS provider errors leave the interview and the email copy
  untouched and are recorded on the connection; webhooks and messaging run from the outbox after
  commit.
- Docs: `docs/integrations/{README,calendar,sso,sms-whatsapp,webhooks,public-api,localisation}.md`
  (owner setup steps; webhook signature verification code in Python and Node).
- Full backend suite 3058 passed, 2 skipped on a fresh database (24 min 43 s); CI run 44604411745 on 3f1058a green (backend, frontend, infrastructure, API contract, images); frontend 196 tests and production build pass.
