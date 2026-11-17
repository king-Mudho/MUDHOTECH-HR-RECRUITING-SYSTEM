# PHASE 08 — Shortlist Review, HR Dashboard & Audit UI  (→ MVP feature-complete)

**Release:** MVP · **Modules:** M12, M15, M22 (UI/reconstruct) · **Depends on:** Phase 07
**Read first:** `docs/01 M12, M15, M22`, `docs/03 shortlisting/audit`, `docs/04 Shortlisting/Dashboard/Audit`, `docs/08 §3.2–3.4`, `docs/07 G`

## Goal
HR reviews every applicant with full evidence, compares candidates, verifies claims, and approves an accountable
shortlist (with undo window); dashboards show operational truth; auditors can reconstruct any decision.

## Tasks
- [x] **P08-T01** — `apps.shortlisting` models: Shortlist, ShortlistEntry, DecisionReason (seed: shortlist reasons, not-selected reasons e.g. "essential criterion not evidenced after review", "less relevant experience than shortlisted candidates", "eligibility requirement not met (verified)", hold reasons, override reasons).
- [x] **P08-T02** — Services: create proposal (pre-fill suggestions from bands — suggestions only), set decisions (reason required for not_selected & overrides), submit, approve/reject (dual control; self-approval forbidden when on; row locks; `@idempotent`) applying all transitions atomically through state machine; schedule notifications after `notification_delay_minutes`; undo within window (cancels scheduled notifications, reverses via new events) (EC-REV-01..05, 07, 08).
- [x] **P08-T03** — Override tracking: entry stores `ai_band_at_decision`, `score_at_decision`, `override` computed; override analytics query.
- [x] **P08-T04** — Blind review mode: server-side serializer redaction (name → "Candidate #A12", email/phone/links/address hidden, optional institution masking); "Reveal identity" action with reason → audit (EC-REV-06).
- [x] **P08-T05** — Applicants list API & UI final: filters (band, score range, coverage, flags, essentials state, status, tags, assigned), saved views, cursor pagination, virtualised table, bulk actions (assign, tag, clarification, propose shortlist) (EC-JOB-17).
- [x] **P08-T06** — Candidate review page `/hr/applications/[id]` per `docs/08 §3.3`: `EvidenceViewer` (pdf.js in sandboxed iframe/canvas, highlight snippets by page/offset; DOCX rendered as extracted text view with highlights), criteria panel with verify/correct, answers, flags banner, timeline, notes, messages, evaluation versions switcher; keyboard shortcuts (j/k next/prev applicant).
- [x] **P08-T07** — Compare view `/hr/compare` (≤ 4) — criteria rows × candidates, evidence snippets on hover.
- [x] **P08-T08** — Shortlist builder `/hr/jobs/[id]/shortlist` per `docs/08 §3.4` incl. undecided count gating, low-coverage separate column, approval dialog summarising counts and reasons, undo countdown.
- [x] **P08-T09** — Role visibility: hiring manager sees shortlist only (EC-REV-09); conflict-of-interest "declare conflict" action (EC-REV-11); staff cannot open own application (EC-ACC-09/10).
- [x] **P08-T10** — HR dashboard `/hr/dashboard`: KPI cards & queues per SRS M15, per-vacancy funnel, filters; AI suggestions vs human decisions shown separately; reconciliation test (dashboard numbers == direct queries).
- [x] **P08-T11** — Audit UI `/hr/settings/audit` (filters, export for auditors) + `GET /hr/applications/{id}/reconstruct` bundle (job version, rubric, evidence refs, evaluation versions, engine/model versions, human decisions with reasons, notifications sent) + PDF rendering of reconstruction.
- [x] **P08-T12** — Access logging on every candidate PII/CV view (AccessLog) with sampling disabled for auditors.
- [x] **P08-T13** — E2E "Core Scenario" test: seed Software Developer job → 100 synthetic applications submitted via API → processing completes → HR filters, verifies 2 claims, requests 1 clarification, approves shortlist of 10 → after delay, notifications in Mailpit (10 shortlisted, others per HR decision only).

## Edge cases
EC-REV-01..11, EC-PRV-06 (auditor redaction), EC-JOB-17.

## Exit criteria (MVP feature-complete)
- [x] Core Scenario E2E passes reliably (3 consecutive runs).
- [x] Audit query proves 0 consequential transitions without human actor.
- [x] Reconstruction bundle complete for a random sample of 10 applications.
- [x] Dashboard reconciliation tests pass.
- [x] Tag `v0.9.0-mvp` created; CHANGELOG updated.

## Exit evidence (2026-11-17)
- Core scenario: `apps/screening/tests/test_core_scenario.py` (marked slow) drives the HTTP API end to end:
  100 synthetic applications -> real extraction + screening via the outbox -> HR filters, verifies 2 claims,
  requests 1 clarification, proposes and approves a shortlist of 10 -> after the delay (and quiet hours)
  exactly 10 outcome emails + the clarification email, nobody else. Passed 3 consecutive runs (92 s, 60 s,
  63 s). The same journey in the browser (`frontend/e2e/core-scenario.spec.ts` with
  `seed_core_scenario --count 100 --delay-minutes 1`) runs in the nightly Docker job; it could not run on
  the dev machine (0.7 GB free RAM, ports held by another project) - confirm on the first nightly.
- No consequential transition without a human: `python manage.py check_human_decisions` (exits 1 otherwise),
  asserted in the core scenario and `test_no_consequential_transition_without_a_human`; DB check constraints
  on shortlist entries (decision needs actor; not selected needs reason).
- Reconstruction: the core scenario reconstructs a random sample of 10 applications and checks job version,
  rubric, every evaluation version (engine/thresholds/models/input hash/evidence refs), status history,
  shortlist decisions (approver, applied time), notifications; PDF rendering tested
  (`test_reconstruct.py`), auditor redaction (EC-PRV-06).
- Dashboard reconciliation: `apps/applications/tests/test_dashboard.py` compares every card and the funnel with
  direct queries.
- Edge cases: `scripts/ec_coverage.py --phase 08` 13/13; backend full suite green, 160+ Vitest.
- Tag `v0.9.0-mvp` created; CHANGELOG release section added.
