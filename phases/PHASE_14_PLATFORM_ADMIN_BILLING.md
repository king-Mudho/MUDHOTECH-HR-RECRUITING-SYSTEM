# PHASE 14 — Platform Administration, Subscriptions & Billing

**Release:** v1.1 · **Modules:** M20 · **Depends on:** Phase 13
**Read first:** `docs/01 M20`, `docs/03 billing`, `docs/07 K`, ADR-015, D-13

> STOP condition: live Paynow integration ID/key are owner-supplied. Build and test against Paynow's test mode / mocks.

## Tasks
- [ ] **P14-T01** — Admin console completion: `/admin/dashboard` (tenants, active vacancies, applications/day, queue health, error rates), organisations detail (members, usage, plan, verification docs), users search (platform scope, minimal PII), feature flags UI, taxonomy curation UI (skills, aliases, relations, qualification mappings; publish new taxonomy version), dead-letter viewer with retry, queues view, system health.
- [ ] **P14-T02** — `apps.billing` models: Plan (limits jsonb: active_vacancies, seats, ai_evaluations_month, storage_gb), Subscription, UsageCounter, Invoice, Payment; seed plans per D-13 (editable).
- [ ] **P14-T03** — Entitlements service `billing.entitlements.check(org, metric)` enforced at: publish job, invite member, run screening, upload storage; never blocks candidates applying to already-published jobs (EC-BIL-03); trial (30 days) flow.
- [ ] **P14-T04** — Usage metering (increment in services via outbox consumers), monthly roll-up, usage page for org_admin.
- [ ] **P14-T05** — Invoicing: monthly invoice generation (USD or ZWG with price snapshot (EC-BIL-05)), PDF invoice (MudhoTech Solutions (Pvt) Ltd details, configurable tax/VAT fields), email.
- [ ] **P14-T06** — Paynow integration (official Python SDK or REST): web checkout (cards) + mobile express checkout (EcoCash/OneMoney); result URL handler with hash verification (EC-BIL-01), server-side polling of poll_url with backoff (EC-BIL-02), idempotent payment application, receipts; manual payment recording by platform admin (bank transfer).
- [ ] **P14-T07** — Dunning & lifecycle: reminders before due, grace 7 days, `past_due` → staff read-only, public jobs remain visible until their deadline (EC-BIL-04), reactivation on payment.
- [ ] **P14-T08** — Org billing UI `/hr/settings/billing` (plan, usage, invoices, pay now, change plan) and admin plan management.
- [ ] **P14-T09** — Tests incl. mocked Paynow callbacks (valid/invalid hash, duplicates, pending→paid, failed).

## Exit criteria
- [ ] Trial → paid via Paynow test mode works end to end; entitlements enforced; candidate flows never blocked by billing.
