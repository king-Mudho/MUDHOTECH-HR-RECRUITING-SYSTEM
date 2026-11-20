# Handover – MUDHOTECH HR RECRUITING SYSTEM (v1.2)

Owner: **MudhoTech Solutions (Pvt) Ltd**, Harare, Zimbabwe. This document hands the system over for
operation. It contains **no secrets**: it lists who owns each credential, never its value.

## 1. System overview

A multi-tenant applicant tracking system with explainable, human-controlled AI screening:
organisations publish vacancies; candidates apply with CVs and answers; workers read CVs and
evaluate them against versioned, HR-approved rubrics; people review the evidence, decide shortlists,
interview, make offers and record hires. v1.1 adds interviews, offers, talent pools, reports and
billing; v1.2 adds integrations and Shona/Ndebele scaffolding.

| Area | Where |
|---|---|
| Requirements, architecture, data model | `docs/01_SRS.md`, `docs/02_ARCHITECTURE.md`, `docs/architecture/ERD.md` |
| API | `backend/schema.yml`, `/api/docs/`, `docs/integrations/public-api.md` |
| AI engine & governance | `docs/05_AI_ENGINE.md`, `docs/ai-governance/` |
| Security & privacy | `docs/06_SECURITY_PRIVACY_COMPLIANCE.md`, `docs/security/ASVS_CHECKLIST.md`, `docs/dpia/` |
| Deployment & operations | `docs/10_DEPLOYMENT_OPERATIONS.md`, `docs/deployment/`, `docs/runbooks/` |
| Decisions | `docs/11_DECISIONS_LOG.md` (ADRs and open owner decisions) |
| User guides | `docs/user-guides/` (candidate, recruiter, HR manager, org admin, platform admin, auditor, FAQ) |
| Developers | `docs/DEVELOPER_ONBOARDING.md`, `CLAUDE.md`, `backend/CLAUDE.md`, `frontend/CLAUDE.md` |

## 2. Credentials and accounts (ownership only)

| Credential / account | Owner | Stored in |
|---|---|---|
| AWS account (EC2, RDS, S3, SES, CloudWatch, SSM) | MudhoTech director (root) + ops IAM users | AWS; MFA on root |
| Domain + DNS (D-09) | MudhoTech | Registrar |
| TLS certificates | Automatic (Certbot) | Server |
| Django `SECRET_KEY`, `FIELD_ENCRYPTION_KEYS` | Ops lead | SSM Parameter Store |
| Database credentials | Ops lead | SSM |
| GitHub repository, environments, `GHCR_READ_TOKEN` | MudhoTech GitHub org owners | GitHub / SSM |
| Paynow integration id/key (USD, ZWG) | Finance lead | SSM (`PAYNOW_*`) |
| Google / Microsoft OAuth apps | IT lead | SSM (`GOOGLE_OAUTH_*`, `MICROSOFT_OAUTH_*`) |
| SMS aggregator key, WhatsApp token/app secret | Customer success lead | Organisation connections / SSM |
| Sentry DSN | Ops lead | SSM |
| Platform admin accounts | Named MudhoTech staff with MFA | MHRS |

Rotate on staff change and after any incident: `docs/runbooks/rotate-keys.md`,
`docs/runbooks/credential-compromise.md`.

## 3. Operational calendar

| When | What |
|---|---|
| Continuously | Outbox relay, interview reminders (5 min), payment polling and webhook retries (1 min), ops metrics |
| Daily | Retention run (01:30), usage roll-up, analytics snapshot, invoices (05:00), dunning (06:00), talent pool reminders, override alerts (07:00), export expiry |
| Weekly | Retention dry-run report, AI drift report (Mon 03:00), logical database backup + restore check |
| Monthly | Review dead letters and failing integrations, access review of platform admins, dependency updates |
| Quarterly | Restore drill, AI quality report per organisation, key rotation, ASVS re-check |
| Yearly | DPIA review, model card review, penetration test |

## 4. Support

| Level | Who | How |
|---|---|---|
| Candidates | Employer first; platform support for account issues | Support email (`SUPPORT_EMAIL`) |
| Organisations | MudhoTech customer success | Support email; break-glass access only with a reason |
| Incidents | On-call ops | Runbooks; data incidents follow `incident-data-leak.md` (POTRAZ timelines with counsel, D-08) |

## 5. Known limitations

- Live Paynow, OAuth (calendar/SSO), SMS and WhatsApp need the owner's provider accounts; until then
  they run in sandbox mode.
- Shona/Ndebele catalogues are partial machine drafts applied client-side; server-rendered text stays
  English.
- AI bands are calibrated on synthetic data; real-world calibration needs HR-labelled applications.
- Browser journeys cover every module locally and in the nightly; a live Paynow payment is tested
  through the API only until the owner's Paynow account exists.
- See `docs/BACKLOG.md` for technical follow-ups.

## 6. Go-live (owner actions)

Complete `docs/deployment/GO_LIVE_CHECKLIST.md`: AWS set-up, domain, GitHub environments, legal items
(D-08), staging rehearsal, backup drill, then tag the release. Remaining phase items needing the owner:
Phase 10 exit (green nightly), Phase 11 T09/T12/exit, Phase 16 sign-off.

## 7. Roadmap

Post-release ideas and follow-ups: `docs/BACKLOG.md`.
