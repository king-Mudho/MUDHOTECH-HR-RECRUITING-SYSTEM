# PHASE 02 — Identity, Tenancy & Access Control

**Release:** MVP · **Modules:** M01, M02, M03, M22 (audit base) · **Depends on:** Phase 01
**Read first:** `docs/01_SRS.md §2, M01–M03`, `docs/03 accounts/organisations/audit`, `docs/04 Auth & Organisations`, `docs/06 §2`, `docs/07 A–B`

## Goal
Users can register/verify/login (MFA for privileged roles), create organisations, invite teams with roles, switch
orgs; every request is tenant-scoped and authorised server-side; all sensitive actions are audited.

## Tasks
- [x] **P02-T01** — Custom `User` model (email login, citext, normalisation) **before first migrate of auth**; Argon2 hasher; password validators incl. breached-password list (bundled top-100k hashed list); `UserSessionMeta`.
- [x] **P02-T02** — django-allauth headless (browser client): signup, email verification (mandatory before application submit), login, logout, password reset/change, email change with re-verification + notice to old address; generic responses (no enumeration); custom email templates branded MHRS.
- [x] **P02-T03** — MFA via `allauth.mfa`: TOTP + recovery codes; enforcement middleware: users with platform role or membership role in {org_admin, hr_manager} must have MFA (7-day grace with banner, then blocked from staff APIs with `mfa_required`).
- [x] **P02-T04** — Rate limiting & lockout: DRF throttles + django-axes (or custom) progressive lockout; notify user on lockout. Session list/revoke endpoints `/me/sessions`.
- [x] **P02-T05** — `apps.audit`: `AuditEvent` append-only with hash chain (`prev_hash`, `hash` = sha256 of canonical JSON + prev), service `audit.record(actor, action, target, before, after, reason, request)`; DB trigger preventing UPDATE/DELETE; `AccessLog` for PII views; verify-chain management command.
- [x] **P02-T06** — `apps.organisations` models: Organisation, OrganisationPolicy (defaults per `docs/03`), Department, Location, Membership, Invitation (hashed tokens). Services: create_org (creator becomes org_admin, status pending_verification), update, invite (email via outbox), accept (email match rule EC-ORG-05), revoke, resend, change_role, deactivate_member (sessions revoked, reassignment needed list), last-admin guard.
- [x] **P02-T07** — Org context: `OrganisationContextMiddleware` resolving `request.organisation` + `request.membership` from `X-Org-Id` validated against active membership (or session active org); `/me/active-org`; suspended org handling (`org_suspended` 423 for writes, read-only staff).
- [x] **P02-T08** — RBAC: permission classes `HasOrgRole(*roles)`, `IsAssignedToJob` (stub interface for Phase 3), `IsPlatformAdmin`, `IsCandidateOwner`; central `permissions/matrix.py` declaring role × action; conflict-of-interest hook (EC-ACC-09/10) interface.
- [x] **P02-T09** — APIs per `docs/04` (me, organisations, policies, departments, locations, members, invitations, public company profile) with OpenAPI annotations.
- [x] **P02-T10** — Platform admin basics: platform_role on user; `/platform/organisations` list/verify/suspend/reactivate (audited); seed command creates platform admin from env.
- [x] **P02-T11** — Tests: permission matrix (parametrised), **cross-tenant suite scaffold** (`tests/tenancy/`) that later phases extend automatically by registering endpoints, invitation flows, last-admin, MFA enforcement, lockout, audit chain integrity.
- [x] **P02-T12** — Frontend auth: `/register`, `/login` (+MFA step), `/verify-email`, `/forgot-password`, `/reset-password`, account settings (password, email, MFA setup with QR + recovery codes, sessions). Auth context from `/me`; route guards per group (middleware redirect for unauthenticated; role-based UI gating — server remains source of truth).
- [x] **P02-T13** — Frontend org: employer sign-up flow (`/employers` → create organisation), HR settings pages: organisation profile (logo upload placeholder until Phase 4 uploader → use simple direct upload), departments, locations, team (invite, role change, deactivate), policies; org switcher; invitation accept page.
- [ ] **P02-T14** — Admin UI: `/admin/organisations` list + verify/suspend actions.

## Edge cases
EC-ACC-01..08, EC-ACC-11, EC-ACC-12, EC-ORG-01..09 (EC-ORG-09 reassignment list completed in Phase 03 once jobs exist).

## Exit criteria
- [ ] Candidate and staff journeys work end to end in browser (manual + Playwright smoke).
- [ ] Permission matrix + cross-tenant tests green; no endpoint without explicit permission class (test asserts all registered views declare permissions).
- [ ] MFA enforced for privileged roles; audit chain verifies.
- [ ] Listed EC ids have tests.

## Verification
`pytest apps/accounts apps/organisations apps/audit tests/tenancy tests/permissions -q` · `npx playwright test e2e/auth.spec.ts`
