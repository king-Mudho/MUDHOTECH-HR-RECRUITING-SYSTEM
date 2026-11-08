# PHASE 16 — Final Hardening, Documentation & Release (Project complete)

**Release:** v1.2 final · **Depends on:** Phases 1–15
**Read first:** everything in `docs/`, PROGRESS.md open issues & deviations

## Tasks
- [ ] **P16-T01** — Full regression: unit, API, E2E (all journeys incl. v1.1/v1.2), accessibility, AI benchmarks, counterfactual fairness, load, resilience; record results in `docs/reports/FINAL_TEST_REPORT.md`.
- [ ] **P16-T02** — Security re-review: dependency updates, ASVS checklist re-run, ZAP full scan on staging, secrets rotation, IAM least-privilege review; third-party pen-test readiness pack.
- [ ] **P16-T03** — Performance tuning pass (query plans for top 20 endpoints, index review, cache headers, image sizes, bundle analysis).
- [ ] **P16-T04** — Technical documentation complete: architecture (updated diagrams), API reference (OpenAPI published), DB ERD (generated, e.g. `django-extensions graph_models` → SVG), AI engine design + model cards, runbooks, onboarding guide for new developers.
- [ ] **P16-T05** — User documentation complete: candidate, recruiter, HR manager, org admin, platform admin, auditor guides; FAQ; video script outlines.
- [ ] **P16-T06** — Clean-up: remove dead code/flags, resolve all TODO/FIXME (or ticket them in `docs/BACKLOG.md`), ensure `CLAUDE.md`, nested CLAUDE.md files and ADRs reflect final reality.
- [ ] **P16-T07** — Final release `v1.2.0`, CHANGELOG, release notes, handover document `docs/HANDOVER.md` (system overview, credentials ownership list (no secrets), operational calendar, support contacts, known limitations, roadmap).
- [ ] **P16-T08** — Post-release backlog `docs/BACKLOG.md` (ideas: ATS/HRIS sync connectors, assessments/tests module, video interview integration, mobile app, EEO reporting by jurisdiction, EU AI Act conformity pack if EU expansion).

## Exit criteria
- [ ] All phases ✅ in PROGRESS.md; all exit criteria satisfied; owner sign-off recorded.
