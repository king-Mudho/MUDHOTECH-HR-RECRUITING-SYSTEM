# Changelog

All notable changes to the MUDHOTECH HR RECRUITING SYSTEM are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Added
- Phase 09 privacy, governance & security hardening: data-subject rights requests with export bundles,
  erasure with legal holds and erasure verification, retention engine, break-glass support access,
  PostgreSQL row-level security, security headers and CSP, nightly security scanning, ASVS L2 checklist,
  AI kill-switch with model registry UI, model card and AI policy, DPIA and DPA template (for legal
  review), accessibility pass, organisation closure, public privacy notice, terms and accessibility pages.

### Changed
- Minimum password length is now 12 characters.
- The Django admin is only mounted when `ENABLE_DJANGO_ADMIN` is set (on in development).

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
