# PROGRESS.md — MUDHOTECH HR RECRUITING SYSTEM

> **Single source of truth for implementation progress.** Every agent session: read this after `CLAUDE.md`,
> work on the **Current task**, then update this file (tick tasks, update pointers, append to the session log).
> Task details live in the phase files; keep both in sync.

## Current pointer
- **Current phase:** 03 — Vacancy Management, Taxonomy & Public Job Board
- **Current task:** P03-T03
- **Last updated:** 2026-11-09
- **Overall:** 33 / 193 tasks · 2 / 16 phases

## Phase status
| # | Phase | Release | Tasks | Status | Closed on |
|---|---|---|---|---|---|
| 01 | [Foundation & Development Environment](phases/PHASE_01_FOUNDATION.md) | MVP | 17 | ✅ Done | 2026-11-08 |
| 02 | [Identity, Tenancy & Access Control](phases/PHASE_02_IDENTITY_TENANCY_ACCESS.md) | MVP | 14 | ✅ Done | 2026-11-09 |
| 03 | [Vacancy Management, Taxonomy & Public Job Board](phases/PHASE_03_VACANCIES_JOB_BOARD.md) | MVP | 14 | 🟦 In progress | |
| 04 | [Candidate Portal, Documents, Applications & Questionnaires](phases/PHASE_04_CANDIDATE_PORTAL_APPLICATIONS.md) | MVP | 16 | ⬜ Not started | |
| 05 | [ATS Workflow, Notifications & Messaging](phases/PHASE_05_ATS_NOTIFICATIONS_MESSAGING.md) | MVP | 11 | ⬜ Not started | |
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
- [ ] P03-T03 — `apps.questionnaires` models: Questionnaire, Question, QuestionOption, (QuestionResponse table created now, used in …
- [ ] P03-T04 — Prohibited-question linter (`questionnaires/linter.py`): keyword/phrase lexicon (age, date of birth, religion, …
- [ ] P03-T05 — Job services: create draft, update (lock), set criteria (validate essential justification), set rubric (weights = …
- [ ] P03-T06 — Beat tasks: publish scheduled jobs; auto-close at `closes_at` (job TZ aware)
- [ ] P03-T07 — Job assignments + `IsAssignedToJob` permission (hr_manager sees all org jobs
- [ ] P03-T08 — AI assist stub (feature-flagged, default off): `POST /hr/jobs/{id}/ai-suggestions` returns criteria/question …
- [ ] P03-T09 — Sanitisation: `nh3` allow-list for rich text (p, br, strong, em, ul, ol, li, h2–h4, a[href] with rel) applied …
- [ ] P03-T10 — Public APIs: list with FTS + filters + sort + pagination
- [ ] P03-T11 — HR APIs per `docs/04` Jobs section with OpenAPI
- [ ] P03-T12 — Frontend HR: `/hr/jobs` table (status filters, search), 5-step job wizard (Details → Requirements (criteria builder …
- [ ] P03-T13 — Frontend public: `/` home with search, `/jobs` (SSR, URL filters, pagination), `/jobs/[slug]` (deadline in job TZ + …
- [ ] P03-T14 — Seed: `seed_demo` extended with 2 orgs and 3 published jobs (Software Developer per Blueprint Appendix A, …
- [ ] P03-EXIT — All exit criteria verified with evidence

### Phase 04 — Candidate Portal, Documents, Applications & Questionnaires  (`phases/PHASE_04_CANDIDATE_PORTAL_APPLICATIONS.md`)
- [ ] P04-T01 — `apps.candidates`: profile + experiences/educations/certifications/skills/languages models & CRUD APIs
- [ ] P04-T02 — `apps.documents`: UploadSession + Document models
- [ ] P04-T03 — Scan pipeline (documents queue): magic-byte detection (`python-magic` + custom DOCX/PDF checks), DOCX zip-bomb …
- [ ] P04-T04 — Orphan cleanup beat task (upload sessions expired, objects in quarantine > 24 h) (EC-APP-08)
- [ ] P04-T05 — `apps.applications` models: Application (+ reference counter table), ApplicationDocument, ApplicationStatusEvent, …
- [ ] P04-T06 — Application state machine module `applications/state_machine.py` implementing all transitions from SRS §3.3 with …
- [ ] P04-T07 — Draft APIs: create/resume draft, autosave PATCH with lock_version, attach documents by role, bulk upsert answers …
- [ ] P04-T08 — Submit service: `@idempotent`, `atomic`, checks (email verified, job published & before deadline in job TZ, org …
- [ ] P04-T09 — Withdraw service (any non-terminal state
- [ ] P04-T10 — Consent records: application processing consent + AI-assisted screening notice version stored on submit
- [ ] P04-T11 — Assisted application (staff creates on behalf
- [ ] P04-T12 — Frontend `FileUploader` (presign → PUT with progress → complete → poll scan status
- [ ] P04-T13 — Frontend candidate: `/candidate/dashboard`, `/candidate/profile` (sections + completeness), `/candidate/documents` …
- [ ] P04-T14 — Frontend `/apply/[jobId]` wizard per `docs/08 §3.1`: autosave indicator, resume at last step, conditional questions …
- [ ] P04-T15 — HR minimal list: `/hr/jobs/[id]/applications` basic table (status, submitted at, candidate name) + application …
- [ ] P04-T16 — E2E: candidate registers → verifies (Mailpit API) → applies with CV + answers → receives receipt
- [ ] P04-EXIT — All exit criteria verified with evidence

### Phase 05 — ATS Workflow, Notifications & Messaging  (`phases/PHASE_05_ATS_NOTIFICATIONS_MESSAGING.md`)
- [ ] P05-T01 — `apps.notifications` models: NotificationTemplate (platform defaults + org overrides, versioned), Notification …
- [ ] P05-T02 — Default templates (en): application_received, document_rejected_reupload, clarification_requested, …
- [ ] P05-T03 — Delivery pipeline: outbox consumers → `send_notification` task (notifications queue) → provider backend (SMTP/SES …
- [ ] P05-T04 — SES/SMTP bounce & complaint webhook endpoint (SNS signature verification) → suppression + in-app banner to update …
- [ ] P05-T05 — In-app notifications API (list, unread count, mark read/all) + `NotificationBell` component with polling (30 s) or SSE
- [ ] P05-T06 — `apps.messaging`: ClarificationRequest (templates + free text + optional upload, due_at), candidate answer endpoint …
- [ ] P05-T07 — ATS features: notes (@mentions → in-app notification), tags, assign recruiter, reopen with reason, holds
- [ ] P05-T08 — Frontend HR: pipeline kanban view per vacancy (columns = statuses
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

## Deviations from spec
| Date | Phase/Task | Deviation | Reason | ADR |
|---|---|---|---|---|
| 2026-11-08 | P01-T03 | Minimal `accounts.User` (email login) and `organisations.Organisation` created in Phase 01 | Custom user model must exist before the first auth migration; `TenantModel` needs its FK target. Phase 02 completes both. | — |
| 2026-11-08 | P01-T08/T10 | Dev S3 = SeaweedFS instead of MinIO | MinIO images no longer pullable | ADR-021 |
| 2026-11-08 | P01-T10 | Dev host ports Postgres 55432 / Redis 6380 (configurable) | Port clashes on dev machines | ADR-022 |
| 2026-11-08 | P01-T03 | Django admin served at `/django-admin/` | `/admin` belongs to the Next.js platform-admin UI | — |
| 2026-11-09 | P02-T01 | Bundled breached-password list = Django common-password corpus (19,640 SHA-1 hashes), not top-100k | No vetted 100k list bundled offline; `build_breached_passwords --source` + `BREACHED_PASSWORDS_FILE` let ops swap in a larger list | — |
| 2026-11-09 | P02-T01/T04 | Session metadata via `allauth.usersessions.UserSession` instead of a custom `UserSessionMeta` model | Same fields (ip, user_agent, created, last_seen), maintained by allauth; `/me/sessions` API built on top; IP truncation added in Phase 09 retention | — |

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
