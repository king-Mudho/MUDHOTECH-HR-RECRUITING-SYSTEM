# PHASE 08 — Shortlist Review, HR Dashboard & Audit UI  (→ MVP feature-complete)

**Release:** MVP · **Modules:** M12, M15, M22 (UI/reconstruct) · **Depends on:** Phase 07
**Read first:** `docs/01 M12, M15, M22`, `docs/03 shortlisting/audit`, `docs/04 Shortlisting/Dashboard/Audit`, `docs/08 §3.2–3.4`, `docs/07 G`

## Goal
HR reviews every applicant with full evidence, compares candidates, verifies claims, and approves an accountable
shortlist (with undo window); dashboards show operational truth; auditors can reconstruct any decision.

## Tasks
- [ ] **P08-T01** — `apps.shortlisting` models: Shortlist, ShortlistEntry, DecisionReason (seed: shortlist reasons, not-selected reasons e.g. "essential criterion not evidenced after review", "less relevant experience than shortlisted candidates", "eligibility requirement not met (verified)", hold reasons, override reasons).
- [ ] **P08-T02** — Services: create proposal (pre-fill suggestions from bands — suggestions only), set decisions (reason required for not_selected & overrides), submit, approve/reject (dual control; self-approval forbidden when on; row locks; `@idempotent`) applying all transitions atomically through state machine; schedule notifications after `notification_delay_minutes`; undo within window (cancels scheduled notifications, reverses via new events) (EC-REV-01..05, 07, 08).
- [ ] **P08-T03** — Override tracking: entry stores `ai_band_at_decision`, `score_at_decision`, `override` computed; override analytics query.
- [ ] **P08-T04** — Blind review mode: server-side serializer redaction (name → "Candidate #A12", email/phone/links/address hidden, optional institution masking); "Reveal identity" action with reason → audit (EC-REV-06).
- [ ] **P08-T05** — Applicants list API & UI final: filters (band, score range, coverage, flags, essentials state, status, tags, assigned), saved views, cursor pagination, virtualised table, bulk actions (assign, tag, clarification, propose shortlist) (EC-JOB-17).
- [ ] **P08-T06** — Candidate review page `/hr/applications/[id]` per `docs/08 §3.3`: `EvidenceViewer` (pdf.js in sandboxed iframe/canvas, highlight snippets by page/offset; DOCX rendered as extracted text view with highlights), criteria panel with verify/correct, answers, flags banner, timeline, notes, messages, evaluation versions switcher; keyboard shortcuts (j/k next/prev applicant).
- [ ] **P08-T07** — Compare view `/hr/compare` (≤ 4) — criteria rows × candidates, evidence snippets on hover.
- [ ] **P08-T08** — Shortlist builder `/hr/jobs/[id]/shortlist` per `docs/08 §3.4` incl. undecided count gating, low-coverage separate column, approval dialog summarising counts and reasons, undo countdown.
- [ ] **P08-T09** — Role visibility: hiring manager sees shortlist only (EC-REV-09); conflict-of-interest "declare conflict" action (EC-REV-11); staff cannot open own application (EC-ACC-09/10).
- [ ] **P08-T10** — HR dashboard `/hr/dashboard`: KPI cards & queues per SRS M15, per-vacancy funnel, filters; AI suggestions vs human decisions shown separately; reconciliation test (dashboard numbers == direct queries).
- [ ] **P08-T11** — Audit UI `/hr/settings/audit` (filters, export for auditors) + `GET /hr/applications/{id}/reconstruct` bundle (job version, rubric, evidence refs, evaluation versions, engine/model versions, human decisions with reasons, notifications sent) + PDF rendering of reconstruction.
- [ ] **P08-T12** — Access logging on every candidate PII/CV view (AccessLog) with sampling disabled for auditors.
- [ ] **P08-T13** — E2E "Core Scenario" test: seed Software Developer job → 100 synthetic applications submitted via API → processing completes → HR filters, verifies 2 claims, requests 1 clarification, approves shortlist of 10 → after delay, notifications in Mailpit (10 shortlisted, others per HR decision only).

## Edge cases
EC-REV-01..11, EC-PRV-06 (auditor redaction), EC-JOB-17.

## Exit criteria (MVP feature-complete)
- [ ] Core Scenario E2E passes reliably (3 consecutive runs).
- [ ] Audit query proves 0 consequential transitions without human actor.
- [ ] Reconstruction bundle complete for a random sample of 10 applications.
- [ ] Dashboard reconciliation tests pass.
- [ ] Tag `v0.9.0-mvp` created; CHANGELOG updated.
