# PHASE 10 — Quality Assurance, AI Validation & Pilot Readiness

**Release:** MVP · **Depends on:** Phase 09
**Read first:** `docs/09_TESTING_STRATEGY.md` (all), `docs/05 §13`, `docs/01 §1.3 objectives`, `docs/07 J`

## Goal
Prove the MVP is correct, fair, resilient, performant and accessible using the 100-application pilot benchmark,
fault injection and load tests; produce a pilot evaluation report.

## Tasks
- [ ] **P10-T01** — EC coverage: run `scripts/ec_coverage.py`; add missing tests until every EC id for Phases 1–9 is covered.
- [ ] **P10-T02** — Full Playwright suite (desktop + mobile emulation) for: candidate apply journey, clarification, withdraw, HR job creation→approval→publish, screening review, shortlist approval + undo, rights request, admin verify org. Visual snapshots for key pages.
- [ ] **P10-T03** — AI validation: expand corpus to ≥ 150 labelled CVs across 5 roles; run extraction + screening benchmarks; compute metrics in `docs/09 §5`; calibrate semantic thresholds (store in engine config w/ new engine version); report `docs/reports/AI_VALIDATION_REPORT.md` incl. missed-qualified analysis and failure taxonomy.
- [ ] **P10-T04** — Fairness: counterfactual suite at scale (≥ 500 perturbations), proxy-variable review (institution, location, gaps), documented findings & mitigations in report.
- [ ] **P10-T05** — Load tests (Locust): 100 and 1,000 concurrent submissions; public job board 200 RPS read; HR applicants list with 5,000 applications; record P95s vs NFR-PERF; fix bottlenecks (indexes, N+1 via `django-query-count`/nplusone).
- [ ] **P10-T06** — Throughput: 100 CVs end-to-end ≤ 15 min on 4 vCPU/8 GB profile (docker resource limits) — record; tune worker concurrency/prefetch.
- [ ] **P10-T07** — Resilience/fault injection: kill workers mid-task, stop Redis during submissions, S3 errors, DB restart, duplicate messages → assert O1 (no loss, no duplicates) and recovery (EC-OPS-01..04).
- [ ] **P10-T08** — Pilot dataset & script: `python manage.py run_pilot_benchmark` → creates vacancy, submits 100 applications, waits, outputs accounting table (100/100 records, parse success/fail, bands, flags) to `docs/reports/PILOT_BENCHMARK.md`.
- [ ] **P10-T09** — UAT pack `docs/uat/UAT_SCRIPTS.md` for HR reviewers (step-by-step scenarios, expected results, sign-off table) and `docs/user-guides/` (Candidate guide, Recruiter guide, HR Manager guide, Org Admin guide) with screenshots (Playwright-generated).
- [ ] **P10-T10** — Bug bash & fix all P0/P1 defects; log in `docs/reports/DEFECT_LOG.md`.

## Exit criteria (Go-live gates from Blueprint)
- [ ] No known critical/high security vulnerabilities.
- [ ] Complete end-to-end submission and shortlist flow verified.
- [ ] Evidence-grounded assessments with human approval (grounding 100%, human-actor audit 100%).
- [ ] Tenant isolation tests 100% pass.
- [ ] Privacy & retention policies implemented (legal sign-off tracked as D-08).
- [ ] AI validation report meets thresholds (or owner-accepted deviations recorded).
- [ ] Performance NFRs met or documented with mitigation.
