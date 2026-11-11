# PROGRESS.md — MUDHOTECH HR RECRUITING SYSTEM

> **Single source of truth for implementation progress.** Every agent session: read this after `CLAUDE.md`,
> work on the **Current task**, then update this file (tick tasks, update pointers, append to the session log).
> Task details live in the phase files; keep both in sync.

## Current pointer
- **Current phase:** 05 — ATS Workflow, Notifications & Messaging
- **Current task:** P05-T09
- **Last updated:** 2026-11-11
- **Overall:** 69 / 193 tasks · 4 / 16 phases

## Phase status
| # | Phase | Release | Tasks | Status | Closed on |
|---|---|---|---|---|---|
| 01 | [Foundation & Development Environment](phases/PHASE_01_FOUNDATION.md) | MVP | 17 | ✅ Done | 2026-11-08 |
| 02 | [Identity, Tenancy & Access Control](phases/PHASE_02_IDENTITY_TENANCY_ACCESS.md) | MVP | 14 | ✅ Done | 2026-11-09 |
| 03 | [Vacancy Management, Taxonomy & Public Job Board](phases/PHASE_03_VACANCIES_JOB_BOARD.md) | MVP | 14 | ✅ Done | 2026-11-10 |
| 04 | [Candidate Portal, Documents, Applications & Questionnaires](phases/PHASE_04_CANDIDATE_PORTAL_APPLICATIONS.md) | MVP | 16 | ✅ Done | 2026-11-10 |
| 05 | [ATS Workflow, Notifications & Messaging](phases/PHASE_05_ATS_NOTIFICATIONS_MESSAGING.md) | MVP | 11 | 🟦 In progress | |
| 06 | [Document Ingestion & CV Extraction (AI Part 1)](phases/PHASE_06_CV_EXTRACTION.md) | MVP | 15 | ⬜ Not started | |
| 07 | [Matching, Scoring & Explainable Evaluation (AI Part 2)](phases/PHASE_07_MATCHING_SCORING_EXPLANATIONS.md) | MVP | 15 | ⬜ Not started | |
| 08 | [Shortlist Review, HR Dashboard & Audit UI  (→ MVP feature-complete)](phases/PHASE_08_SHORTLIST_DASHBOARD_AUDIT.md) | MVP | 13 | ⬜ Not started | |
| 09 | [Privacy, Governance & Security Hardening](phases/PHASE_09_PRIVACY_GOVERNANCE_SECURITY.md) | MVP | 13 | ⬜ Not started | |
| 10 | [Quality Assurance, AI Validation & Pilot Readiness](phases/PHASE_10_QA_AI_VALIDATION_PILOT.md) | MVP | 10 | ⬜ Not started | |
| 11 | [Production Deployment & Operations (→ v1.0 pilot live)](phases/PHASE_11_PRODUCTION_DEPLOYMENT.md) | MVP | 12 | ⬜ Not started | |
| 12 | [Interviews, Offers & Hiring](phases/PHASE_12_INTERVIEWS_OFFERS_HIRING.md) | v1.1 | 10 | ⬜ Not started | |
| 13 | [Consent-Based Talent Pool, Advanced Analytics & Exports](phases/PHASE_13_TALENT_POOL_ANALYTICS.md) | v1.1 | 8 | ⬜ Not started | |
| 14 | [Platform Administration, Subscriptions & Billing](phases/PHASE_14_PLATFORM_ADMIN_BILLING.md) | v1.1 | 9 | ⬜ Not started | |
| 15 | [External Integrations & Localisation](phases/PHASE_15_INTEGRATIONS_LOCALISATION.md) | v1.2 | 8 | ⬜ Not started | |
| 16 | [Final Hardening, Documentation & Release (Project complete)](phases/PHASE_16_FINAL_HARDENING_RELEASE.md) | v1.2 final | 8 | ⬜ Not started | |

Status legend: ⬜ Not started · 🟦 In progress · ✅ Done · ⛔ Blocked

## Milestones
- [ ] **M1 — MVP feature-complete** (Phase 08 closed) → tag `v0.9.0-mvp`
- [ ] **M2 — Pilot validated** (Phase 10 closed; go-live gates passed)
- [ ] **M3 — v1.0 live** (Phase 11 closed) → tag `v1.0.0`
- [ ] **M4 — v1.1** (Phase 14 closed) → tag `v1.1.0`
- [ ] **M5 — v1.2 / project complete** (Phase 16 closed) → tag `v1.2.0`

## Blockers & owner decisions pending
| ID | Item | Needed by | Status |
|---|---|---|---|
| D-08 | Legal review: CDPA / SI 155 of 2024 obligations, POTRAZ registration/licensing, DPO, DPA template | Phase 11 go-live | Open (default: counsel review before go-live) |
| D-07/D-09/D-10 | AWS region, production domain, SES | Phase 11 | Open (defaults in docs/11) |
| D-13 | Plan pricing | Phase 14 | Open (placeholder prices) |
| D-14 | SMS aggregator / WhatsApp BSP | Phase 15 | Open |

## Task checklist (mirror of phase files)

### Phase 01 — Foundation & Development Environment  (`phases/PHASE_01_FOUNDATION.md`)
- [x] P01-T01 — Initialise git repo (if not already), `.gitignore` (Python, Node, env, media, .DS_Store, `*.docx~`), …
- [x] P01-T02 — Verify current stable versions (Django LTS, DRF, Celery, Next.js, Node LTS, PostgreSQL, pgvector image) via official …
- [x] P01-T03 — Backend scaffold: `backend/pyproject.toml` (uv), `config/` with split settings (`base/dev/test/staging/prod`), …
- [x] P01-T04 — `apps.core`: `BaseModel` (UUID pk, timestamps), `TenantModel` + `TenantQuerySet.for_org()` + strict unscoped guard …
- [x] P01-T05 — `apps.core.outbox`: `OutboxEvent`, `ProcessedEvent` models, `emit(event_type, aggregate, payload, dedupe_key)` (must …
- [x] P01-T06 — `apps.core.idempotency`: `IdempotencyKey` model + DRF mixin/decorator `@idempotent(endpoint="…")` storing response
- [x] P01-T07 — Health endpoints `/healthz` and `/readyz` (DB, Redis, S3 checks with timeouts)
- [x] P01-T08 — Storage service `apps.core.storage` (django-storages/boto3): buckets per purpose, `presign_put`, …
- [x] P01-T09 — Field encryption utility (`EncryptedTextField` using Fernet MultiFernet with key ids from `FIELD_ENCRYPTION_KEYS`)
- [x] P01-T10 — Docker: `backend/Dockerfile` (python:3.12-slim, non-root user, uv install), `backend/Dockerfile.worker` (adds …
- [x] P01-T11 — Frontend scaffold: create Next.js app (TypeScript, App Router, Tailwind, ESLint, `src/` dir) in a temp folder and …
- [x] P01-T12 — API client: `src/lib/api-client.ts` (fetch wrapper with credentials, CSRF header from cookie, error envelope parsing …
- [x] P01-T13 — Base UI shell: public header/footer with "MUDHOTECH HR RECRUITING SYSTEM" branding, HR shell (sidebar nav, top bar …
- [x] P01-T14 — Tooling: backend `ruff` + `mypy` (django-stubs, drf-stubs) + `pytest` config + `factory_boy`
- [x] P01-T15 — CI `.github/workflows/ci.yml` per `docs/09 §6` (backend lint/type/test with Postgres+Redis services
- [x] P01-T16 — Write nested memories: confirm `backend/CLAUDE.md` and `frontend/CLAUDE.md` are accurate for the scaffold produced …
- [x] P01-T17 — Smoke test: `docker compose up -d --build` from clean clone works on Windows
- [x] P01-EXIT — All exit criteria verified with evidence

### Phase 02 — Identity, Tenancy & Access Control  (`phases/PHASE_02_IDENTITY_TENANCY_ACCESS.md`)
- [x] P02-T01 — Custom `User` model (email login, citext, normalisation) before first migrate of auth
- [x] P02-T02 — django-allauth headless (browser client): signup, email verification (mandatory before application submit), login, …
- [x] P02-T03 — MFA via `allauth.mfa`: TOTP + recovery codes
- [x] P02-T04 — Rate limiting & lockout: DRF throttles + django-axes (or custom) progressive lockout
- [x] P02-T05 — `apps.audit`: `AuditEvent` append-only with hash chain (`prev_hash`, `hash` = sha256 of canonical JSON + prev), …
- [x] P02-T06 — `apps.organisations` models: Organisation, OrganisationPolicy (defaults per `docs/03`), Department, Location, …
- [x] P02-T07 — Org context: `OrganisationContextMiddleware` resolving `request.organisation` + `request.membership` from `X-Org-Id` …
- [x] P02-T08 — RBAC: permission classes `HasOrgRole(*roles)`, `IsAssignedToJob` (stub interface for Phase 3), `IsPlatformAdmin`, …
- [x] P02-T09 — APIs per `docs/04` (me, organisations, policies, departments, locations, members, invitations, public company …
- [x] P02-T10 — Platform admin basics: platform_role on user
- [x] P02-T11 — Tests: permission matrix (parametrised), cross-tenant suite scaffold (`tests/tenancy/`) that later phases extend …
- [x] P02-T12 — Frontend auth: `/register`, `/login` (+MFA step), `/verify-email`, `/forgot-password`, `/reset-password`, account …
- [x] P02-T13 — Frontend org: employer sign-up flow (`/employers` → create organisation), HR settings pages: organisation profile …
- [x] P02-T14 — Admin UI: `/admin/organisations` list + verify/suspend actions
- [x] P02-EXIT — All exit criteria verified with evidence

### Phase 03 — Vacancy Management, Taxonomy & Public Job Board  (`phases/PHASE_03_VACANCIES_JOB_BOARD.md`)
- [x] P03-T01 — `apps.taxonomy`: models (skills, aliases, relations, qualification levels/aliases, professional bodies, taxonomy …
- [x] P03-T02 — `apps.jobs` models: Job, JobVersion, JobCriterion, Rubric, JobApproval, JobAssignment, JobEvent
- [x] P03-T03 — `apps.questionnaires` models: Questionnaire, Question, QuestionOption, (QuestionResponse table created now, used in …
- [x] P03-T04 — Prohibited-question linter (`questionnaires/linter.py`): keyword/phrase lexicon (age, date of birth, religion, …
- [x] P03-T05 — Job services: create draft, update (lock), set criteria (validate essential justification), set rubric (weights = …
- [x] P03-T06 — Beat tasks: publish scheduled jobs; auto-close at `closes_at` (job TZ aware)
- [x] P03-T07 — Job assignments + `IsAssignedToJob` permission (hr_manager sees all org jobs
- [x] P03-T08 — AI assist stub (feature-flagged, default off): `POST /hr/jobs/{id}/ai-suggestions` returns criteria/question …
- [x] P03-T09 — Sanitisation: `nh3` allow-list for rich text (p, br, strong, em, ul, ol, li, h2–h4, a[href] with rel) applied …
- [x] P03-T10 — Public APIs: list with FTS + filters + sort + pagination
- [x] P03-T11 — HR APIs per `docs/04` Jobs section with OpenAPI
- [x] P03-T12 — Frontend HR: `/hr/jobs` table (status filters, search), 5-step job wizard (Details → Requirements (criteria builder …
- [x] P03-T13 — Frontend public: `/` home with search, `/jobs` (SSR, URL filters, pagination), `/jobs/[slug]` (deadline in job TZ + …
- [x] P03-T14 — Seed: `seed_demo` extended with 2 orgs and 3 published jobs (Software Developer per Blueprint Appendix A, …
- [x] P03-EXIT — All exit criteria verified with evidence

### Phase 04 — Candidate Portal, Documents, Applications & Questionnaires  (`phases/PHASE_04_CANDIDATE_PORTAL_APPLICATIONS.md`)
- [x] P04-T01 — `apps.candidates`: profile + experiences/educations/certifications/skills/languages models & CRUD APIs
- [x] P04-T02 — `apps.documents`: UploadSession + Document models
- [x] P04-T03 — Scan pipeline (documents queue): magic-byte detection (`python-magic` + custom DOCX/PDF checks), DOCX zip-bomb …
- [x] P04-T04 — Orphan cleanup beat task (upload sessions expired, objects in quarantine > 24 h) (EC-APP-08)
- [x] P04-T05 — `apps.applications` models: Application (+ reference counter table), ApplicationDocument, ApplicationStatusEvent, …
- [x] P04-T06 — Application state machine module `applications/state_machine.py` implementing all transitions from SRS §3.3 with …
- [x] P04-T07 — Draft APIs: create/resume draft, autosave PATCH with lock_version, attach documents by role, bulk upsert answers …
- [x] P04-T08 — Submit service: `@idempotent`, `atomic`, checks (email verified, job published & before deadline in job TZ, org …
- [x] P04-T09 — Withdraw service (any non-terminal state
- [x] P04-T10 — Consent records: application processing consent + AI-assisted screening notice version stored on submit
- [x] P04-T11 — Assisted application (staff creates on behalf
- [x] P04-T12 — Frontend `FileUploader` (presign → PUT with progress → complete → poll scan status
- [x] P04-T13 — Frontend candidate: `/candidate/dashboard`, `/candidate/profile` (sections + completeness), `/candidate/documents` …
- [x] P04-T14 — Frontend `/apply/[jobId]` wizard per `docs/08 §3.1`: autosave indicator, resume at last step, conditional questions …
- [x] P04-T15 — HR minimal list: `/hr/jobs/[id]/applications` basic table (status, submitted at, candidate name) + application …
- [x] P04-T16 — E2E: candidate registers → verifies (Mailpit API) → applies with CV + answers → receives receipt
- [x] P04-EXIT — All exit criteria verified with evidence

### Phase 05 — ATS Workflow, Notifications & Messaging  (`phases/PHASE_05_ATS_NOTIFICATIONS_MESSAGING.md`)
- [x] P05-T01 — `apps.notifications` models: NotificationTemplate (platform defaults + org overrides, versioned), Notification …
- [x] P05-T02 — Default templates (en): application_received, document_rejected_reupload, clarification_requested, …
- [x] P05-T03 — Delivery pipeline: outbox consumers → `send_notification` task (notifications queue) → provider backend (SMTP/SES …
- [x] P05-T04 — SES/SMTP bounce & complaint webhook endpoint (SNS signature verification) → suppression + in-app banner to update …
- [x] P05-T05 — In-app notifications API (list, unread count, mark read/all) + `NotificationBell` component with polling (30 s) or SSE
- [x] P05-T06 — `apps.messaging`: ClarificationRequest (templates + free text + optional upload, due_at), candidate answer endpoint …
- [x] P05-T07 — ATS features: notes (@mentions → in-app notification), tags, assign recruiter, reopen with reason, holds
- [x] P05-T08 — Frontend HR: pipeline kanban view per vacancy (columns = statuses
- [ ] P05-T09 — Frontend candidate: actions-needed panel (clarifications, re-uploads), clarification answer form, messages inbox per …
- [ ] P05-T10 — HR settings: template editor (markdown with variable picker, preview with sample data, version history, revert to …
- [ ] P05-T11 — No-reply auto-response doc + `Reply-To` handling decision (EC-NOT-06): emails link to portal messages
- [ ] P05-EXIT — All exit criteria verified with evidence

### Phase 06 — Document Ingestion & CV Extraction (AI Part 1)  (`phases/PHASE_06_CV_EXTRACTION.md`)
- [ ] P06-T01 — Synthetic CV corpus generator `scripts/generate_synthetic_cvs.py` (python-docx + reportlab + Pillow for scanned …
- [ ] P06-T02 — `ai_engine/contracts.py` pydantic models (DocumentText, Page, Block, ExtractedClaim, CandidateEvidence…) + …
- [ ] P06-T03 — `extraction/pdf.py` (PyMuPDF dict extraction, column-aware reading order, hidden-text detection: colour ≈ …
- [ ] P06-T04 — `extraction/ocr.py` (trigger rules, 300 DPI render, Tesseract, per-page confidence) + `extraction/quality.py` …
- [ ] P06-T05 — `extraction/sections.py` heading detection (typography + lexicon incl
- [ ] P06-T06 — `extraction/dates.py` all formats in `docs/05 §6.1`, precision flags, anomalies
- [ ] P06-T07 — `extraction/parser.py` claim extraction for experience, education, certifications/licences, skills (Aho–Corasick …
- [ ] P06-T08 — `normalisation/qualifications.py` map to qualification levels (ZIMSEC, NC/ND/HND, degrees, professional bodies, …
- [ ] P06-T09 — `extraction/pii.py` protected/irrelevant data detection (DOB/age, ZW national ID regex, passport, gender, marital, …
- [ ] P06-T10 — Embedding service (`matching/semantic.py` base): load model once per worker, batch encode, cache by hash (Redis), …
- [ ] P06-T11 — Django adapter `apps.resumes`: ExtractionRun, DocumentText (encrypted), ExtractedClaim, ClaimCorrection
- [ ] P06-T12 — Cross-application flags: same sha256 across different accounts (EC-APP-15), CV name vs account name mismatch …
- [ ] P06-T13 — Candidate features: view "What we extracted from your CV" (wizard review step + documents page), submit corrections …
- [ ] P06-T14 — HR: extraction panel on application detail (claims grouped, snippet + page, flags banner), "Retry processing" action
- [ ] P06-T15 — Benchmark harness `ai_engine/tests/benchmark/run_extraction_benchmark.py` → metrics JSON + markdown report in …
- [ ] P06-EXIT — All exit criteria verified with evidence

### Phase 07 — Matching, Scoring & Explainable Evaluation (AI Part 2)  (`phases/PHASE_07_MATCHING_SCORING_EXPLANATIONS.md`)
- [ ] P07-T01 — `matching/rules.py` deterministic checks: qualification rank vs required (equivalence + "or equivalent experience"), …
- [ ] P07-T02 — `matching/skills_match.py` cascade exact → alias → relations (`implies`, `narrower`) → semantic (threshold from …
- [ ] P07-T03 — `matching/experience_match.py` role relevance (title/responsibility similarity, HR equivalent titles) + months via …
- [ ] P07-T04 — `matching/answers.py` question scoring per rubric mode (exact/options/range/rubric_text keyword-criteria/human) 
- [ ] P07-T05 — `evaluation/scoring.py` criterion bands, category aggregation over assessable criteria, total with re-normalisation, …
- [ ] P07-T06 — `explanations/templates.py` deterministic strengths/gaps/conflicts sentences with citations
- [ ] P07-T07 — `ai_engine/llm/` provider interface + `null_adapter` (default) + `anthropic_adapter` + `openai_adapter` (behind …
- [ ] P07-T08 — `versioning.py` input_hash; determinism test (EC-AI-08)
- [ ] P07-T09 — Django `apps.screening`: ScreeningRun, Evaluation, CriterionResult, EvaluationEvidence, HumanVerification models
- [ ] P07-T10 — Screening runs API: start/retry for scope (all/pending/failed/selected) with chunking (50) and progress counts
- [ ] P07-T11 — Human verification API (`/hr/claims/{id}/verify`): confirm/correct/reject → evidence status `human_verified` → …
- [ ] P07-T12 — Vacancy-level analytics for screening: score/band distribution, low-coverage warning (EC-AI-15), high-score …
- [ ] P07-T13 — Frontend: `/hr/jobs/[id]/screening` (runs, progress bar, failures with retry, distribution chart with table …
- [ ] P07-T14 — Model registry seed entries (embedding model, rules engine version, null LLM) and `ai_quality` metrics capture hooks
- [ ] P07-T15 — Benchmark: matching & recall harness against gold labels → report `docs/reports/screening_benchmark_<date>.md`
- [ ] P07-EXIT — All exit criteria verified with evidence

### Phase 08 — Shortlist Review, HR Dashboard & Audit UI  (→ MVP feature-complete)  (`phases/PHASE_08_SHORTLIST_DASHBOARD_AUDIT.md`)
- [ ] P08-T01 — `apps.shortlisting` models: Shortlist, ShortlistEntry, DecisionReason (seed: shortlist reasons, not-selected reasons e.g
- [ ] P08-T02 — Services: create proposal (pre-fill suggestions from bands — suggestions only), set decisions (reason required for …
- [ ] P08-T03 — Override tracking: entry stores `ai_band_at_decision`, `score_at_decision`, `override` computed
- [ ] P08-T04 — Blind review mode: server-side serializer redaction (name → "Candidate #A12", email/phone/links/address hidden, …
- [ ] P08-T05 — Applicants list API & UI final: filters (band, score range, coverage, flags, essentials state, status, tags, …
- [ ] P08-T06 — Candidate review page `/hr/applications/[id]` per `docs/08 §3.3`: `EvidenceViewer` (pdf.js in sandboxed …
- [ ] P08-T07 — Compare view `/hr/compare` (≤ 4) — criteria rows × candidates, evidence snippets on hover
- [ ] P08-T08 — Shortlist builder `/hr/jobs/[id]/shortlist` per `docs/08 §3.4` incl
- [ ] P08-T09 — Role visibility: hiring manager sees shortlist only (EC-REV-09)
- [ ] P08-T10 — HR dashboard `/hr/dashboard`: KPI cards & queues per SRS M15, per-vacancy funnel, filters
- [ ] P08-T11 — Audit UI `/hr/settings/audit` (filters, export for auditors) + `GET /hr/applications/{id}/reconstruct` bundle (job …
- [ ] P08-T12 — Access logging on every candidate PII/CV view (AccessLog) with sampling disabled for auditors
- [ ] P08-T13 — E2E "Core Scenario" test: seed Software Developer job → 100 synthetic applications submitted via API → processing …
- [ ] P08-EXIT — All exit criteria verified with evidence

### Phase 09 — Privacy, Governance & Security Hardening  (`phases/PHASE_09_PRIVACY_GOVERNANCE_SECURITY.md`)
- [ ] P09-T01 — `apps.privacy` models: ConsentRecord (versioned notices), RightsRequest, RetentionRun, LegalHold
- [ ] P09-T02 — Rights requests: candidate `/candidate/privacy` (consents, request access/export, correction, deletion, objection, …
- [ ] P09-T03 — Export bundle generator (reports queue): JSON (profile, applications, answers, claims, evaluations summary, …
- [ ] P09-T04 — Deletion/anonymisation service: replace PII with tokens, delete S3 objects (all versions), keep minimal audit (ids, …
- [ ] P09-T05 — Retention engine (beat daily): per-org `retention_months` after vacancy close for non-hired applications
- [ ] P09-T06 — Break-glass support access: request (reason, ≤ 4 h), platform approval, scoped middleware allowing read access, …
- [ ] P09-T07 — Evaluate & (if acceptable overhead < 10% on key queries) implement PostgreSQL RLS policies on major tenant tables …
- [ ] P09-T08 — Security headers (Django + Next.js middleware: CSP with nonces for Next scripts, HSTS, etc.), cookie settings audit, …
- [ ] P09-T09 — Security tooling in CI: bandit, semgrep (django/react rulesets), pip-audit, npm audit (high+ fails), detect-secrets, …
- [ ] P09-T10 — Manual security checklist `docs/security/ASVS_CHECKLIST.md` (L2 items relevant) completed with evidence links
- [ ] P09-T11 — AI governance: `/admin/model-registry` UI, `docs/ai-governance/MODEL_CARD_screening_engine.md`, …
- [ ] P09-T12 — DPIA `docs/dpia/DPIA.md` (processing description, necessity, risks, mitigations, residual risk, sign-off section for …
- [ ] P09-T13 — Accessibility pass on candidate + HR core journeys: axe zero serious/critical, keyboard walkthrough, NVDA spot check …
- [ ] P09-EXIT — All exit criteria verified with evidence

### Phase 10 — Quality Assurance, AI Validation & Pilot Readiness  (`phases/PHASE_10_QA_AI_VALIDATION_PILOT.md`)
- [ ] P10-T01 — EC coverage: run `scripts/ec_coverage.py`
- [ ] P10-T02 — Full Playwright suite (desktop + mobile emulation) for: candidate apply journey, clarification, withdraw, HR job …
- [ ] P10-T03 — AI validation: expand corpus to ≥ 150 labelled CVs across 5 roles
- [ ] P10-T04 — Fairness: counterfactual suite at scale (≥ 500 perturbations), proxy-variable review (institution, location, gaps), …
- [ ] P10-T05 — Load tests (Locust): 100 and 1,000 concurrent submissions
- [ ] P10-T06 — Throughput: 100 CVs end-to-end ≤ 15 min on 4 vCPU/8 GB profile (docker resource limits) — record
- [ ] P10-T07 — Resilience/fault injection: kill workers mid-task, stop Redis during submissions, S3 errors, DB restart, duplicate …
- [ ] P10-T08 — Pilot dataset & script: `python manage.py run_pilot_benchmark` → creates vacancy, submits 100 applications, waits, …
- [ ] P10-T09 — UAT pack `docs/uat/UAT_SCRIPTS.md` for HR reviewers (step-by-step scenarios, expected results, sign-off table) and …
- [ ] P10-T10 — Bug bash & fix all P0/P1 defects; log in `docs/reports/DEFECT_LOG.md`
- [ ] P10-EXIT — All exit criteria verified with evidence

### Phase 11 — Production Deployment & Operations (→ v1.0 pilot live)  (`phases/PHASE_11_PRODUCTION_DEPLOYMENT.md`)
- [ ] P11-T01 — Production images: multi-stage, non-root, healthchecks, pinned bases, SBOM (syft) 
- [ ] P11-T02 — Nginx config per `docs/10 §5` + Certbot automation script
- [ ] P11-T03 — `infrastructure/deployment/ec2-bootstrap.sh` (Ubuntu 24.04: updates, unattended-upgrades, docker engine + compose …
- [ ] P11-T04 — `docs/deployment/AWS_SETUP.md` step-by-step: VPC/SG, EC2 + IAM instance role (S3, SES, SSM read), RDS PostgreSQL 16 …
- [ ] P11-T05 — `deploy.sh` (pull, migrate, collectstatic, rolling restart, smoke, rollback) + …
- [ ] P11-T06 — Backups: RDS automated + `backup.sh` logical dump to S3 weekly
- [ ] P11-T07 — Monitoring/alerting per `docs/10 §8`: Sentry release tracking, CloudWatch alarms, uptime checks, queue-depth …
- [ ] P11-T08 — Runbooks in `docs/runbooks/` (all listed in `docs/10 §6`)
- [ ] P11-T09 — Staging environment live with synthetic seed
- [ ] P11-T10 — Production go-live checklist `docs/deployment/GO_LIVE_CHECKLIST.md` (gates from Phase 10, D-08 legal sign-off, DNS, …
- [ ] P11-T11 — HR onboarding/training material: short walkthrough doc + recorded-script outline
- [ ] P11-T12 — Tag `v1.0.0`; CHANGELOG; release notes
- [ ] P11-EXIT — All exit criteria verified with evidence

### Phase 12 — Interviews, Offers & Hiring  (`phases/PHASE_12_INTERVIEWS_OFFERS_HIRING.md`)
- [ ] P12-T01 — `apps.interviews` models: Interview, InterviewSlot, InterviewPanelist, Scorecard (+ scorecard templates derived from …
- [ ] P12-T02 — Scheduling services: create interview (mode, stage, panel), offer slots, candidate self-booking (row-locked slots), …
- [ ] P12-T03 — Scorecards: per-criterion 1–5 with evidence notes, overall recommendation
- [ ] P12-T04 — `apps.offers`: Offer, OfferApproval, HireRecord
- [ ] P12-T05 — Hiring close-out: hire record, prompt to close vacancy when openings filled, bulk final notifications to remaining …
- [ ] P12-T06 — APIs + permission matrix + cross-tenant tests for all new endpoints
- [ ] P12-T07 — Frontend HR: `/hr/interviews` calendar/list (day/week), schedule dialog, panel management, scorecard form, …
- [ ] P12-T08 — Frontend candidate: interview invitations (book slot, add to calendar, reschedule request), offer view …
- [ ] P12-T09 — Notifications templates: interview_invitation, interview_reminder, interview_rescheduled, interview_cancelled, …
- [ ] P12-T10 — Funnel extended to interviews/offers/hires on dashboard
- [ ] P12-EXIT — All exit criteria verified with evidence

### Phase 13 — Consent-Based Talent Pool, Advanced Analytics & Exports  (`phases/PHASE_13_TALENT_POOL_ANALYTICS.md`)
- [ ] P13-T01 — `apps.talentpool`: TalentPoolEntry linked to ConsentRecord (purpose `talent_pool`, per organisation, duration …
- [ ] P13-T02 — Talent search (HR): FTS + skill/qualification filters over consented profiles only (org-scoped)
- [ ] P13-T03 — Analytics selectors/materialised views (refresh nightly + on-demand): time-to-review, time-to-shortlist, …
- [ ] P13-T04 — Optional voluntary diversity monitoring module (default OFF
- [ ] P13-T05 — Reports UI `/hr/reports` with charts (accessible, table alternatives
- [ ] P13-T06 — Exports (reports queue): XLSX (openpyxl) / CSV / PDF
- [ ] P13-T07 — AI quality monitoring: scheduled `ai_quality_reports`
- [ ] P13-T08 — Tests: consent boundaries, export permissions & escaping, analytics reconciliation against raw data
- [ ] P13-EXIT — All exit criteria verified with evidence

### Phase 14 — Platform Administration, Subscriptions & Billing  (`phases/PHASE_14_PLATFORM_ADMIN_BILLING.md`)
- [ ] P14-T01 — Admin console completion: `/admin/dashboard` (tenants, active vacancies, applications/day, queue health, error …
- [ ] P14-T02 — `apps.billing` models: Plan (limits jsonb: active_vacancies, seats, ai_evaluations_month, storage_gb), Subscription, …
- [ ] P14-T03 — Entitlements service `billing.entitlements.check(org, metric)` enforced at: publish job, invite member, run …
- [ ] P14-T04 — Usage metering (increment in services via outbox consumers), monthly roll-up, usage page for org_admin
- [ ] P14-T05 — Invoicing: monthly invoice generation (USD or ZWG with price snapshot (EC-BIL-05)), PDF invoice (MudhoTech Solutions …
- [ ] P14-T06 — Paynow integration (official Python SDK or REST): web checkout (cards) + mobile express checkout (EcoCash/OneMoney)
- [ ] P14-T07 — Dunning & lifecycle: reminders before due, grace 7 days, `past_due` → staff read-only, public jobs remain visible …
- [ ] P14-T08 — Org billing UI `/hr/settings/billing` (plan, usage, invoices, pay now, change plan) and admin plan management
- [ ] P14-T09 — Tests incl. mocked Paynow callbacks (valid/invalid hash, duplicates, pending→paid, failed)
- [ ] P14-EXIT — All exit criteria verified with evidence

### Phase 15 — External Integrations & Localisation  (`phases/PHASE_15_INTEGRATIONS_LOCALISATION.md`)
- [ ] P15-T01 — `apps.integrations` framework: provider registry, encrypted credentials per org, health status, credential rotation, …
- [ ] P15-T02 — Calendar sync: Google Calendar & Microsoft 365 (OAuth per staff user) — create/update/cancel interview events, …
- [ ] P15-T03 — Staff SSO: Google / Microsoft via allauth socialaccount, org domain restriction, MFA policy interplay
- [ ] P15-T04 — SMS (local aggregator adapter, D-14) and WhatsApp Business Cloud API adapter: explicit opt-in consent (purpose …
- [ ] P15-T05 — Outbound webhooks: org-configured endpoints, event subscription (application.submitted, status_changed, …
- [ ] P15-T06 — Public API v1 (API keys, scoped: `jobs:read`, `applications:read`), rate limited, documented OpenAPI subset
- [ ] P15-T07 — Localisation: externalise all strings (lint for hard-coded text), add `sn` (Shona) and `nd` (Ndebele) message …
- [ ] P15-T08 — Tests: webhook signature verification sample code in docs
- [ ] P15-EXIT — All exit criteria verified with evidence

### Phase 16 — Final Hardening, Documentation & Release (Project complete)  (`phases/PHASE_16_FINAL_HARDENING_RELEASE.md`)
- [ ] P16-T01 — Full regression: unit, API, E2E (all journeys incl
- [ ] P16-T02 — Security re-review: dependency updates, ASVS checklist re-run, ZAP full scan on staging, secrets rotation, IAM …
- [ ] P16-T03 — Performance tuning pass (query plans for top 20 endpoints, index review, cache headers, image sizes, bundle analysis)
- [ ] P16-T04 — Technical documentation complete: architecture (updated diagrams), API reference (OpenAPI published), DB ERD …
- [ ] P16-T05 — User documentation complete: candidate, recruiter, HR manager, org admin, platform admin, auditor guides
- [ ] P16-T06 — Clean-up: remove dead code/flags, resolve all TODO/FIXME (or ticket them in `docs/BACKLOG.md`), ensure `CLAUDE.md`, …
- [ ] P16-T07 — Final release `v1.2.0`, CHANGELOG, release notes, handover document `docs/HANDOVER.md` (system overview, credentials …
- [ ] P16-T08 — Post-release backlog `docs/BACKLOG.md` (ideas: ATS/HRIS sync connectors, assessments/tests module, video interview …
- [ ] P16-EXIT — All exit criteria verified with evidence

## Phase summaries
_(Written by `/close-phase`: what was built, deviations from spec, known limitations, follow-ups.)_

### Phase 01 — Foundation & Development Environment (closed 2026-11-08)
- **Built:** monorepo + hygiene files; Django 5.2 LTS / DRF / drf-spectacular / Celery backend with split settings; `apps.core`
  (BaseModel, TenantModel + strict unscoped-query guard, request-id middleware + JSON logs, error envelope, page/cursor
  pagination, TenantScopedViewSet, transactional outbox + relay + idempotent consumers, idempotency keys, feature flags,
  BaseTask + dead letters, health checks, S3 storage service, field encryption); minimal `accounts.User` +
  `organisations.Organisation`; Docker images + dev compose (11 services) + prod compose skeleton; Next.js 16 frontend
  (shadcn, next-intl, TanStack Query, typed API client, gen:api, area shells, state primitives, 404/500); tooling
  (ruff, mypy, pre-commit, detect-secrets, dev-up scripts, EC coverage); CI + nightly workflows.
- **Evidence:** 130 backend tests (apps/core 97% coverage), 22 Vitest + 4 Playwright/axe tests; clean clone healthy in 79 s;
  CI green on main (run 42523821127).
- **Deviations:** SeaweedFS replaces MinIO in dev (ADR-021); dev host ports 55432/6380 (ADR-022); User/Organisation pulled
  forward from Phase 02; Django admin at `/django-admin/`.
- **Known limitations / follow-ups:** host RAM pressure on the dev machine caused a Docker engine hang and a transient ENOMEM;
  ClamAV only under compose profile `full`; `gh` CLI not installed (CI checked via the public API).

### Phase 02 — Identity, Tenancy & Access Control (closed 2026-11-09)
- **Built:** complete `User` (email login, platform roles, MFA grace), Argon2 + breached-password validator; allauth headless
  (signup/verify/login/reset/email change, enumeration-free, branded emails via the outbox); TOTP MFA + recovery codes with
  privileged-role enforcement; progressive lockout, DRF throttles, session list/revoke + new-device notice; append-only,
  hash-chained audit (DB trigger) + access log; organisations, policies, departments, locations, memberships, invitations and
  services (last-admin guard, EC-ORG-01..09); org context middleware (X-Org-Id/session, violation audit, suspended 423); RBAC
  matrix + permission classes (HasOrgRole/Action, IsAssignedToJob stub, platform, candidate owner, conflict-of-interest hook);
  full org/team/me/platform APIs; logo upload; frontend auth pages, account security (MFA/sessions), auth context + route
  guards, employer sign-up, HR settings (profile, structure, team, policies), org switcher, invitation accept, admin orgs UI.
- **Evidence:** 442 backend tests (98% coverage), 61 Vitest, Playwright journeys desktop + mobile, EC 19/19, CI green.
- **Deviations:** ADR-023 email verification mandatory before login (no-enumeration signup); breached list = Django corpus
  (19,640) not top-100k; session metadata via allauth.usersessions; logo direct upload until Phase 04 uploader.
- **Found in exit verification and fixed:** pre-hydration native form submit could put passwords in the URL (all forms now
  POST); Next 16 `allowedDevOrigins`; CSRF trusted origin for 127.0.0.1; stale de-duplicated `/me` after login/verify.
- **Follow-ups:** EC-ORG-09 reassignment list filled by jobs (Phase 03); `IsAssignedToJob` checker registered in P03-T07;
  `assert_can_publish` to be called by the job publish service; dev host memory pressure (use RUNSERVER_ARGS=--noreload).

### Phase 03 — Vacancy Management, Taxonomy & Public Job Board (closed 2026-11-10)
- **Built:** skills & qualification taxonomy (700 skills, aliases, relations, 14 levels, 20 bodies; versioned loader;
  trigram autocomplete; org custom skills); jobs model (versions, criteria, rubric, approvals, assignments, events, slug
  redirects, FTS); questionnaires (types, options, earlier-only branching, scoring per type, knock-out, protected-topic
  linter + audited HR exception); job services (lock_version, readiness checklist, submit/approve/reject with dual control,
  publish/schedule/pause/resume/close/archive/extend/duplicate/new-version, JobEvent + audit + outbox); beat tasks
  (scheduled publish, auto-close, catch-up); assignments + assigned-only visibility + reassignment provider; flag-gated
  heuristic AI suggestions; nh3 sanitisation + XSS suite; public APIs (FTS list, detail, questions, company, sitemap,
  RSS/JSON feeds, 90-day closed then 410, slug redirects); HR API (31 endpoints in tenancy/matrix suites); HR UI (job table,
  5-step wizard with TipTap, autosave + 409 conflict reload, readiness sidebar, overview with lifecycle actions, team,
  versions, activity); public pages (home search, /jobs, /jobs/[slug] with JSON-LD/OG/share/viewer-local deadline,
  /companies/[slug], robots); `seed_demo`; `scripts/run_backend_host.py`, `scripts/lighthouse.sh`.
- **Evidence:** 868 backend tests, 79 Vitest, Playwright jobs journey 8/8 (desktop + mobile, axe), Lighthouse mobile
  median /jobs 89/100/100 and /jobs/[slug] 88/100/100 (perf/a11y/SEO), EC-JOB 20/20, schema + types no drift.
- **Deviations:** job approval dual control reuses `policy.rubric_dual_control`; auditors get read-only access to all org
  vacancies; tenant guard treats related managers of loaded tenant objects as scoped; job/company detail pages render
  as one blocking response (`instant = false`) so metadata is in `<head>` for every user agent.
- **Found in exit verification and fixed:** status badge text contrast (axe); `htmlLimitedBots: /.*/` made browser
  prefetch requests hang (removed); frontend image build failed on empty `public/` (Dockerfile creates it); EC-JOB-17/19/20
  lacked tagged tests.
- **Known limitations / follow-ups:** public pages cache 60 s per URL (closed/edited vacancies can be stale up to a minute;
  on-demand revalidation via outbox later); question bank is built-in templates (org template bank UI later); shortlist
  sizing by openings (EC-JOB-19) in Phase 07, offers limit in Phase 10; application-scale paging (EC-JOB-17) from Phase 04;
  `/privacy`, `/terms`, `/accessibility`, `/how-we-use-ai` pages still 404 (console errors in Lighthouse best-practices 96);
  backend dev Docker image is stale (no pgvector) - rebuild before the next compose-based E2E.

### Phase 04 — Candidate Portal, Documents, Applications & Questionnaires (closed 2026-11-10)
- **Built:** candidate profile (sections, completeness, phone E.164, frozen snapshot on submit) and CV library; documents
  (upload sessions with presigned PUT + direct-upload fallback, filename sanitising, per-purpose limits, magic-byte + DOCX/PDF
  checks, image re-encoding, ClamAV INSTREAM, quarantine → documents promotion, per-owner dedupe, generic rejection email,
  orphan cleanup, staff access through visible applications, 503 `storage_unavailable` on S3 outages); applications
  (state machine for every SRS §3.3 transition, append-only status events with DB trigger, duplicate policies, drafts with
  lock_version autosave, documents by role, answers with branching, review checklist, idempotent atomic submit with
  gap-free references, receipts, withdraw/abandon/reactivate lifecycle, consent + AI-notice records with objection flag,
  staff-assisted applications); frontend FileUploader, candidate dashboard/profile/documents/applications/settings,
  `/how-we-use-ai`, the 5-step apply wizard, and a read-only HR applications list/detail.
- **Evidence:** 1,552 backend tests (incl. 100 concurrent double-clicked submits → 100 applications, refs 1..100, 100
  receipts; EICAR/spoofed/corrupt rejection; infected-after-submit keeps the application; exhaustive state machine);
  102 Vitest; Playwright apply journey at 360 px (keyboard-only step, axe on every wizard step, no page errors, Mailpit
  verification + receipt, duplicate, withdraw, no-JS) on mobile + desktop, plus jobs/auth/smoke suites 10/10; Lighthouse
  mobile medians /jobs 91/100/100 and /jobs/[slug] 90/100/100; EC coverage 31/31; schema/migrations no drift.
- **Deviations:** application reference org code = 6-char slug prefix + 4 chars of the org id (two orgs sharing a slug
  prefix collided); `source` keeps known utm/referrer keys only and records `direct` when absent; `/jobs` now renders as
  one blocking response (readable without JavaScript, EC-APP-21); the apply page is blocking with a server-rendered no-JS
  notice and reads `jobId` through a Suspense + `useParams` route wrapper.
- **Found in exit verification and fixed:** hydration error and hang on full load of `/apply` (client `<noscript>`, async
  params page); wizard step saves hit 409 after attaching documents/answers (lock_version now synced); stale "Candidate
  dashboard" E2E assertion; axe sampling buttons mid-transition (E2E helpers freeze transitions); missing EC tests.
- **Known limitations / follow-ups:** EC-APP-15/16 HR flags are computed in Phase 06; the HR review workspace (scores,
  shortlist) arrives in Phase 08; Locust load test against the full stack in Phase 10; real-clamd EICAR runs nightly only.

## Deviations from spec
| Date | Phase/Task | Deviation | Reason | ADR |
|---|---|---|---|---|
| 2026-11-08 | P01-T03 | Minimal `accounts.User` (email login) and `organisations.Organisation` created in Phase 01 | Custom user model must exist before the first auth migration; `TenantModel` needs its FK target. Phase 02 completes both. | — |
| 2026-11-08 | P01-T08/T10 | Dev S3 = SeaweedFS instead of MinIO | MinIO images no longer pullable | ADR-021 |
| 2026-11-08 | P01-T10 | Dev host ports Postgres 55432 / Redis 6380 (configurable) | Port clashes on dev machines | ADR-022 |
| 2026-11-08 | P01-T03 | Django admin served at `/django-admin/` | `/admin` belongs to the Next.js platform-admin UI | — |
| 2026-11-09 | P02-T01 | Bundled breached-password list = Django common-password corpus (19,640 SHA-1 hashes), not top-100k | No vetted 100k list bundled offline; `build_breached_passwords --source` + `BREACHED_PASSWORDS_FILE` let ops swap in a larger list | — |
| 2026-11-09 | P02-T01/T04 | Session metadata via `allauth.usersessions.UserSession` instead of a custom `UserSessionMeta` model | Same fields (ip, user_agent, created, last_seen), maintained by allauth; `/me/sessions` API built on top; IP truncation added in Phase 09 retention | — |
| 2026-11-10 | P03-T05 | Job approval dual control uses the existing `OrganisationPolicy.rubric_dual_control` flag | No separate job flag in the schema; approving a job approves its rubric | — |
| 2026-11-10 | P03-T11 | Auditors can read every vacancy of their organisation (read-only) | Governance role needs visibility; RBAC denies all writes | — |
| 2026-11-10 | P03-T13 | `/jobs/[slug]` and `/companies/[slug]` render as one blocking response (`instant = false`) | Metadata must be in `<head>` for link previews/SEO; streaming gained nothing (data cached 60 s) | — |
| 2026-11-10 | P04-T15 | Application reference org code = 6-char slug prefix + 4 chars of org id (format MHRS-<ORG>-<YYYY>-<NNNNNN> unchanged) | Orgs whose slugs share an 8-char prefix produced identical references | - |
| 2026-11-10 | P04-EXIT | `/jobs` and `/apply/[jobId]` render as one blocking response | Readable without JavaScript (EC-APP-21); streamed content is hidden without JS | - |

## Session log
| Date | Session | Tasks | Summary | Follow-ups |
|---|---|---|---|---|
| 2026-11-08 | Planning | — | Blueprint finalised into docs/ (12 specs), 16 phases, CLAUDE.md memories, commands | Start P01-T01 |
| 2026-11-08 | Impl | P01-T01 | git init (main), .gitignore/.gitattributes/.editorconfig, LICENSE (proprietary), CHANGELOG, README quick start; blueprint kept at root | _to_delete/ (planning tarball) git-ignored, owner may delete |
| 2026-11-08 | Impl | P01-T02 | Verified current versions (PyPI/npm/nodejs.org); Django 5.2 LTS kept (6.2 LTS not yet released), Next 16, Node 24 LTS; recorded in docs/11 | Re-evaluate Django 6.2 LTS / Node 26 in Phase 16 |
| 2026-11-08 | Impl | P01-T03 | Backend scaffold: pyproject (uv, py3.12), split settings base/dev/test/staging/prod, Celery app + queues/beat, /api/v1 + /api/schema + /api/docs, ai_engine placeholder (contracts, versioning); minimal accounts.User + organisations.Organisation pulled forward | Phase 02 completes User/Organisation |
| 2026-11-08 | Impl | P01-T04 | apps.core: BaseModel, TenantModel + TenantQuerySet.for_org() + strict unscoped guard (request context), RequestIDMiddleware + JSON log context, error envelope handler (all codes docs/04 §1), page + cursor pagination, TenantScopedViewSet; tests incl. cross-tenant 404 | - |
| 2026-11-08 | Impl | P01-T05 | Transactional outbox: OutboxEvent/ProcessedEvent, emit() (atomic-only, dedupe), relay (FOR UPDATE SKIP LOCKED, batch 100, backoff), on_commit kick, @idempotent_consumer; tests: rollback, dedupe, concurrent relays, broker down (EC-OPS-01) | - |
| 2026-11-08 | Impl | P01-T06 | IdempotencyKey + @idempotent(endpoint): replay same key/body, 422 idempotency_key_reuse, 400 missing key, per-user, 24h TTL + purge task | - |
| 2026-11-08 | Impl | P01-T07 | C:/Program Files/Git/healthz + /readyz (DB/Redis/S3, parallel with timeouts), FeatureFlag + is_enabled() cached, DeadLetter + BaseTask (acks_late, backoff retries, dead letter), task/request id log context, ping task, send_test_email + celery_ping commands | - |
| 2026-11-08 | Impl | P01-T08 | Storage service: buckets per purpose, presign_put/presign_get(ttl 60)/move/delete/head (moto tests); dev S3 = SeaweedFS + aws-cli init (MinIO images no longer pullable, ADR-021) | - |
| 2026-11-08 | Impl | P01-T09 | EncryptedTextField (Fernet/MultiFernet, key-id prefixed), rotate/needs_rotation, tests read old key + rotate + tamper | Re-encrypt job in Phase 09 (rotate-keys runbook) |
| 2026-11-08 | Impl | P01-T10 | Dockerfile (py3.12-slim, uv, non-root), Dockerfile.worker (tesseract, poppler, libmagic), frontend/Dockerfile (node 24, multi-stage), docker-compose.yml name mhrs w/ healthchecks (postgres pgvector, redis, SeaweedFS S3 + init, mailpit, clamav profile, backend, 3 workers, beat, flower, frontend), docker-compose.prod.yml skeleton, .env.example; verified readyz 200, ping/pong, Mailpit email, 125 tests in container | ClamAV under compose profile 'full' (large image/DB download) |
| 2026-11-08 | Impl | P01-T11 | Next.js 16.4 (App Router, TS strict, Tailwind 4, Turbopack, Cache Components) scaffolded in temp dir and moved in; shadcn/ui (radix-nova), Prettier, ESLint+prettier, Vitest+RTL, Playwright+axe smoke, TanStack Query provider, next-intl (en, Africa/Harare), Inter font, brand tokens (docs/08 §1), route groups (public)/(candidate)/(hr)/(admin), /api rewrites + skipTrailingSlashRedirect, standalone output | - |
| 2026-11-08 | Impl | P01-T12 | api-client.ts (same-origin fetch, CSRF from cookie, X-Org-Id, Idempotency-Key, envelope -> typed ApiError with requestId + fieldErrors, network errors), gen:api (openapi-typescript from backend/schema.yml or live schema) -> src/types/api.d.ts; 12 Vitest tests | - |
| 2026-11-08 | Impl | P01-T13 | UI shells: public header (mobile sheet) + footer with branding, AppShell (sidebar desktop / sheet mobile, top bar) for candidate/HR/admin, OrgSwitcher + NotificationBell placeholders, EmptyState/ErrorState(request id + retry)/ForbiddenState, PageSkeleton, StatusBadge (text + shape, never 'rejected'), 404/500/global-error pages, loading skeletons; API rewrite keeps trailing slash; 22 Vitest tests, build OK | - |
| 2026-11-08 | Impl | P01-T14 | Tooling: ruff/mypy(django-stubs, drf-stubs)/pytest config (--ds test), factory_boy factories (User, Organisation), pre-commit (ruff, prettier, eslint, EOF/whitespace, detect-secrets + .secrets.baseline), scripts/dev-up.ps1 + dev-up.sh, scripts/ec_coverage.py (Phase 01: 2/2 EC covered) | test_user_model.py DB run pending Docker recovery |
| 2026-11-08 | Impl | P01-T15 | CI .github/workflows/ci.yml: backend (pgvector+redis services, ruff, format, mypy, makemigrations --check, pytest cov>=80, EC coverage, bandit, pip-audit), frontend (format, lint, typecheck, vitest, build, npm audit), contract (schema drift + gen:api drift + typecheck), images on main (+Trivy); nightly.yml skeleton (compose E2E+axe, Semgrep/Trivy/bandit, AI benchmark placeholder). Local run of bandit/pip-audit/npm audit/spectacular --fail-on-warn all clean | CI green on GitHub needs a remote (none configured yet) |
| 2026-11-08 | Impl | P01-T16 | backend/CLAUDE.md + frontend/CLAUDE.md rewritten for the actual scaffold (core module map, host vs container commands, Next 16 Cache Components caveats), docs/runbooks/README.md index + dev quick reference; .env auto-load made opt-in (DJANGO_READ_DOT_ENV) so host test runs work; frontend healthcheck uses 127.0.0.1 | - |
| 2026-11-08 | Impl | P01-T17 | Clean clone (path with spaces) -> scripts/dev-up.ps1: all 11 services healthy in 79 s (cached images, fresh volumes); /readyz 200 (db/redis/s3), frontend home via proxy 200, /api/v1/ through Next rewrite 200, celery ping -> pong (worker-default), send_test_email received in Mailpit; Playwright+axe smoke 4/4 (desktop+mobile). Fixed dev-up.ps1 stderr handling | Host RAM pressure (~1 GB free) caused one transient ENOMEM + an earlier Docker engine hang |
| 2026-11-08 | Impl | P01-EXIT (verify) | Exit criteria: clean-clone stack 79 s ✅, apps/core coverage 97% ✅, /api/docs + gen:api + tsc ✅, CI on main ❌ not verifiable (no remote; all CI steps green locally) | Phase 01 NOT closed; need GitHub remote from owner |
| 2026-11-08 | Impl | P01-EXIT | CI fixed on GitHub (scripts ruff config, trivy-action pinned by SHA, empty public/ in frontend image, Debian security updates in backend images); CI green on main run 42523821127; Phase 01 closed | Start P02-T01 |
| 2026-11-09 | Impl | P02-T01 | User completed: email_verified_at, preferred_name, phone_e164, platform_role (none/platform_admin/platform_support), locale, timezone, mfa_grace_started_at, deleted_at; email normalised on save; Argon2 hasher; validators = min 10 + similarity + BreachedPasswordValidator (SHA-1 gz list, build_breached_passwords command); 13 new tests | Swap in a top-100k list when owner supplies one |
| 2026-11-09 | Impl | P02-T02 | allauth headless (browser) at /api/v1/auth/browser/v1/*: signup, verify (link -> frontend /verify-email, auto-login), login/logout, password reset (1 h single-use) + change, email change with re-verification + notice to old address; enumeration-free (ADR-023: verification mandatory before login); /api/v1/csrf/; branded MHRS email templates; all auth email goes through outbox (core.email.queue_email, bodies encrypted); email_verified_at synced via signals; require_verified_email guard; 11 flow tests | Lockout hooks wired here; tests + session API in P02-T04 |
| 2026-11-09 | Impl | P02-T05 | apps.audit: AuditEvent hash chain per organisation (+platform), sha256(canonical JSON + prev_hash), advisory-lock serialised; Postgres trigger rejects UPDATE/DELETE (opt-in maintenance flag for Phase 09); audit.record(actor, action, target, before/after minimised, reason, request -> ip /24|/48 + UA hash + request_id); AccessLog + log_access; verify_audit_chain command; 14 tests incl. tamper/delete detection + concurrent writers. Done before T03 (reset_mfa needs it) | - |
| 2026-11-09 | Impl | P02-T03 | MFA via allauth.mfa (TOTP + 10 recovery codes); policy module accounts/mfa.py (privilege-provider registry: platform roles now, org_admin/hr_manager registered by organisations), 7-day grace started on first login/contact, MfaEnforcementMiddleware returns 401 mfa_required on staff API prefixes after grace; reset_mfa (EC-ACC-08) audited; 11 tests incl. enrolment, 2FA login, recovery-code single use, grace/enforced | Frontend must handle allauth 'reauthenticate' flow before TOTP setup / recovery codes |
| 2026-11-09 | Impl | P02-T04 | Progressive lockout (10 fails -> 15 min, doubling to 24 h cap, per normalised email, generic too_many_login_attempts, owner notified, cleared by password reset or time) via allauth adapter + lockout-aware backend; allauth IP/key rate limits; DRF Anon/User throttles; /api/v1/me/sessions list (truncated IP, is_current), revoke one, revoke-others (audited); revoke_all_sessions helper (EC-ACC-12); new-device sign-in email (EC-ACC-11); global cache-clear test fixture; 13 tests | - |
| 2026-11-09 | Impl | P02-T06 | Organisation (full profile, statuses incl. closed), OrganisationPolicy (defaults per docs/03 + decisions, version lock), Department, Location, Membership (6 roles), Invitation (sha256 token hash, 7-day expiry, single open invite per email, allow_any_email). Services: create (creator org_admin, pending_verification, slug de-dup), update (nh3 sanitised), update_policy (409 stale), invite/resend (rotates token)/revoke/accept (EC-ORG-03/04/05) with outbox email, change_role + deactivate with last-admin guard, deactivation revokes sessions + reassignment provider hook; org privilege registered for MFA; core.sanitize; factories + make_org_with_team; 17 tests | EC-ORG-09 reassignment list populated by jobs in Phase 03 |
| 2026-11-09 | Impl | P02-T07 | OrganisationContextMiddleware: request.organisation/membership from X-Org-Id (validated active membership, closed orgs excluded) or session active org (stale cleared); foreign/invalid header -> 404 + audit tenant_violation_attempt (EC-ORG-06); suspended/closed org -> 423 org_suspended for unsafe requests on context-scoped staff APIs (EC-ORG-07); POST /api/v1/me/active-org/; selectors active_membership/memberships_for_user; 13 tests | - |
| 2026-11-09 | Impl | P02-T08 | RBAC: central role x action matrix organisations/rbac.py (fails closed on unknown actions); permission classes HasOrgRole(*roles)/HasOrgAction(action) (path organisation_id or context; non-member 404, wrong role 403, suspended writes 423), IsAssignedToJob (Phase 03 registers checker), IsPlatformAdmin, IsPlatformStaff (support read-only), IsCandidateOwner (404 for others), conflict-of-interest checker registry + audited 403 (EC-ACC-09/10); 20 tests | - |
| 2026-11-09 | Impl | P02-T09 | APIs (OpenAPI-annotated, schema clean): GET/PATCH /me (memberships, active org, MFA status, E.164 phone, tz/locale validation, audited), POST /organisations, GET/PATCH /organisations/{id}, GET/PATCH .../policies (lock_version), CRUD .../departments + .../locations (audited, case-insensitive unique), .../members list/PATCH role/DELETE deactivate (reassignment list)/POST reset-mfa, .../invitations list/create/resend/revoke, public GET /invitations/{token} (masked email) + POST accept, public GET /companies/{slug} (active only); StrictFieldsMixin rejects unknown fields; RbacActionMixin maps DRF actions to rbac matrix; 16 API tests; TS types regenerated | - |
| 2026-11-09 | Impl | P02-T10 | apps.platform: services verify/suspend(reason required)/reactivate (state checks -> 409 invalid_transition, audited, outbox organisation.* events for downstream pause/hide); /api/v1/platform/organisations list (status filter, search, member_count) + retrieve (admin + support read-only) + verify/suspend/reactivate (admin only); create_platform_admin command from PLATFORM_ADMIN_EMAIL/PASSWORD env (idempotent, verified email, MFA grace); enum name overrides; 13 tests | - |
| 2026-11-09 | Impl | P02-T11 | Test scaffolds: tests/tenancy/registry.py (21 org endpoints, Ctx + setup hooks for later phases), cross-tenant suite (404 for every endpoint from another org's admin, list exclusion, foreign X-Org-Id audited, unauthenticated rejected), tests/permissions/matrix.py derived from rbac (21 endpoints x 6 roles), meta-test every DRF view declares permissions, integration: MFA enforced on staff API after grace, audit chain verifies after API activity; org publish guard assert_can_publish (EC-ORG-08); ec_coverage supports ranges/heading variants (Phase 02 19/19); 435 backend tests, 98% coverage | - |
| 2026-11-09 | Impl | P02-T12 | Frontend auth: typed allauth headless client (CSRF bootstrap, 401 flows vs errors), zod schemas, accessible TextField + ErrorSummary, pages /login (+MFA step, verify-email notice, ?next with open-redirect guard), /register (no-enumeration 'check inbox'), /verify-email (explicit confirm, expired page), /forgot-password, /reset-password; /account/security (MFA setup with QR + recovery codes behind reauth dialog, change password, change email, sessions list/revoke/revoke-others); useMe auth context, AuthGate per area (MFA grace banner, forbidden state), UserMenu in shells/header, proxy.ts redirect for signed-out visitors; en.json strings; 21 new Vitest tests (43 total), build OK | Playwright auth journey in P02 exit verification |
| 2026-11-09 | Impl | P02-T13 | Backend: POST /organisations/{id}/logo/ (Pillow verify + re-encode PNG <=512px, metadata stripped, private bucket, audited), logo_url presigned in org + company serializers, organisation_id on memberships, spectacular doc leak fixed. Frontend: /employers (pitch + create-org form -> active org -> settings), HR settings layout + tabs: organisation (profile + logo upload, verification/suspension notice), structure (departments/locations CRUD), team (members table w/ role change + deactivate ConfirmDialog with reason, invitations invite/resend/revoke), policies (lock_version, stale-conflict handling, read-only for HR managers); real OrgSwitcher (POST /me/active-org); /invitations/[token] accept page (signed-out sign-in path, expired/revoked/used/email-mismatch states); UI role helper mirroring rbac (hiding only); SelectField + ConfirmDialog; 13 component tests (56 total); 7 backend logo tests | - |
| 2026-11-09 | Impl | P02-T14 | Admin UI /admin/organisations: status filter (pending by default), search, table (status badge, members, created), verify / suspend (required reason) / reactivate via ConfirmDialog, platform support read-only; output serializers marked read-only (precise OpenAPI types); status tones for org/membership states; 4 component tests (60 total) | - |
| 2026-11-09 | Impl | P02-EXIT | Phase 02 journeys pass in Playwright (desktop + mobile); fixed pre-hydration GET submit (password in URL), dev origins, CSRF origin, stale /me refresh; CI green run 42570014917; Phase 02 closed | Start P03-T01 |
| 2026-11-09 | Impl | P03-T01 | apps.taxonomy: TaxonomyVersion, Skill (pgvector 384-d embedding column, org custom skills), SkillAlias, SkillRelation, QualificationLevel/Alias, ProfessionalBody; fixtures: 700 skills / 14 categories (all SRS M24 sectors), 112 relations, ZW qualification framework (O/A-Level, NC, ND, HND, degrees...) + 20 professional bodies, generated by scripts/build_taxonomy_fixtures.py; load_taxonomy (idempotent, versioned, checksum conflict, deactivates removed skills); trigram autocomplete API + qualification levels (public) + org custom skills CRUD (taxonomy.manage) registered in tenancy/matrix suites; 13 tests (511 total). Dev Postgres host port moved to 15432 (55432 became Windows-reserved, ADR-022 amended) | Platform taxonomy curation UI/API in Phase 14 admin |
| 2026-11-09 | Impl | P03-T02 | apps.jobs models: Job (header + lifecycle status, visibility public/unlisted, locations M2M, salary Decimal USD/ZWG, timezone, lock_version, SearchVectorField + GIN, check constraints openings>=1 & salary_min<=max), JobSlugRedirect, JobVersion (draft/in_review/approved/superseded, content + snapshot), JobCriterion (type/importance/justification/skill/qualification/min_months/equivalents/rubric category), Rubric (DB check: approved => total 100), JobApproval, JobAssignment, JobEvent; search.py unique global slugs (redirect-aware) + weighted FTS vector; JobFactory; 7 tests | - |
| 2026-11-09 | Impl | P03-T03 | questionnaires app: Questionnaire (job_version 1:1 or template), Question (stable key, branching show_if, scoring config, knockout, protected flag + exception reason), QuestionOption, QuestionResponse; pure validation (types, options, config, scoring modes per type, salary never scored, branching only to earlier questions); 543 tests pass | backend dev image stale (no pgvector) - rebuild before E2E |
| 2026-11-09 | Impl | P03-T04 | linter lexicon (age/DOB, religion, tribe/totem, marital/children, pregnancy, HIV/health, disability, political incl ZANU/MDC/CCC, gender, national ID, appearance); questionnaires.services.replace_questions recomputes flags; record_protected_exception (hr_manager/admin via rbac questions.protected_exception, >=20 char reason, audited, reset on rewording); flagged questions block publishing |  |
| 2026-11-09 | Impl | P03-T05 | jobs.services: create (creator auto-assigned recruiter, default 35/25/20/10/10 rubric, empty questionnaire), update w/ lock_version (EC-JOB-07; slug frozen after first publish EC-JOB-13), set_criteria (essential justification), set_rubric (=100, ordered bands), set_questionnaire; readiness(stage submit|publish) checklist + warnings (all-essential, <24h, protected topics); submit/approve/reject (dual control via policy.rubric_dual_control, approval freezes version+rubric+questionnaire+snapshot); publish/schedule/publish_scheduled/pause/resume/close/auto_close/archive/extend_deadline (reopens closed)/new_version (live advert swaps on approval, EC-JOB-06)/duplicate (EC-JOB-14); JobEvent+audit+outbox job.published/job.closed/...; 26 tests | dual control for job approval reuses policy.rubric_dual_control (no separate flag) |
| 2026-11-09 | Impl | P03-T06 | apps.jobs.tasks publish_scheduled_jobs + close_expired_jobs (beat every minute, <= now catch-up EC-JOB-18, per-job lock + service re-check = idempotent, failures isolated); scheduled job past deadline reverts to approved; TZ-aware deadline test (EC-JOB-05) |  |
| 2026-11-09 | Impl | P03-T07 | jobs.assignments: is_assigned registered as IsAssignedToJob checker, jobs_visible_to (admin/hr all; recruiter/hiring_manager assigned only; others none), set_assignments (admin/hr only, eligible org roles per role_on_job, active same-org members, open job needs a recruiter, audited), needs_reassignment provider (EC-ORG-09: sole recruiter on open jobs) |  |
| 2026-11-09 | Impl | P03-T08 | jobs.suggestions: flag jobs.ai_suggestions (default off) + policy.ai_enabled; taxonomy n-gram skill extraction (names + aliases, longest match); suggested criteria always preferred, skip existing skills, nothing persisted; question suggestions pass questionnaire validation | POST /hr/jobs/{id}/ai-suggestions endpoint wired with the HR API in P03-T11; accept UI in P03-T12 |
| 2026-11-09 | Impl | P03-T09 | core.sanitize nh3 allow-list (p, br, strong, em, ul, ol, li, h2-h4, a[href http/https/mailto] rel=noopener nofollow ugc) applied in jobs.services on every rich-text save; 20-payload XSS suite x 3 fields (EC-JOB-12) + allowed-markup and stripped-tag tests |  |
| 2026-11-09 | Impl | P03-T10 | public APIs: GET /jobs (websearch FTS rank + location/workplace/employment/seniority/org/posted_within/closing_within filters, relevance|newest|closing|title ordering, page pagination, public_search throttle), /jobs/{slug|id} (published/paused/unlisted; closed 200+is_closed for 90 days then 410 gone; old-slug 301), /jobs/{slug}/questions (approved published-version questions, scoring/knockout stripped), /companies/{slug} open_jobs, /sitemap.xml, /jobs/feed.rss|json; suspended orgs hidden; salary only when disclosed (decimal strings); schema + api.d.ts regenerated | frontend proxies /sitemap.xml + feeds in P03-T13 |
| 2026-11-09 | Impl | P03-T11 | HR job API /api/v1/hr/jobs (X-Org-Id context): list (status/search/assigned/ordering) + create + retrieve + PATCH(lock_version) + PUT criteria/rubric/questionnaire + lint + ai-suggestions + questions/{key}/protected-exception + submit/approve/reject/publish/schedule/pause/resume/close/archive/extend-deadline/duplicate/new-version + assignments GET/PUT + events + versions; rbac jobs.assign; auditor read-only access to org jobs; tenant guard treats related managers of loaded tenant objects as scoped; 31 endpoints registered (org_header, targets_object, per-endpoint setup -> suites 84 s); 11 API tests; schema validated, api.d.ts regenerated; 861 backend tests |  |
| 2026-11-09 | Impl | P03-T12 | frontend HR vacancies: /hr/jobs table (status filters, debounced search, paging, empty/error/permission states), 5-step wizard /hr/jobs/new + /hr/jobs/[id]/edit (Details w/ TipTap rich text + deadline in vacancy TZ; Requirements criteria builder w/ taxonomy combobox, essential justification, equivalents, AI suggestions panel (flagged, accept-only); Questions builder w/ options, scoring per type, knock-out, earlier-question branching, protected-topic notices + HR exception, question bank; Rubric sliders w/ live total=100 + bands; Preview + readiness checklist + submit), debounced autosave with lock_version and 409 conflict reload, locked-version state; /hr/jobs/[id] overview (status actions w/ reason/date dialogs, 422 checklist, assignments editor, versions, activity); AuthGate + sidebar active state under Suspense (dynamic routes PPR); status badge contrast fix (axe); seed_demo command (2 orgs, users per role, 3 published jobs) + scripts/run_backend_host.py; 16 vitest + Playwright journey (desktop+mobile, axe) green | seed_demo also covers P03-T14 (tick after skill linking + tests) |
| 2026-11-10 | Impl | P03-T13 | public pages: / (search), /jobs (SSR GET form filters, pagination, empty/unavailable states), /jobs/[slug] (deadline in vacancy TZ + viewer local TZ, essential vs preferred, documents, Apply CTA, WhatsApp/LinkedIn/email/copy share, JSON-LD JobPosting with safe escaping, OG/canonical, closed banner + noindex, unlisted noindex, 410 gone page, old-slug permanent redirect), /companies/[slug]; 'use cache' data with 60 s cacheLife; robots.ts + /sitemap.xml and /jobs/feed.rss|json rewrites; root ships only public i18n namespaces (areas get full catalogue). Lighthouse mobile median of 3 (scripts/lighthouse.sh): /jobs perf 89 a11y 100 SEO 100; /jobs/[slug] perf 88 a11y 100 SEO 100. Playwright jobs journey 8/8 (desktop+mobile, axe). Found + fixed: htmlLimitedBots=/.*/ made browser prefetch requests hang -> removed; blocking render of detail pages keeps metadata in head instead | public pages are cached 60 s per URL, so a closed/edited vacancy can show stale for up to a minute (on-demand revalidation via outbox later) |
| 2026-11-10 | Impl | P03-T14 | seed_demo (DEMO_PASSWORD env, refuses when DEBUG off unless --allow-non-debug): platform admin, MudhoTech Demo Ltd + Acme Mining Zimbabwe (verified, privacy notice, departments, locations, one user per role), 3 published jobs via the real services (Software Developer per Blueprint Appendix A, Accountant, Registered Nurse) with justified criteria linked to the taxonomy where skills exist (taxonomy auto-loaded), rubrics and valid questionnaires (branching, knock-out, salary never scored); idempotent; 5 tests; 866 backend tests pass |  |
| 2026-11-10 | Close | P03-EXIT | Phase 03 closed: exit criteria verified (E2E 8/8, Lighthouse /jobs 89/100/100 and /jobs/[slug] 88/100/100, EC-JOB 20/20, 868 backend + 79 frontend tests, tenancy/matrix 360). Fixed during close: EC-JOB-17/19/20 tests, frontend Dockerfile public/ | Phase 04 started |
| 2026-11-10 | Impl | P04-T01 | apps.candidates: CandidateProfile (user-owned, lock_version, E.164 phone, validated links, availability/notice) + Experience/Education/Certification/CandidateSkill/Language (source manual|cv_import read-only, date checks, case-insensitive uniqueness); /candidate/profile GET (auto-create)/PATCH + section CRUD scoped to request.user (404 for others); completeness 0-100 + missing list; test asserts no protected field names on any candidate model; schema + api.d.ts regenerated | default_resume FK added with documents in P04-T02 |
| 2026-11-10 | Impl | P04-T02 | apps.documents: UploadSession + Document (user-owned, quarantine->documents buckets, scan_status, sha256 index, duplicate_of); per-purpose allow-lists (CV pdf/docx, supporting/messages pdf/docx/jpg/png, offer pdf) with ext+declared MIME match, EC-DOC-04 conversion guidance (415), size limits from settings narrowed by OrganisationPolicy.upload_limits_mb (413); filename sanitisation (UUID storage keys); presign PUT (10 min) -> complete (HEAD, real size check, idempotent, rejection committed) -> outbox document.uploaded; multipart direct-upload fallback; GET /documents/{id} + /download (owner or registered access checker, clean only, 302 to 60 s presigned attachment URL, no-store, access log); uploads throttle; CandidateProfile.default_resume FK; shared s3 (moto) fixture; 22 tests; 896 backend tests | staff document access checker registered by applications (P04-T15); upload_limits_mb not yet editable in the policy API |
| 2026-11-10 | Impl | P04-T03 | documents queue scan pipeline (outbox document.uploaded -> on_commit scan_document task, autoretry on scanner outage): sha256, own magic-byte signatures (+ python-magic second opinion on Linux) reject spoofed types before any parser (EC-DOC-05), ClamAV INSTREAM client (fake/skip modes; skip DEBUG-only) - infected never parsed, audited, generic candidate email (EC-DOC-06), DOCX guards (entries/size/ratio, macros, unsafe paths; EC-DOC-07), PDF via PyMuPDF (encrypted, page limits 30 CV/50 other; EC-DOC-08), images re-encoded (metadata/polyglot stripped), promote quarantine->documents, outbox document.accepted|rejected; new scan_status 'rejected' for non-malware rejections; deps pymupdf~=1.28.2 + python-magic (non-Windows), libmagic1 in image; nightly real-clamd EICAR job; 17 pipeline tests; 913 backend tests | found+fixed: rejection email shared the outbox dedupe key with document.rejected and was dropped |
| 2026-11-10 | Impl | P04-T04 | documents.cleanup + hourly beat cleanup_uploads: expire pending sessions past expires_at, delete unconfirmed/orphan quarantine objects older than 24 h unless referenced by a live session or pending document (EC-APP-08), purge rejected/infected files after 24 h keeping rows (deleted_at); scan pipeline de-duplicates identical bytes per user+purpose (EC-DOC-25): alias to the original's stored file and verdict, quarantine copy removed, stored once; pipeline refactored (_find_original/_alias/_scan_and_promote); 5 tests |  |
| 2026-11-10 | Impl | P04-T05 | apps.applications: Application (all SRS 3.3 statuses, snapshot, reference, contact/last_step for the wizard, scoring fields, flags/tags arrays, lock_version, indexes) with active_key partial unique constraint + reference-after-submit check; ReferenceCounter (per org+year, row-locked MHRS-<ORG>-<YYYY>-<NNNNNN>); ApplicationDocument; append-only ApplicationStatusEvent (model guard + DB trigger reusing mhrs_audit_append_only); QuestionResponse.application now a FK; services: duplicate policy (one_active / allow_resubmit_replace / allow_multiple), start_or_resume_draft (resume draft, 409 duplicate_application with link, re-apply after withdrawal, concurrent-create safe, closed/paused/deadline 422); 12 tests |  |
| 2026-11-10 | Impl | P04-T06 | applications/state_machine.py: full SRS 3.3 table with per-transition actors (candidate/staff/system) and reasons; consequential outcomes (shortlisted/not_selected/offer/hired) and reopen of terminal states human-only with reason; services.transition(): row lock, actor resolution (staff via rbac applications.transition, candidate = owner, system has no actor), reopen limited to org_admin/hr_manager, active_key maintained (withdraw frees slot, reopen conflicts with newer active), append-only status event + audit + outbox application.status_changed; exhaustive tests: 225 pairs vs an independent SRS table, every allowed transition x 3 actor kinds, disallowed pairs 409 (544 tests) | check constraint now allows abandoned drafts without a reference |
| 2026-11-10 | Impl | P04-T07 | candidate draft APIs: POST /applications (create 201 / resume 200 / 409 duplicate / 404 / 422 closed), GET /applications, GET/PATCH /applications/{id} (contact + last_step autosave with lock_version, E.164 phone), PUT /documents (own, not rejected/infected, pending ok, unique, 25 MB total, role + required_doc_key), PUT /answers (per-type validation, file answers must be own documents, branching evaluated server-side and hidden answers deleted/ignored), GET /review (email_unverified, document_required, document_rejected, answer_required by step); pure answers.py (validate_answer, visible_keys incl. hidden-parent cascade, missing_required); 18 tests; 1480 backend tests |  |
| 2026-11-10 | Impl | P04-T08 | POST /applications/{id}/submit (@idempotent Idempotency-Key, atomic): checks org active (423 org_suspended), job published / paused (job_paused) / closed, deadline by server time inclusive + APPLICATION_DEADLINE_GRACE_SECONDS (EC-APP-05), draft only, review checklist (email_unverified EC-ACC-03, required docs - scan pending ok, rejected not - required visible answers), privacy acceptance; freezes candidate_profile_snapshot (candidates.profile_snapshot, no protected fields) with job_version, gap-free reference MHRS-<ORG>-<YYYY>-<NNNNNN>, transition draft->submitted, outbox application.submitted (+objects_to_automated_processing), encrypted receipt email; allow_resubmit_replace withdraws the previous submitted one; 12 tests incl. 100 concurrent double-clicked HTTP submits -> 100 apps, refs 1..100, 100 receipts (EC-APP-01/04); 1492 backend tests | Locust scenario against the full stack in Phase 16 load testing; consent records persisted in P04-T10 |
| 2026-11-10 | Impl | P04-T09 | applications.lifecycle: POST /applications/{id}/withdraw (non-terminal -> withdrawn with reason, draft -> abandoned; 409 when closed) + email to assigned recruiters (EC-APP-12/13); is_processable() guard for processing tasks; job.closed consumer abandons drafts with notice, submitted untouched (EC-JOB-10); pause keeps drafts (EC-JOB-08); job.deadline_extended consumer reactivates drafts abandoned by the close within 30 days unless the candidate has a newer active one + email (EC-JOB-09; new system-only abandoned->draft transition added to the state machine and SRS table test); hourly sweep_stale_drafts beat safety net; 8 tests; 1502 backend tests |  |
| 2026-11-10 | Impl | P04-T10 | apps.privacy ConsentRecord (purpose, notice_version, granted, granted_at, withdrawn_at, ip_trunc /24 or /48, context) + services; submit records application_processing consent (employer privacy notice version = policy version + sha256 of text) and ai_assisted_screening notice acknowledgement (AI_NOTICE_VERSION; granted=False = objection), sets Application.consent_record_id + new objects_to_automated_processing flag (Phases 7/8 hide AI evaluation); application API exposes notices (privacy text/version, AI notice version/url) for the wizard; public /how-we-use-ai page (what AI does / never does / choices / data, versioned); 5 tests |  |
| 2026-11-10 | Impl | P04-T11 | assisted applications: POST /hr/jobs/{id}/assisted-applications (multipart or JSON; recruiting staff who are admin/HR or assigned): email required (EC-APP-18), consent confirmation + method (in_person|phone|written); finds or creates the candidate account (unusable password), runs the normal draft/document/answer/submit services with the staff member as actor (only the email-verification gate is skipped), flags is_assisted/assisted_by/channel, consent context names the method and staff member, audit application.assisted_created, invite email with set-password link for new/passwordless accounts (EC-APP-17); duplicate policy still applies; registered in cross-tenant + permission matrix (open_job fixture stage); 7 tests; 1521 backend tests |  |
| 2026-11-10 | Impl | P04-T12 | frontend FileUploader (features/documents): upload session -> XHR PUT to presigned URL with progress -> complete -> poll scan status (2 s, ~2 min, then 'still checking' and carry on); falls back to multipart direct upload when storage is unreachable (status 0 / upload_failed); cancel (AbortController), retry only for transfer failures, client-side size check, purpose-specific accept list, friendly per-reason rejection messages, labelled file input + progressbar + aria-live status/alert; documentsApi client; 6 Vitest tests (happy path, fallback, polling, rejection, oversize, retry); 85 frontend tests |  |
| 2026-11-10 | Impl | P04-T13 | candidate frontend: /candidate/dashboard (things to do: drafts to finish + profile completeness, active application counts, jobs matching profile skills via public FTS), /candidate/profile (completeness meter + missing checklist, details form with lock_version conflict handling, generic section manager for experience/education/certifications/skills/languages), /candidate/documents (FileUploader, CV library with scan chips, set default, download, remove with confirm), /candidate/applications + [id] (status list, draft continue link, candidate timeline, what you sent, withdraw/discard with optional reason), /candidate/settings; shared candidate layout with main landmark; backend: CV library API (GET /candidate/resumes, set-default, DELETE unless used by a submitted application) and GET /applications/{id}/timeline (internal steps folded, no staff reasons); 3 backend + 5 Vitest tests |  |
| 2026-11-10 | Impl | P04-T14 | Apply wizard /apply/[jobId]: 5 steps + confirmation, resume from last_step, autosave indicator, conditional questions (client mirror of branching), word counters, required-doc picker/uploader, review with blocking list and go-to-step links, privacy consent + AI objection, idempotent submit, specific messages for deadline/paused/closed/suspended/unverified/duplicate, 401 -> sign-in and back (EC-APP-06); 7 Vitest tests | 360px/keyboard/axe verified in P04-T16 Playwright |
| 2026-11-10 | Impl | P04-T15 | HR minimal applications: GET /hr/jobs/{id}/applications (status/search/paging, drafts hidden, assignment-scoped) + GET /hr/applications/{id} (snapshot, documents, answers, status history; access logged); staff document access checker (submitted + visible apps only); cross-tenant + role matrix entries; HR list/detail pages + 'View applications' on vacancy; fixed reference collisions for orgs sharing a slug prefix (org code = 6-char slug prefix + 4 chars of org id); backend 1545 passed, Vitest 101 | Full review workspace in Phase 08 |
| 2026-11-10 | Impl | P04-T16 | E2E e2e/apply.spec.ts: register -> verify via Mailpit -> apply to seeded Software Developer with synthetic PDF CV + answers (keyboard checkbox) at 360px -> receipt email with reference -> duplicate attempt points to existing app -> withdraw; signed-out apply -> login?next; axe on each wizard step; no uncaught page errors. Passed mobile x3 + chromium x2. Fixed: hydration error (noscript) and hang on full load (async params page) -> Suspense + useParams route wrapper; lock_version sync after documents/answers saves; opaque sticky header. Host runner gained celery mode (worker -P solo + separate beat on Windows) and S3 rewrite |  |
| 2026-11-10 | Close | P04-EXIT | Phase 04 closed: exit criteria verified (1552 backend tests incl. 100 concurrent submits, EICAR/spoofed + infected-after-submit, exhaustive state machine; Playwright apply journey 360px keyboard + axe + no-JS on mobile/desktop, jobs/auth/smoke 10/10; Lighthouse /jobs 91/100/100, /jobs/[slug] 90/100/100; EC 31/31; 102 Vitest). Fixed during close: missing EC tests, storage_unavailable 503, source=direct, /jobs no-JS, axe transition flake, stale auth E2E heading | Phase 05 started |
| 2026-11-10 | Impl | P05-T01 | apps.notifications: NotificationTemplate (platform defaults + org overrides, versioned, one active per key/channel/locale), Notification (dedupe_key unique, status, scheduling, read_at), EmailSuppression; registry of 14 notification keys with allowed variables + preview samples (no scores/evaluations); safe renderer ({{ var }} only, strict variables, escaped values, markdown via Python-Markdown + nh3, branded HTML layout + plain-text alternative with no-reply footer); services save (new version, audit), revert, render_for with fallback to default (EC-NOT-05), preview; HR API /hr/notification-templates list/create/retrieve/preview/history/revert (notifications.manage = org_admin/hr_manager); 10 tests + 42 tenancy/matrix cases | Delivery pipeline + default template content in T02/T03 |
| 2026-11-10 | Impl | P05-T02 | Platform default templates (en) for all 14 notification keys, email + one-line in-app text: receipt with reference, re-upload request, clarification request/reminder (question shown only in the portal), withdrawal confirmation, draft deadline reminder, draft abandoned, shortlisted, respectful not_selected (human decision, no reasons/scores), recruitment paused, staff invitation, rights request update, recruiter digest (AI suggestions need human review), note mention; synced idempotently on post_migrate (new version only when text changes, no audit noise) + sync_notification_templates command; tests: render with samples, no score/rank/rejected/percent wording, idempotent versioning |  |
| 2026-11-10 | Impl | P05-T03 | Delivery pipeline: notify() writes one Notification per channel inside the business transaction (dedupe_key unique) + outbox notification.queued; send_notification task claims queued->sending, checks recipient active + verified email (EC-ACC-07), suppression list (EC-NOT-01), withdrawn application (EC-NOT-04), quiet hours 20:00-07:00 recipient TZ for non-urgent candidate mail (EC-NOT-09), renders org override with fallback, sends with deterministic Message-ID, marks sent; provider errors requeue and retry with backoff ~24 h (13 retries, 4 h cap) then dead letter + failed (EC-NOT-02); send_due beat task (deferred mail, stale sending rows); receipt, withdrawal confirmation, draft-abandoned and document re-upload emails now go through templates; 12 delivery tests incl. replay and killed-worker; backend 1633 passed | Internal status 'sending' added to Notification; auth/security and recruiter emails still use queue_email |
| 2026-11-10 | Impl | P05-T04 | POST /api/v1/webhooks/ses/ for SNS bounce/complaint feedback: topic allowlist (SES_SNS_TOPIC_ARNS, empty = refuse all), signing cert only from https sns.<region>.amazonaws.com, RSA signature over the canonical string (v1/v2), subscription confirmation only to Amazon; hard bounce/complaint -> EmailSuppression (audited without the address), bounced notification marked failed, soft bounces logged; /me exposes email_delivery_problem and signed-in areas show an 'update your email' banner (EC-NOT-01); 9 backend + 2 Vitest tests | Set SES_SNS_TOPIC_ARNS at go-live (Phase 11); dev uses Mailpit (no bounces) |
| 2026-11-10 | Impl | P05-T05 | In-app notifications: GET /notifications (own, paged, ?unread=1, rendered one-line text, site-relative link only), GET /notifications/unread-count, POST /notifications/{id}/read and /notifications/read-all (other users' items 404); NotificationBell in candidate/HR/admin top bars polling every 30 s while visible, unread count in the accessible name, panel with open / mark read / mark all, closes on Escape or outside click; 3 backend + 2 Vitest tests; checked in the running app |  |
| 2026-11-11 | Impl | P05-T06 | apps.messaging: ClarificationRequest (one open per application, questions/answers JSON, due_at, statuses open/answered/expired/cancelled), MessageThread (one per application), Message (plain-text sanitised body, attachment ids). HR asks (1-5 questions, due 1 h-30 d, from under_review/processing) -> needs_information + candidate email/in-app (question text only in the portal); candidate answers (plain text, own clean uploads) -> processing -> back to under_review via clarification.answered consumer until Phase 06/07 re-evaluation, recruiters notified; HR cancel; beat task: reminder 24 h before due, expiry -> expired + recruiter notified, no automatic decision, candidate can still message (EC-NOT-07); messages both ways with new_message notifications (no bodies in email, staff names hidden from candidates), attachments must be own message files that passed the scan (EC-NOT-08), participants may download them; question templates endpoint; all audited (never message bodies); 3 new notification kinds; 7 tests + 42 tenancy/matrix cases; backend 1697 passed | Screening re-evaluation on clarification.answered arrives with Phases 06/07 |
| 2026-11-11 | Impl | P05-T07 | ATS: POST /hr/applications/{id}/transition (state machine; reason codes required for shortlist / not_selected / hold / reopen from seeded decision_reasons, 'other' needs text; outcomes need new applications.decide = org_admin/hr_manager; reopen HR-manager only; optional lock_version; candidate outcome email + in-app held for the org's notification delay); notes with team/private visibility and @mentions (only colleagues who can see the application, in-app note_mention, bodies never audited); PUT tags (normalised, max 10); POST assign (applications.assign = org_admin/hr_manager, assignee must work on the vacancy); GET /hr/decision-reasons; HR detail now returns tags, assignee, lock_version, allowed_transitions; scheduled in-app notifications stay hidden until due; 6 tests + 56 tenancy/matrix cases; backend 1745 passed | Undo within the delay and batching arrive with the Phase 08 shortlist workflow |
| 2026-11-11 | Impl | P05-T08 | HR UI: /hr/jobs/[id]/pipeline kanban (status columns, HTML5 drag onto a column + keyboard Move button per card, move dialog loads allowed moves, asks for the reason code list the move needs, 'other' needs text, notification-delay notice for outcomes, explains illegal moves and server 409s with allowed targets, stale-version reload); application detail panels: actions (change status, assign recruiter for HR managers, tags), notes (team/private, mention colleagues on the vacancy), clarification composer (templates, up to 5 questions, upload toggle, due date; list with answers and withdraw), message thread (30 s refresh); status history kept; vacancy team endpoint now returns user_id; decision reasons re-seeded on post_migrate (survive test flushes); 6 Vitest tests; checked in the running app (move to on hold, note, tag, clarification) | Mobile kanban is a horizontal scroll; attachments in HR messages arrive with T09 |
| 2026-11-11 | Fix | CI-NIGHTLY | Nightly workflow had never passed. E2E job now starts beat + documents worker, seeds demo data and runs a production frontend build; ClamAV job gets Postgres/Redis and a case-insensitive EICAR check; security job: Bandit clean at all severities (asserts replaced by explicit checks, reasoned nosec), Semgrep p/default with metrics off clean (all GitHub Actions pinned to commit SHAs, health-check SQL parameterised, protocol-mandated SHA-1/SNS cases annotated), uv 7-day dependency cooldown with dated exceptions for celery/types-markdown; pip-audit clean | Confirm the next scheduled nightly run is green |
