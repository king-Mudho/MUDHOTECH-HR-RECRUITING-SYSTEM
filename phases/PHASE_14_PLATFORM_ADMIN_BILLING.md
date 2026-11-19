# PHASE 14 — Platform Administration, Subscriptions & Billing

**Release:** v1.1 · **Modules:** M20 · **Depends on:** Phase 13
**Read first:** `docs/01 M20`, `docs/03 billing`, `docs/07 K`, ADR-015, D-13

> STOP condition: live Paynow integration ID/key are owner-supplied. Build and test against Paynow's test mode / mocks.

## Tasks
- [x] **P14-T01** — Admin console completion: `/admin/dashboard` (tenants, active vacancies, applications/day, queue health, error rates), organisations detail (members, usage, plan, verification docs), users search (platform scope, minimal PII), feature flags UI, taxonomy curation UI (skills, aliases, relations, qualification mappings; publish new taxonomy version), dead-letter viewer with retry, queues view, system health.
- [x] **P14-T02** — `apps.billing` models: Plan (limits jsonb: active_vacancies, seats, ai_evaluations_month, storage_gb), Subscription, UsageCounter, Invoice, Payment; seed plans per D-13 (editable).
- [x] **P14-T03** — Entitlements service `billing.entitlements.check(org, metric)` enforced at: publish job, invite member, run screening, upload storage; never blocks candidates applying to already-published jobs (EC-BIL-03); trial (30 days) flow.
- [x] **P14-T04** — Usage metering (increment in services via outbox consumers), monthly roll-up, usage page for org_admin.
- [x] **P14-T05** — Invoicing: monthly invoice generation (USD or ZWG with price snapshot (EC-BIL-05)), PDF invoice (MudhoTech Solutions (Pvt) Ltd details, configurable tax/VAT fields), email.
- [x] **P14-T06** — Paynow integration (official Python SDK or REST): web checkout (cards) + mobile express checkout (EcoCash/OneMoney); result URL handler with hash verification (EC-BIL-01), server-side polling of poll_url with backoff (EC-BIL-02), idempotent payment application, receipts; manual payment recording by platform admin (bank transfer).
- [x] **P14-T07** — Dunning & lifecycle: reminders before due, grace 7 days, `past_due` → staff read-only, public jobs remain visible until their deadline (EC-BIL-04), reactivation on payment.
- [x] **P14-T08** — Org billing UI `/hr/settings/billing` (plan, usage, invoices, pay now, change plan) and admin plan management.
- [x] **P14-T09** — Tests incl. mocked Paynow callbacks (valid/invalid hash, duplicates, pending→paid, failed).

## Exit criteria
- [x] Trial → paid via Paynow test mode works end to end; entitlements enforced; candidate flows never blocked by billing.

## Exit evidence (2026-11-19)
- Trial -> paid: `backend/tests/integration/test_phase14_billing.py` - trial limits block a third
  vacancy, trial end -> 7-day grace -> read-only (candidate still submits), Growth chosen, EcoCash
  payment through Paynow (test double speaking Paynow's signed protocol; result URL hash verified
  and confirmed by poll) -> subscription active, higher limit applies.
- Paynow behaviour: `apps/billing/tests/test_payments.py` (valid/invalid hash, duplicates,
  pending -> paid, failed, cancelled, spoofed/replayed callbacks, amount mismatch, 15-minute
  polling window -> manual check, not configured, manual bank payments).
- Entitlements: `test_entitlements.py` (publish/schedule/resume, seats, screening runs, staff
  uploads; candidate submissions at the limit and while read-only succeed).
- Full backend suite 2985 passed, 2 skipped on a fresh database; CI green (run 44598967647 on 4e5de83, after fixing an evening-only core-scenario test and a Bandit B310 finding).
- Live Paynow test mode needs the owner's integration id/key (STOP condition) - the protocol is
  implemented against Paynow's documented fields; run one sandbox payment once keys exist.
