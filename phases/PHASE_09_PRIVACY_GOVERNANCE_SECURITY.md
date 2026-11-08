# PHASE 09 — Privacy, Governance & Security Hardening

**Release:** MVP · **Modules:** M22, security baseline · **Depends on:** Phase 08
**Read first:** `docs/06_SECURITY_PRIVACY_COMPLIANCE.md` (all), `docs/03 privacy/platform`, `docs/07 I`

## Goal
Make the MVP compliant-by-design and hardened: rights workflows, retention/anonymisation, legal holds, consent
management, break-glass support access, AI governance artefacts, security headers, scanning and DPIA.

## Tasks
- [ ] **P09-T01** — `apps.privacy` models: ConsentRecord (versioned notices), RightsRequest, RetentionRun, LegalHold; privacy notice versioning per org (shown at application start; stored on submit) (EC-PRV-09).
- [ ] **P09-T02** — Rights requests: candidate `/candidate/privacy` (consents, request access/export, correction, deletion, objection, consent withdrawal); re-auth + email confirmation; routing to org(s) & platform; SLA due dates & reminders; staff handling UI `/hr/settings/privacy`.
- [ ] **P09-T03** — Export bundle generator (reports queue): JSON (profile, applications, answers, claims, evaluations summary, messages, consents, decisions) + human-readable PDF + original documents ZIP; expiring link 24 h; audit (EC-PRV-03).
- [ ] **P09-T04** — Deletion/anonymisation service: replace PII with tokens, delete S3 objects (all versions), keep minimal audit (ids, actions), cascade rules, legal-hold check (EC-PRV-01/02/05), account deletion (EC-ACC-13).
- [ ] **P09-T05** — Retention engine (beat daily): per-org `retention_months` after vacancy close for non-hired applications; dry-run weekly report to org_admin; run records; idempotent.
- [ ] **P09-T06** — Break-glass support access: request (reason, ≤ 4 h), platform approval, scoped middleware allowing read access, banner + tenant-visible log, auto-expiry (EC-PRV-07).
- [ ] **P09-T07** — Evaluate & (if acceptable overhead < 10% on key queries) implement PostgreSQL RLS policies on major tenant tables using `SET LOCAL app.current_org` in middleware/transaction (ADR-012); document result.
- [ ] **P09-T08** — Security headers (Django + Next.js middleware: CSP with nonces for Next scripts, HSTS, etc.), cookie settings audit, CORS locked, Django admin gated (`ENABLE_DJANGO_ADMIN`), export formula-injection escaping util used everywhere (EC-PRV-08).
- [ ] **P09-T09** — Security tooling in CI: bandit, semgrep (django/react rulesets), pip-audit, npm audit (high+ fails), detect-secrets, Trivy on images; OWASP ZAP baseline against staging-like compose in nightly.
- [ ] **P09-T10** — Manual security checklist `docs/security/ASVS_CHECKLIST.md` (L2 items relevant) completed with evidence links; fix all findings.
- [ ] **P09-T11** — AI governance: `/admin/model-registry` UI, `docs/ai-governance/MODEL_CARD_screening_engine.md`, `docs/ai-governance/AI_POLICY.md`, candidate-facing `/how-we-use-ai` finalised, AI kill-switch per org and platform (feature flags) with test that disabling AI routes all applications to manual review (`docs/runbooks/disable-ai.md`).
- [ ] **P09-T12** — DPIA `docs/dpia/DPIA.md` (processing description, necessity, risks, mitigations, residual risk, sign-off section for owner/counsel) and DPA template `docs/legal/DPA_TEMPLATE.md` (controller=employer, processor=MudhoTech) — marked "for legal review" (D-08).
- [ ] **P09-T13** — Accessibility pass on candidate + HR core journeys: axe zero serious/critical, keyboard walkthrough, NVDA spot check notes in `docs/accessibility/AUDIT.md`.

## Edge cases
EC-PRV-01..10, EC-ACC-13, EC-ORG-10.

## Exit criteria
- [ ] Rights request lifecycle E2E (export + deletion) passes; deleted candidate leaves no PII in DB/S3 (verification script).
- [ ] No high/critical findings from security tooling; ASVS checklist complete.
- [ ] DPIA, DPA template, model card, AI policy written.
- [ ] AI kill-switch verified.
