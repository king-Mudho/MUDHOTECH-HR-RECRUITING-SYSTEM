# 01 — Software Requirements Specification (Final)

**System:** MUDHOTECH HR RECRUITING SYSTEM (MHRS) · **Version:** 2.0 (finalised from Blueprint v1.0) · **Date:** 8 Nov 2026
**Vendor:** MudhoTech Solutions (Pvt) Ltd, Harare, Zimbabwe

Requirement IDs: `FR-<module>-<nn>` (functional), `NFR-<area>-<nn>` (non-functional). Phases reference these IDs.
Priority: **P0** = MVP (Phases 1–11), **P1** = Release 1.1 (Phases 12–14), **P2** = Release 1.2 (Phase 15).

---

## 1. Vision, problem, objectives

### 1.1 Problem
HR teams receive many differently formatted CVs and answers, apply inconsistent criteria and slow down as
volume grows. Qualified applicants get missed because of wording differences; decisions are poorly documented.

### 1.2 Vision
One secure, multi-company platform where organisations advertise jobs, receive applications, assess every
candidate against **approved, job-related, versioned criteria** with **traceable evidence**, and keep humans
accountable for every consequential decision.

### 1.3 Objectives (measurable at pilot)
| # | Objective | Pilot measure |
|---|---|---|
| O1 | No lost applications | 100/100 submitted applications accounted for in a 100-applicant test; 0 duplicates |
| O2 | Faster first review | Median time from deadline to HR-approved shortlist reduced vs manual baseline (measured in pilot) |
| O3 | Evidence-grounded AI | 100% of criterion results link to evidence or carry an explicit missing/uncertain flag |
| O4 | Qualified applicants not missed | Recall of HR reference "qualified" set within suggested-for-review group ≥ target agreed in pilot (default goal 0.90) |
| O5 | Human control | 0 consequential state changes without a human actor (verified by audit query) |
| O6 | Tenant isolation | 0 successful cross-tenant accesses in security test suite |
| O7 | Accessibility | WCAG 2.2 AA audit on candidate journey with no open critical issues |

### 1.4 Scope by release
| Release | Included | Excluded |
|---|---|---|
| **MVP (v1.0-pilot)** | Multi-tenant orgs, roles, MFA, vacancies + rubric approval, public job board, candidate portal, application wizard, uploads + malware scan, dynamic questionnaires, CV extraction + OCR, hybrid matching, explainable evaluation, clarification requests, shortlist approval, ATS states, email/in-app notifications, HR dashboard, audit log, privacy rights requests, production deployment | Billing, interviews/offers, talent pool, deep integrations |
| **v1.1** | Interviews + scorecards, offers + hiring, consent talent pool, advanced analytics + exports, platform admin, subscription plans + Paynow/EcoCash billing | HRIS sync |
| **v1.2** | Calendar sync (Google/Microsoft), SMS/WhatsApp Business (consented), outbound webhooks, public API keys, localisation (Shona/Ndebele UI strings), job board syndication feed | Fully autonomous hiring (never) |

### 1.5 Operating principles
Human-in-control · Evidence-first · Missing ≠ negative · Consistency (approved, versioned criteria) ·
Tenant isolation · Candidate dignity · Resilience · Data minimisation · Transparency to candidates.

---

## 2. Stakeholders, users, roles

| Role (code) | Scope | Key permissions | Restrictions |
|---|---|---|---|
| Platform Super Admin (`platform_admin`) | Platform | Tenants lifecycle, plans, system health, feature flags, break-glass support | No routine CV browsing; support access must be time-boxed, reasoned, logged, and visible to tenant |
| Platform Support (`platform_support`) | Platform | Read tenant metadata, assist with tickets | No candidate PII unless break-glass granted |
| Company Admin (`org_admin`) | Own org | Org profile, members, roles, policies, branding, retention settings | Cannot remove last org_admin |
| HR Manager (`hr_manager`) | Own org | Approve vacancies/rubrics, approve shortlists, decisions, offers | Only org vacancies (all or assigned, per org setting) |
| Recruiter (`recruiter`) | Assigned vacancies | Create drafts, manage applications, clarifications, communications, propose shortlist | Cannot approve own rubric/shortlist when dual-control is enabled |
| Hiring Manager (`hiring_manager`) | Assigned vacancies | View shortlist & evidence, comment, interview feedback | No candidate pool beyond shortlist unless granted |
| Interview Panel Member (`panelist`) | Assigned interviews | Submit scorecards | Only own interviews; no AI score visible (configurable, default hidden to avoid anchoring) |
| Auditor (`auditor`) | Own org (or platform) | Read audit/governance records, evaluation reconstructions | Read-only; PII redacted by default |
| Candidate (`candidate`) | Self | Profile, documents, applications, consents, rights requests, messages | Only own data |
| Anonymous visitor | Public | Browse published jobs, company pages | — |

A user may belong to **multiple organisations** (membership per org with its own role) and may also be a
candidate. Role is per membership, never on the user globally (except platform roles).

---

## 3. End-to-end workflows

### 3.1 Organisation onboarding
Sign-up → email verify → create org (name, registration no. optional, industry, country, city, website) →
org status `pending_verification` → platform admin verifies (or auto-verify by email domain policy) →
`active`. Unverified orgs can draft vacancies but **cannot publish** (default; configurable).

### 3.2 Vacancy lifecycle
`draft → in_review → approved → scheduled | published → paused ⇄ published → closed → archived`
- Publishing requires: mandatory fields, ≥1 essential criterion, rubric with weights summing to 100,
  approved questionnaire, deadline in the future (job timezone), ≥1 assigned recruiter, privacy notice,
  org verified, HR manager approval.
- Editing a published vacancy's criteria/questions creates a new **job version**; existing applications stay
  bound to the version they applied under; re-evaluation is explicit and versioned.
- Vacancies with applications can never be hard-deleted (only archived).

### 3.3 Application lifecycle (state machine)
| State | Entered by | Allowed next |
|---|---|---|
| `draft` | Candidate starts | `submitted`, `abandoned` (auto after deadline/inactivity) |
| `submitted` | Validated submit (idempotent) | `processing`, `withdrawn` |
| `processing` | Outbox event | `under_review`, `needs_information`, `processing_error` |
| `processing_error` | Worker failure after retries | `processing` (retry), `under_review` (manual review) |
| `needs_information` | Clarification request sent | `processing` (on answer), `under_review`, `withdrawn` |
| `under_review` | Evidence ready | `shortlisted`*, `on_hold`, `not_selected`*, `needs_information`, `withdrawn` |
| `on_hold` | HR action | `under_review`, `shortlisted`*, `not_selected`* |
| `shortlisted` | **Human approval** | `interview`, `not_selected`*, `withdrawn` |
| `interview` | Interview scheduled | `offer`*, `not_selected`*, `withdrawn` |
| `offer` | **Approved offer issued** | `hired`*, `offer_declined`, `withdrawn` |
| `hired` / `not_selected` / `withdrawn` / `offer_declined` / `abandoned` | Terminal | `under_review` via authorised **reopen** with reason |

`*` requires human actor + reason; recorded in `application_status_events` + `audit_events`.
AI recommendation (`recommended`, `needs_review`, `insufficient_evidence`) is a **separate field** on the
evaluation — never an application status.

### 3.4 Screening workflow
Submission → scan → extract → normalise → match → evaluate → explain → `under_review` → HR reviews list
(with filters: recommendation, evidence completeness, flags) → HR opens candidate (evidence viewer) →
verify/correct claims (human-verified) → propose shortlist (desired size configurable) → approve
(single or dual control) → notifications queued (with optional delay to allow undo, default 15 min).

### 3.5 Clarification workflow
Recruiter selects question template or free text → candidate notified (email + in-app) → candidate answers
in portal (with optional upload) before due date → answer stored as `candidate-reported` evidence →
re-evaluation queued as a new evaluation version → recruiter notified.

### 3.6 Candidate rights workflow
Candidate submits request (access/export, correction, deletion, objection to automated processing,
withdraw consent) → identity confirmed by session + email re-verification → routed to the controller
(organisation) and/or platform → due date tracked (default 30 days, configurable) → completed with audit.

---

## 4. Functional modules (24)

Format: purpose · requirements (FR) · acceptance (AC). Edge cases → `docs/07_EDGE_CASES.md`.

### M01 Authentication & identity (P0)
- FR-M01-01 Candidate self-registration (email + password), email verification required before submitting.
- FR-M01-02 Staff join only via organisation invitation (expiring, single-use token) or org creation.
- FR-M01-03 Login/logout, password reset, change password, session list + revoke, "log out all devices".
- FR-M01-04 TOTP MFA + recovery codes; **mandatory** for platform roles, org_admin, hr_manager; optional others.
- FR-M01-05 Rate limiting + progressive lockout; generic error messages (no account enumeration).
- FR-M01-06 Password policy: min 10 chars, breached-password check (offline list), no composition rules.
- FR-M01-07 Email change requires re-verification of new address and notice to old address.
- FR-M01-08 Account deletion request routes through rights workflow (M22).
- AC: roles cannot be self-assigned; candidates see only their records; locked accounts unlock by time or reset.

### M02 Organisation management (P0)
- FR-M02-01 Create org; slug unique; logo upload (image validated, resized); public careers page `/companies/[slug]`.
- FR-M02-02 Departments, locations (city, country, remote policy), default timezone (default `Africa/Harare`), default currency.
- FR-M02-03 Org policies: privacy notice text, retention period, duplicate-application policy, shortlist dual-control, AI features enabled, LLM allowed (default off), notification delay.
- FR-M02-04 Org status: `pending_verification`, `active`, `suspended`, `closed`. Suspended → staff read-only, public jobs hidden, candidates see "recruitment paused".
- FR-M02-05 Org switcher for users in multiple orgs; active org in session; every API request resolves org from membership, not body.
- AC: Company A cannot read, list, count, search or export Company B data (automated tests per endpoint).

### M03 HR teams, roles & assignments (P0)
- FR-M03-01 Invite member (email, role, optional vacancy assignments); resend; revoke; expiry 7 days.
- FR-M03-02 Change role, deactivate member (sessions revoked, assignments transferred prompt).
- FR-M03-03 Vacancy assignment: recruiters, hiring managers, approvers.
- FR-M03-04 Approval chains: job publication approver(s); shortlist approver(s); dual control toggle.
- FR-M03-05 Prevent removing/demoting the last `org_admin`.
- AC: restricted users get 403 (with error code) server-side for prohibited actions.

### M04 Vacancy creation & management (P0)
- FR-M04-01 5-step wizard: Details → Requirements → Questionnaire → Assessment rubric → Preview & submit for approval; autosave.
- FR-M04-02 Fields: title, department, location(s), workplace type (on-site/hybrid/remote), employment type (full-time, part-time, contract, internship, attachment/industrial attachment, temporary, graduate trainee), seniority, openings count, summary, responsibilities (rich text, sanitised), salary (min/max/currency/period/disclose flag), benefits, closing date+time+timezone, start date, required documents, accommodation contact, internal reference.
- FR-M04-03 Criteria: list of criteria each with `type` (skill, experience, qualification, certification, competency, language, licence, eligibility), `importance` (essential/preferred), description, evidence guidance, accepted equivalents (taxonomy links, free-text alternatives), min years (optional), weight category.
- FR-M04-04 Rubric: 5 default categories (technical skills 35, relevant experience 25, job competencies 20, qualifications 10, screening answers 10) — editable; weights must sum to 100; each category has scoring guidance bands (0/25/50/75/100 descriptors).
- FR-M04-05 Justification required for each essential criterion (text) — supports fairness review.
- FR-M04-06 Approval: submit → HR manager approves/rejects with comments; approved version locked (immutable `job_version`).
- FR-M04-07 Publish now / schedule; pause; resume; close (manual or auto at deadline); extend deadline (logged, notifies draft holders); archive; duplicate as new draft; repost.
- FR-M04-08 AI assist (optional, flag): suggest criteria/questions from description — always shown as suggestions requiring explicit acceptance; never auto-applied.
- FR-M04-09 Optimistic locking (`version` field) to prevent concurrent edit overwrites.
- AC: cannot publish until all checks pass; published criteria immutable; changes → new version.

### M05 Public job board & careers pages (P0)
- FR-M05-01 Public listing with full-text search (title, skills, description), filters: location, workplace type, employment type, organisation, posted date, closing soon; sort; pagination.
- FR-M05-02 Job detail page: SEO metadata, schema.org `JobPosting` JSON-LD, Open Graph image, share links (WhatsApp, LinkedIn, copy).
- FR-M05-03 Closed jobs: page stays (HTTP 200 with "closed" banner + `noindex`) for 90 days, then 410.
- FR-M05-04 Company careers page lists that org's open jobs.
- FR-M05-05 Sitemap + RSS/JSON feed of open jobs.
- FR-M05-06 Low-bandwidth friendly (server-rendered, small JS, image optimisation).
- AC: paused/closed/draft jobs never accept new submissions; visibility rules correct.

### M06 Candidate accounts & profiles (P0)
- FR-M06-01 Profile: name, preferred name, email, phone (E.164), city/country, headline, summary, links (LinkedIn, GitHub, portfolio), work experience, education, certifications, skills, languages, availability/notice period.
- FR-M06-02 **No collection** of DOB, gender, ID number, marital status, religion, tribe, photo, health in core profile. (Org-level special fields allowed only via M08 eligibility questions approved as job-related, e.g. "valid driver's licence class 4?").
- FR-M06-03 CV library: multiple CVs, set default, view parse result, correct extracted data (corrections stored, originals retained).
- FR-M06-04 Profile prefill from parsed CV (candidate confirms).
- FR-M06-05 Notification preferences; consent records; privacy centre.
- AC: one account, many independent applications; no cross-job leakage.

### M07 Application & document submission (P0)
- FR-M07-01 6-step wizard: Contact & privacy → Profile/experience → Documents → Questions → Review (incl. extracted data correction) → Submit; autosave every change (debounced) and resume across devices.
- FR-M07-02 Upload via presigned URL; allowed: PDF, DOCX (CV); PDF, JPG, PNG, DOCX (supporting); default max 10 MB/file, 25 MB/application (configurable); magic-byte check; antivirus; page limit 30 (CV).
- FR-M07-03 Submission is **idempotent** (client `Idempotency-Key` header) and atomic; returns reference `MHRS-<ORG>-<YYYY>-<6 digits>`.
- FR-M07-04 Receipt email + in-app; status timeline in candidate portal.
- FR-M07-05 Withdraw application (reason optional); stops processing; notifies assigned recruiter.
- FR-M07-06 Duplicate policy per org/job: `one_active` (default), `allow_resubmit_replace` (before deadline), `allow_multiple`.
- FR-M07-07 Deadline enforcement server-side in job timezone; drafts after deadline → `abandoned` + email.
- FR-M07-08 Accessibility alternative: "Need help applying?" contact route; staff can create an **assisted application** on behalf of a candidate (flagged, consent recorded).
- AC: persisted once despite retries; AI/scan failure never loses the application.

### M08 Dynamic screening questionnaires (P0)
- FR-M08-01 Question types: yes/no, single choice, multiple choice, number (min/max/unit), short text, long text (word limit), date, file upload, scale (1–5), eligibility/knock-out (see rule below), availability/notice period, salary expectation (optional, never scored by default).
- FR-M08-02 Sections, ordering, required/optional, help text, conditional branching (show if answer X), per-question evidence prompts.
- FR-M08-03 Scoring rubric per question (expected answers, points, keywords/criteria for text with human or AI-assisted scoring, "not scored" option).
- FR-M08-04 **Knock-out questions never auto-reject**: they set flag `eligibility_unmet`, routing to human review with recommendation `not_eligible_review`.
- FR-M08-05 Question bank per org (reusable templates); AI-suggested questions require approval.
- FR-M08-06 Prohibited-question linter: warns/blocks questions about protected characteristics (age, religion, tribe, marital, pregnancy, HIV, disability, political affiliation) unless a documented lawful job-related exception is recorded by HR manager.
- AC: comparable applicants get equivalent questions; answers saved in drafts; rubric versioned with job version.

### M09 CV ingestion & extraction (P0)
- FR-M09-01 Pipeline per document: signature check → AV scan → text extraction (PyMuPDF → pdfplumber fallback; python-docx; OCR when text density low) → quality score → structured parse → evidence records.
- FR-M09-02 Extract: contact (for dedupe only), work history (employer, title, start/end, current flag, responsibilities), education (institution, qualification, level, field, dates, grade where stated), certifications, skills (taxonomy-normalised), languages, projects, publications, licences, links.
- FR-M09-03 Each claim stores: page, bounding text snippet, char offsets, extraction method, confidence, status (`explicit`/`inferred`).
- FR-M09-04 Date normalisation for formats like "Jan 2020 – Present", "2019-21", "03/2018", "Since 2020"; overlapping roles handled; experience months computed without double counting overlaps.
- FR-M09-05 Detect: encrypted/password PDF, image-only, corrupted, empty, non-CV (e.g. certificate uploaded as CV), language not supported → flags + candidate notification to re-upload (application kept).
- FR-M09-06 Protected/irrelevant data (DOB, ID numbers, gender, marital status, photo) detected and **excluded** from evaluation inputs and LLM payloads.
- AC: never invents facts; unsupported docs flagged; extraction accuracy measured on benchmark set.

### M10 Candidate–job matching (P0)
- FR-M10-01 Deterministic checks: qualification level ≥ required (via equivalence table), certifications/licences present, min experience months, language.
- FR-M10-02 Skill matching: exact taxonomy ID → synonym/alias → related-skill graph → semantic similarity (embeddings) with threshold; each match records method + confidence.
- FR-M10-03 Experience relevance: role/responsibility semantic similarity to job responsibilities; recency weighting optional (off by default).
- FR-M10-04 Questionnaire answers matched against question rubrics; CV vs answer conflicts flagged.
- FR-M10-05 Evidence status per criterion: explicit / candidate-reported / inferred / missing / conflicting / human-verified.
- AC: same rubric version + same evidence + same engine version ⇒ identical results (deterministic; LLM parts cached by hash).

### M11 Explainable evaluation (P0)
- FR-M11-01 Per-criterion result: score 0–100 (or `not_assessable`), evidence links, rationale, gaps, uncertainty.
- FR-M11-02 Category scores and weighted total `S = Σ wᵢsᵢ`; **coverage** (% of weight with assessable evidence) and **confidence** shown alongside score.
- FR-M11-03 Recommendation band: `recommended_for_review`, `review_needed` (uncertain/conflict/low coverage), `eligibility_review` (knock-out unmet), `lower_match`. Never "reject".
- FR-M11-04 Natural-language summary (template-based; LLM optional) — every sentence must cite evidence IDs; grounding validator rejects uncited claims.
- FR-M11-05 Suggested clarification questions for gaps.
- FR-M11-06 Record versions: job_version, rubric_version, engine_version, taxonomy_version, model ids, prompt hash.
- AC: recruiter can trace every material result to a source or flag.

### M12 Shortlist review & approval (P0)
- FR-M12-01 Applicants table: sort/filter by recommendation, score, coverage, flags, status, criteria met; saved views; pagination (handles 5,000+ applicants).
- FR-M12-02 Candidate review page: CV viewer (PDF render) with highlighted evidence, criteria panel, answers, flags, history, notes (internal, @mentions), verify/correct claim.
- FR-M12-03 Compare up to 4 candidates side by side.
- FR-M12-04 Blind review mode (default on for first-pass): hides name, photo, contact, address, institution names optional — reduces bias.
- FR-M12-05 Propose shortlist (desired size), bulk actions with reasons, approval request, dual-control approval, undo window before notifications.
- FR-M12-06 "Not selected" requires reason category (+optional note) and human confirmation; bulk not-selected requires confirmation listing count and showing low-coverage candidates separately.
- FR-M12-07 Override tracking: when HR decision differs from AI band, capture reason (feeds AI quality monitoring).
- AC: no consequential rejection from AI score/ranking alone; all uncertain cases visible before approval.

### M13 Applicant tracking (P0)
- FR-M13-01 Central transition service enforcing §3.3; timeline UI; who/when/from/to/reason.
- FR-M13-02 Kanban pipeline view per vacancy (drag = transition request with validation + reason modal).
- FR-M13-03 Handle holds, reopen, withdrawals, duplicates merge (staff-assisted), expired vacancies.
- FR-M13-04 Tags, internal notes, ratings (human), assignment of application to recruiter.
- AC: all transitions validated and auditable.

### M14 Notifications (P0)
- FR-M14-01 Transactional outbox → Celery → provider; delivery log; retries with backoff; dedupe key; suppression list (bounces/complaints).
- FR-M14-02 Templates per org (with safe variables, preview, versioning), default templates: receipt, clarification request, shortlisted, not selected (respectful), interview invite, offer, withdrawal confirmation, deadline reminder (draft), document re-upload request, rights request updates.
- FR-M14-03 In-app notifications (bell, unread counts) for staff and candidates.
- FR-M14-04 No sensitive details (scores, evaluations) in emails; links to portal.
- FR-M14-05 Quiet sending: batch "not selected" emails with configurable delay; never before human approval.
- AC: failures visible and retried; no uncontrolled duplicates.

### M15 HR dashboard & basic reporting (P0)
- FR-M15-01 Cards: open vacancies, applications (today/7d), processing queue, processing errors, pending reviews, clarifications outstanding, shortlist approvals pending.
- FR-M15-02 Per-vacancy funnel: submitted → processed → reviewed → shortlisted (→ interviewed → offered → hired in v1.1).
- FR-M15-03 Filters: department, vacancy, recruiter, date range. AI recommendations vs human decisions shown distinctly.
- AC: totals reconcile with underlying tenant-scoped records (reconciliation test).

### M16 Interviews (P1)
- Schedule (single/panel, in-person/video/phone), timezone-aware slots, candidate self-booking from offered slots, invitations with ICS, reminders, reschedule/cancel with reasons, conflict detection, structured scorecards per criterion (1–5 + evidence notes), independent submission before seeing others' scores, consolidated recommendation, no-show handling.
- AC: panelists see only their interviews; AI score hidden from panelists by default.

### M17 Offers & hiring (P1)
- Offer draft (salary, currency, start date, contract type, conditions, expiry), approval chain, generate PDF offer letter from template, issue via portal, candidate accept/decline (with e-acceptance record: timestamp, IP, typed name), expiry handling, counter-offer note, hire record, close vacancy when openings filled (prompt), notify remaining candidates (with human confirmation).
- AC: offers cannot be issued without required approvals; hire record separate from screening data.

### M18 Consent-based talent pool (P1)
- Candidate opt-in per organisation (never cross-org by default), duration (default 12 months), reconfirmation reminder, search within permitted profiles, invite to apply, opt-out and deletion.
- AC: applying to one role never exposes a CV to another employer.

### M19 Advanced analytics & exports (P1)
- Time-to-review, time-to-shortlist, time-to-hire, funnel conversion, source of applicants (UTM), questionnaire completion/drop-off, processing quality (parse failure rate, OCR rate), AI–human agreement & override rates, recall monitoring on validation sets, diversity monitoring only where lawful/voluntary & aggregated (k-anonymity ≥ 10).
- Exports XLSX/CSV/PDF: permissioned, formula-injection safe, time-bounded download links, logged.

### M20 Platform administration, subscriptions & billing (P1)
- Tenant provisioning/verification/suspension, plans (Free trial, Starter, Growth, Enterprise) with limits (active vacancies, seats, AI evaluations/month, storage), usage metering, invoices, Paynow (EcoCash/OneMoney/Visa/Mastercard) integration, USD + ZWG pricing, grace periods, dunning emails, feature flags, system health, queue monitoring, break-glass support access (time-boxed, reason, visible to tenant).

### M21 External integrations (P2)
- Google Calendar / Microsoft 365 calendar, SMS (local aggregator) and WhatsApp Business Cloud API with opt-in & approved templates, outbound webhooks (signed HMAC, retries), public REST API keys per org (scoped), job syndication XML feed, SSO (Google/Microsoft) for staff, integration health and credential rotation.

### M22 Audit, privacy & governance (P0)
- Immutable audit events (append-only table, hash-chained), access logging for viewing candidate PII/CVs, rubric changes, screening runs, overrides, exports, logins, permission changes.
- Data subject rights: access/export (JSON + PDF), correction, deletion/anonymisation, objection to automated processing (routes to fully manual review), consent withdrawal.
- Retention engine: per-org schedule; anonymise unsuccessful applications after N months post-closure (default 12); legal hold flag; deletion of files from storage; audit of retention runs.
- AI governance: model registry (name, version, purpose, data, limitations), evaluation reports, incident log, fairness monitoring jobs.
- Reconstruct: any evaluation and decision can be reconstructed (inputs refs, versions, outputs, human actions).

### M23 Clarifications & candidate messaging (P0)
- Structured clarification requests (templates + free text + optional upload) with due date; candidate portal inbox; secure staff↔candidate message threads per application; message templates; attachments scanned; read receipts in-app; all messages tenant-scoped and audited.

### M24 Skills taxonomy & qualification equivalence (P0)
- Platform skills taxonomy (seeded: software/IT, finance/accounting, engineering, health admin, sales/marketing, logistics, education, agriculture, mining, NGO/development) with aliases & related skills; org-level custom skills.
- Qualification framework mapping incl. Zimbabwe: ZIMSEC O-Level, A-Level, Cambridge IGCSE/AS/A, National Certificate (NC), National Diploma (ND), Higher National Diploma (HND), Bachelor's (Hons), Postgraduate Diploma, Master's, PhD; professional bodies (ACCA, CIMA, ICAZ/CA(Z), CIPS, IoDZ, ZIE/ECZ engineering registration, Nursing Council of Zimbabwe, Law Society of Zimbabwe), international equivalents; levels used for "minimum qualification" checks with HR-editable equivalence rules.
- Admin UI for taxonomy curation; versioned taxonomy (`taxonomy_version`) referenced by evaluations.

---

## 5. Non-functional requirements

| ID | Area | Requirement |
|---|---|---|
| NFR-PERF-01 | Performance | P95 API latency < 400 ms for list/detail endpoints at pilot load (excl. file transfer) |
| NFR-PERF-02 | Throughput | Process 100 CVs end-to-end in ≤ 15 min on 2 worker processes (4 vCPU / 8 GB); 1,000 in ≤ 2 h; measured in Phase 10 |
| NFR-PERF-03 | Frontend | Public job pages LCP < 2.5 s on simulated 3G "Fast" mobile; JS < 200 KB gz for public routes |
| NFR-SCAL-01 | Scalability | Workers horizontally scalable per queue; stateless web tier |
| NFR-AVAIL-01 | Availability | Pilot target 99.5% monthly for public job board & submission |
| NFR-REL-01 | Reliability | Zero lost submissions under worker/Redis/S3 failure injection tests |
| NFR-SEC-01 | Security | OWASP ASVS L2 controls for auth, session, access control, input validation, files |
| NFR-SEC-02 | Security | No critical/high findings open at go-live (SAST, dependency, container scans, manual pen-test checklist) |
| NFR-PRIV-01 | Privacy | Data minimisation, retention engine, rights workflows, DPIA documented |
| NFR-ACC-01 | Accessibility | WCAG 2.2 AA for candidate & HR core journeys |
| NFR-MAINT-01 | Maintainability | Backend coverage ≥ 85% for `apps/` services & `ai_engine/`; frontend critical components tested |
| NFR-OBS-01 | Observability | Structured logs with request_id, Sentry, queue metrics, health endpoints `/healthz` `/readyz` |
| NFR-DR-01 | Recovery | RPO ≤ 24 h (daily backups + WAL/point-in-time if RDS), RTO ≤ 4 h; restore rehearsed |
| NFR-I18N-01 | Localisation | All UI strings externalised; English default; dates/currency localised |
| NFR-BW-01 | Low bandwidth | Resumable/retryable uploads, autosave, works on Android Chrome 2 GB RAM devices |
| NFR-BROWSER-01 | Compatibility | Last 2 versions of Chrome, Edge, Firefox, Safari; Android Chrome; iOS Safari |

## 6. Constraints & assumptions
- Development on Windows (D: drive) with Docker Desktop (WSL2); production on AWS EC2 Ubuntu 24.04.
- English-language CVs for MVP; other languages flagged `language_unsupported` for manual review.
- No model training on customer CVs. Embeddings computed locally. External LLM off by default.
- Legal applicability (CDPA, SI 155/2024, POTRAZ licensing) to be confirmed by counsel before production.
