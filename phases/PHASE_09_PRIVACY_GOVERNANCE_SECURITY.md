# PHASE 09 — Privacy, Governance & Security Hardening

**Release:** MVP · **Modules:** M22, security baseline · **Depends on:** Phase 08
**Read first:** `docs/06_SECURITY_PRIVACY_COMPLIANCE.md` (all), `docs/03 privacy/platform`, `docs/07 I`

## Goal
Make the MVP compliant-by-design and hardened: rights workflows, retention/anonymisation, legal holds, consent
management, break-glass support access, AI governance artefacts, security headers, scanning and DPIA.

## Tasks
- [x] **P09-T01** — `apps.privacy` models: ConsentRecord (versioned notices), RightsRequest, RetentionRun, LegalHold; privacy notice versioning per org (shown at application start; stored on submit) (EC-PRV-09).
- [x] **P09-T02** — Rights requests: candidate `/candidate/privacy` (consents, request access/export, correction, deletion, objection, consent withdrawal); re-auth + email confirmation; routing to org(s) & platform; SLA due dates & reminders; staff handling UI `/hr/settings/privacy`.
- [x] **P09-T03** — Export bundle generator (reports queue): JSON (profile, applications, answers, claims, evaluations summary, messages, consents, decisions) + human-readable PDF + original documents ZIP; expiring link 24 h; audit (EC-PRV-03).
- [x] **P09-T04** — Deletion/anonymisation service: replace PII with tokens, delete S3 objects (all versions), keep minimal audit (ids, actions), cascade rules, legal-hold check (EC-PRV-01/02/05), account deletion (EC-ACC-13).
- [x] **P09-T05** — Retention engine (beat daily): per-org `retention_months` after vacancy close for non-hired applications; dry-run weekly report to org_admin; run records; idempotent.
- [x] **P09-T06** — Break-glass support access: request (reason, ≤ 4 h), platform approval, scoped middleware allowing read access, banner + tenant-visible log, auto-expiry (EC-PRV-07).
- [x] **P09-T07** — Evaluate & (if acceptable overhead < 10% on key queries) implement PostgreSQL RLS policies on major tenant tables using `SET LOCAL app.current_org` in middleware/transaction (ADR-012); document result.
- [x] **P09-T08** — Security headers (Django + Next.js middleware: CSP with nonces for Next scripts, HSTS, etc.), cookie settings audit, CORS locked, Django admin gated (`ENABLE_DJANGO_ADMIN`), export formula-injection escaping util used everywhere (EC-PRV-08).
- [x] **P09-T09** — Security tooling in CI: bandit, semgrep (django/react rulesets), pip-audit, npm audit (high+ fails), detect-secrets, Trivy on images; OWASP ZAP baseline against staging-like compose in nightly.
- [x] **P09-T10** — Manual security checklist `docs/security/ASVS_CHECKLIST.md` (L2 items relevant) completed with evidence links; fix all findings.
- [x] **P09-T11** — AI governance: `/admin/model-registry` UI, `docs/ai-governance/MODEL_CARD_screening_engine.md`, `docs/ai-governance/AI_POLICY.md`, candidate-facing `/how-we-use-ai` finalised, AI kill-switch per org and platform (feature flags) with test that disabling AI routes all applications to manual review (`docs/runbooks/disable-ai.md`).
- [x] **P09-T12** — DPIA `docs/dpia/DPIA.md` (processing description, necessity, risks, mitigations, residual risk, sign-off section for owner/counsel) and DPA template `docs/legal/DPA_TEMPLATE.md` (controller=employer, processor=MudhoTech) — marked "for legal review" (D-08).
- [x] **P09-T13** — Accessibility pass on candidate + HR core journeys: axe zero serious/critical, keyboard walkthrough, NVDA spot check notes in `docs/accessibility/AUDIT.md`.

## Edge cases
EC-PRV-01..10, EC-ACC-13, EC-ORG-10.

## Exit criteria
- [x] Rights request lifecycle E2E (export + deletion) passes; deleted candidate leaves no PII in DB/S3 (verification script).
- [x] No high/critical findings from security tooling; ASVS checklist complete.
- [x] DPIA, DPA template, model card, AI policy written.
- [x] AI kill-switch verified.

## Exit evidence (2026-11-17)
- Rights lifecycle: `apps/privacy/tests/test_lifecycle.py` drives the API end to end - export request
  (password re-auth, email-token confirmation, bundle built on the reports queue, 24 h download, staff
  completion), organisation-scoped deletion (erases the employer's records and files) and account
  deletion by a platform admin; `verify_erasure` then finds no former identifier in the database and the
  CV object is gone from storage. Unit coverage in `test_export.py`, `test_erasure.py` (legal holds,
  `verify_erasure` failing when PII remains), `test_retention.py`.
- Security tooling (2026-11-17): bandit 0 medium/high, pip-audit 0, npm audit 0 high/critical (one
  moderate dev-tooling advisory, recorded), detect-secrets 0 new; nightly adds semgrep, Trivy (fs +
  images, fail on HIGH/CRITICAL) and the ZAP baseline. ASVS L2 checklist complete with evidence per item
  (`docs/security/ASVS_CHECKLIST.md`, findings F1-F10).
- Documents: `docs/dpia/DPIA.md`, `docs/legal/DPA_TEMPLATE.md` (both for legal review, D-08),
  `docs/ai-governance/MODEL_CARD_screening_engine.md`, `docs/ai-governance/AI_POLICY.md`,
  `docs/runbooks/disable-ai.md`, `docs/accessibility/AUDIT.md`.
- AI kill-switch: `apps/screening/tests/test_killswitch.py` - with the platform flag, an organisation
  override or the organisation policy off, evaluation is skipped and the application reaches
  `under_review` in `manual_review_requested` with no score or AI text; LLM summaries and criteria
  suggestions are off; API and `ai_switch` command require a platform admin and a reason, audited.
- Edge cases: `scripts/ec_coverage.py --phase 09` 12/12 (EC-ORG-10 close flow, EC-PRV-05, EC-PRV-10 added
  at close).
- Full backend suite on a fresh CI-like database: 2,448 passed (the RLS overhead check and the core
  scenario's clarification-email count were made robust during the close); Vitest 160 passed.

