# Changelog

All notable changes to the MUDHOTECH HR RECRUITING SYSTEM are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

## [1.2.0] - release candidate (dated when the tag is pushed after owner sign-off)

### Added
- Phase 15 integrations: Google/Microsoft 365 calendar sync for interviews; staff single sign-on
  (no sign-up via SSO, organisation domain allow-list, MFA still enforced); opt-in SMS and WhatsApp
  updates with STOP handling; signed outbound webhooks with SSRF guard; scoped, hashed read-only API
  keys and job feeds; Shona and Ndebele draft catalogues with a language switcher.
- Phase 16: generated ERD, updated architecture diagrams, developer onboarding, platform admin and
  auditor guides, FAQ, video outlines, handover and backlog; v1.1/v1.2 security re-review and
  penetration test readiness pack; indexes for reports, AI allowance and delivery receipts.
- Phase 14 platform administration & billing: platform console (dashboard, organisations, users,
  feature flags, taxonomy curation and publishing, dead letters, system health, plans & pricing);
  subscriptions with a 30-day trial and plan limits that never block candidates; usage metering;
  monthly invoices (USD/ZWG, tax fields, PDF); Paynow payments (EcoCash, OneMoney, cards) with
  verified callbacks; manual bank payments; reminders, grace period and read-only mode with
  reactivation on payment; plan & billing page for organisation admins.
- Phase 13 talent pool, analytics & exports: consent-based talent pool per employer (opt-in at
  application end or on the privacy page, reconfirmation, expiry, leave/delete) with HR talent
  search and invitations; recruitment reports (time to review/shortlist/hire, funnel conversion,
  sources, completion, CV processing quality, AI-human agreement, clarifications) with nightly
  snapshots; permissioned CSV/XLSX/PDF exports with a blind option and 15-minute links; AI
  quality monitoring (override alerts, drift indicators).
- Phase 12 interviews, offers & hiring: interview scheduling with candidate self-booking, calendar
  files, reminders, panel conflict warnings and no-show handling; independent scorecards with a
  consolidated view; offers with approval chain, PDF letter, electronic acceptance, expiry and
  withdrawal; hire records, vacancy close prompt and confirmed close-out messages; HR interview and
  offer pages; candidate interview booking and offer response; dashboard funnel through hires.

## [1.0.0] - release candidate (the date is set when the tag is pushed after the go-live checklist)
Pilot release: production deployment and operations on AWS. See `docs/releases/v1.0.0.md`.

### Added
- Phase 11 production deployment & operations: multi-stage, pinned, non-root production images with
  healthchecks, resource limits and SBOMs; production compose; nginx site for staging and production
  (TLS 1.2/1.3, HSTS preload, rate limits, operator allow-list, JSON access logs) with Certbot automation;
  EC2 bootstrap for Ubuntu 24.04; AWS setup guide; `deploy.sh` with zero-downtime rolling restarts,
  smoke tests and automatic rollback (rehearsed in CI); staging and production pipelines (production
  promotes the staging-tested images after approval); weekly logical backups with a verified restore
  script and runbook; operational metrics, host checks and CloudWatch alarm definitions; all operations
  runbooks; `rotate_field_keys` for encryption-key rotation; dead-letter retry/resolve in the admin;
  staging profile with Mailpit and staging E2E + ZAP checks; go-live checklist; HR onboarding material
  and pilot support process.
- Phase 10 quality, AI validation & pilot readiness: extraction/screening/calibration benchmarks and the
  AI validation report; fairness benchmark (1,095 perturbations, no result changed); load, throughput and
  resilience tests (Locust) with the performance report; Playwright journeys on desktop and phone with
  axe; UAT scripts; user guides with screenshots; bug bash (defect log D-001…D-020).
- Phase 09 privacy, governance & security hardening: data-subject rights requests with export bundles,
  erasure with legal holds and erasure verification, retention engine, break-glass support access,
  PostgreSQL row-level security, security headers and CSP, nightly security scanning, ASVS L2 checklist,
  AI kill-switch with model registry UI, model card and AI policy, DPIA and DPA template (for legal
  review), accessibility pass, organisation closure, public privacy notice, terms and accessibility pages.

### Changed
- The API runs on gunicorn with threaded WSGI workers and a per-process PostgreSQL connection pool
  (ADR-029); the cache degrades to misses when Redis is unavailable; work lost with a killed worker is
  recovered automatically.
- Sentry events carry the release (image tag) and environment.
- Minimum password length is now 12 characters.
- The Django admin is only mounted when `ENABLE_DJANGO_ADMIN` is set (on in development).

### Fixed
- Phone layout of the HR review workspace (evidence no longer covers the claim actions, D-016).

## [0.9.0-mvp] - 2026-11-17
MVP feature-complete.

### Added
- Phase 01 foundation: repository hygiene files (`.gitignore`, `.gitattributes`, `.editorconfig`, licence, changelog).
- Phase 02 identity, tenancy & access control: email accounts with verification, MFA, lockout and sessions; append-only
  audit; organisations, teams, invitations, RBAC and org context; HR settings and platform admin UI.
- Phase 03 vacancies & job board: skills/qualification taxonomy; job versions, criteria, rubrics and screening
  questionnaires with a protected-topic linter; approval and publish lifecycle with readiness checklist, scheduling and
  auto-close; HR job wizard and overview; public job board (search, job pages with JSON-LD/Open Graph, company pages,
  sitemap, RSS/JSON feeds); `seed_demo` demo data.
- Phase 04 candidate portal & applications: candidate profile and CV library; secure document uploads (presigned
  upload, type and content checks, antivirus, quarantine); application drafts, idempotent submission with references and
  receipts, withdrawal and lifecycle; consent and AI-notice records; staff-assisted applications; the 5-step apply
  wizard; read-only HR application list and detail.
- Phase 05 ATS, notifications & messaging: versioned notification templates with an HR editor; reliable
  deduplicated email and in-app delivery (suppression, quiet hours, retries, bounce handling); notification
  bell and centre; clarification requests and per-application message threads; HR pipeline board with
  validated, reason-coded status changes, notes, tags and assignment; candidate to-do list.
- Phase 06 CV extraction (AI part 1): synthetic CV corpus with gold labels; sandboxed PDF/DOCX text
  extraction with hidden-text detection, OCR fallback and quality/language checks; sections, dates and
  experience totals; evidence-linked claims (experience, education, certifications, skills, languages,
  projects) with qualification levels and job titles normalised; protected details excluded and masked;
  prompt-injection detection; local embeddings for semantic skill matching; encrypted extraction runs
  with outbox orchestration and safe failure handling; duplicate-file and name-mismatch flags; candidate
  "What we extracted" view, import to profile and corrections; HR extraction panel with retry;
  extraction benchmark with a nightly job.
- Phase 07 matching, scoring & explanations (AI part 2): evidence-based criterion matching (rules,
  skill aliases/relations/semantic, experience relevance, screening answers, knock-outs, conflicts);
  category scores with coverage, essentials, confidence and review bands (no reject band; missing
  evidence is unknown, never a fail); grounded explanations with citations and clarification
  suggestions; optional guarded LLM phrasing (off by default); versioned evaluations with evidence
  links, screening runs and re-evaluation with reasons, human claim verification, vacancy score
  distribution with coverage and saturation warnings; model registry and AI quality counters; HR
  screening page and evaluation panel labelled "AI-assisted suggestion — requires human review";
  screening benchmark (recall, grounding, determinism, counterfactual fairness) with a nightly job.
- Phase 08 shortlist review, HR dashboard & audit UI (MVP feature-complete): accountable shortlists with
  human decisions, structured reasons, override tracking, dual-control approval and an undo window before
  candidates are told; server-side blind review with audited identity reveal; applicants table with filters,
  saved views and bulk actions; review page with highlighted CV evidence and evaluation versions; compare
  view; conflict-of-interest rules; HR dashboard separating AI suggestions from human decisions; audit trail
  with safe export; decision reconstruction (JSON and PDF); access logging of every view of candidate data;
  end-to-end core scenario (100 applicants to an approved shortlist of ten).
