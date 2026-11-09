# PHASE 03 — Vacancy Management, Taxonomy & Public Job Board

**Release:** MVP · **Modules:** M04, M05, M24 (base), M08 (questionnaire builder data model) · **Depends on:** Phase 02
**Read first:** `docs/01 M04, M05, M08, M24`, `docs/03 jobs/taxonomy/questionnaires`, `docs/04 Jobs/Taxonomy`, `docs/08 §2–3`, `docs/07 C`

## Goal
HR can build a vacancy with criteria, rubric and questionnaire via a 5-step wizard, get it approved, publish/schedule,
pause/close; candidates can discover jobs on a fast, SEO-friendly, accessible public job board.

## Tasks
- [x] **P03-T01** — `apps.taxonomy`: models (skills, aliases, relations, qualification levels/aliases, professional bodies, taxonomy versions); seed data files `backend/fixtures/taxonomy/*.json` — ≥ 600 skills across sectors listed in SRS M24 with aliases (e.g. "JS"→JavaScript, "Postgres"→PostgreSQL, "MS Excel"→Excel), relations (Django implies Python; React implies JavaScript), Zimbabwe qualification framework + aliases, professional bodies; `load_taxonomy` command (idempotent, versioned); autocomplete API (`pg_trgm` similarity).
- [x] **P03-T02** — `apps.jobs` models: Job, JobVersion, JobCriterion, Rubric, JobApproval, JobAssignment, JobEvent; slug generation (stable after publish, redirects table for renamed slugs); search_vector trigger/update; optimistic locking (`lock_version`).
- [x] **P03-T03** — `apps.questionnaires` models: Questionnaire, Question, QuestionOption, (QuestionResponse table created now, used in Phase 4); question bank templates (`is_template`); branching schema validation (no cycles; references only earlier questions); scoring config validation per type.
- [x] **P03-T04** — Prohibited-question linter (`questionnaires/linter.py`): keyword/phrase lexicon (age, date of birth, religion, church, tribe, totem, marital, married, pregnant, children, HIV, disability, political party, ZANU/MDC/CCC party names, national ID) + regex; returns warnings with explanation; HR manager can record `protected_exception_reason` (audited). Tests with positive/negative samples.
- [x] **P03-T05** — Job services: create draft, update (lock), set criteria (validate essential justification), set rubric (weights = 100, bands present), set questionnaire, **publish-readiness lint** (all checks from SRS §3.2 returned as checklist), submit for approval, approve/reject (dual-control rule when policy on), publish/schedule/pause/resume/close/archive/extend/duplicate/new-version; every transition → JobEvent + audit + outbox (`job.published`, `job.closed`).
- [x] **P03-T06** — Beat tasks: publish scheduled jobs; auto-close at `closes_at` (job TZ aware); idempotent; catch-up after downtime (EC-JOB-18).
- [ ] **P03-T07** — Job assignments + `IsAssignedToJob` permission (hr_manager sees all org jobs; recruiter/hiring_manager only assigned).
- [ ] **P03-T08** — AI assist stub (feature-flagged, default off): `POST /hr/jobs/{id}/ai-suggestions` returns criteria/question suggestions from deterministic heuristics (taxonomy skill extraction from description); UI shows as suggestions requiring accept. (LLM adapter wiring comes in Phase 7.)
- [ ] **P03-T09** — Sanitisation: `nh3` allow-list for rich text (p, br, strong, em, ul, ol, li, h2–h4, a[href] with rel) applied server-side on save; XSS test payload suite (EC-JOB-12).
- [ ] **P03-T10** — Public APIs: list with FTS + filters + sort + pagination; detail by slug; questions for published version; company profile with open jobs; sitemap.xml & jobs feed (RSS/JSON). Closed jobs: 200 + closed flag for 90 days then 410 (EC visibility rules).
- [ ] **P03-T11** — HR APIs per `docs/04` Jobs section with OpenAPI; register all in cross-tenant and permission matrix tests.
- [ ] **P03-T12** — Frontend HR: `/hr/jobs` table (status filters, search), 5-step job wizard (Details → Requirements (criteria builder with taxonomy autocomplete, essential/preferred, justification, equivalents) → Questionnaire builder (types, options, branching UI, scoring, linter warnings inline, insert from question bank) → Rubric (weights sliders with running total = 100, band descriptors) → Preview (public-page preview + readiness checklist)); autosave with lock conflict handling; job overview page with status actions & version history; approval UI for HR managers.
- [ ] **P03-T13** — Frontend public: `/` home with search, `/jobs` (SSR, URL filters, pagination), `/jobs/[slug]` (deadline in job TZ + viewer local TZ, essential vs preferred, required documents, Apply CTA, share buttons incl. WhatsApp, JSON-LD JobPosting, OG tags), `/companies/[slug]`; ISR/revalidate 60 s; closed banner + noindex.
- [ ] **P03-T14** — Seed: `seed_demo` extended with 2 orgs and 3 published jobs (Software Developer per Blueprint Appendix A, Accountant, Registered Nurse) with full criteria/rubrics/questionnaires.

## Edge cases
EC-JOB-01..19 (EC-JOB-20 deferred to v1.1: implement `unlisted` visibility only).

## Exit criteria
- [ ] A recruiter creates the Software Developer vacancy, HR manager approves, it appears publicly and is searchable.
- [ ] Publishing blocked with clear checklist when invalid; criteria immutable after approval (new version flow works).
- [ ] Lighthouse (mobile) on `/jobs` and `/jobs/[slug]`: Performance ≥ 85, Accessibility ≥ 95, SEO ≥ 95.
- [ ] Tests for listed EC ids; cross-tenant suite includes all new endpoints.
