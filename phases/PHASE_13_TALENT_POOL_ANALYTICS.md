# PHASE 13 — Consent-Based Talent Pool, Advanced Analytics & Exports

**Release:** v1.1 · **Modules:** M18, M19 · **Depends on:** Phase 12
**Read first:** `docs/01 M18–M19`, `docs/05 §13`, `docs/06 §4`

## Tasks
- [x] **P13-T01** — `apps.talentpool`: TalentPoolEntry linked to ConsentRecord (purpose `talent_pool`, per organisation, duration default 12 months); opt-in at application end and from candidate privacy page; reconfirmation reminder 30 days before expiry; opt-out & deletion.
- [x] **P13-T02** — Talent search (HR): FTS + skill/qualification filters over **consented** profiles only (org-scoped); "invite to apply" to a vacancy (notification); never exposes CVs across orgs (test).
- [x] **P13-T03** — Analytics selectors/materialised views (refresh nightly + on-demand): time-to-review, time-to-shortlist, time-to-hire, funnel conversion per stage, source of applicants (UTM capture on job links → application.source), questionnaire drop-off per step/question, processing quality (parse fail rate, OCR rate, avg processing time), AI–human agreement and override rates per vacancy/band, clarification response rates.
- [x] **P13-T04** — Optional voluntary diversity monitoring module (default OFF; separate form after submission, never visible to reviewers, aggregate-only with k ≥ 10 suppression) — only if owner enables (record ADR).
- [x] **P13-T05** — Reports UI `/hr/reports` with charts (accessible, table alternatives; follow dataviz guidance), date/department/vacancy filters, drill-down.
- [x] **P13-T06** — Exports (reports queue): XLSX (openpyxl) / CSV / PDF; permission-checked, formula-injection-safe, PII minimisation options (blind export), expiring links (15 min), audit (EC-PRV-08).
- [x] **P13-T07** — AI quality monitoring: scheduled `ai_quality_reports`; alert to HR manager when vacancy override rate > 30% (suggest rubric review); platform-level drift indicators (parse failure trends, score distribution shifts by engine version).
- [x] **P13-T08** — Tests: consent boundaries, export permissions & escaping, analytics reconciliation against raw data.

## Exit criteria
- [x] Talent pool consent boundaries proven by tests; reports reconcile; exports secure and logged.

## Exit evidence (2026-11-19)
- Consent boundaries: `tests/integration/test_phase13_boundaries.py` (join only employers applied
  to; another employer never finds the person by skill or name; no CV id, filename or email in
  search results; CV download refused across employers; leaving and erasure end membership at
  once) + `apps/talentpool/tests` (opt-in at submit, reconfirmation, reminders, expiry, withdrawal
  from the general consents list, deletion, cross-tenant 404s) + registry endpoints in the
  cross-tenant suite and role matrix.
- Reports reconcile: `apps/analytics/tests/test_reports.py` compares every section with direct
  queries; the report funnel equals the dashboard funnel for the same vacancy.
- Exports secure and logged: `apps/analytics/tests/test_exports.py` (EC-PRV-08 formula payloads
  neutralised in CSV and XLSX, blind export without names/contacts, admin/HR manager only, other
  organisations 404, 15-minute presigned links, files expire after 24 h, requested/downloaded
  audited).
- Full backend suite 2897 passed, 2 skipped; CI green (run 44506354495 on d66a298).
- T04 (diversity monitoring) not built by design: ADR-031 / open decision D-10.
