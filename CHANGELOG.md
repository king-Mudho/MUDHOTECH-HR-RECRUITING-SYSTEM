# Changelog

All notable changes to the MUDHOTECH HR RECRUITING SYSTEM are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]
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
