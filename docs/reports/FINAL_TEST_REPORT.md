# Final test report — v1.2.0 (P16-T01)

Date: 2026-11-19. Code: `main` at `45081b3` (v1.2.0 release candidate). Synthetic data only.

## 1. Summary

| Area | Result | Evidence |
|---|---|---|
| Backend unit + API + integration | **3,058 passed, 2 skipped, 0 failed** on a fresh database (24 min 43 s) | local run against PostgreSQL 16 created from migrations, 2026-11-19 |
| Backend static checks | ruff check + format clean; mypy clean (417 files); Bandit `-ll` clean; `makemigrations --check` clean | CI |
| Cross-tenant and role matrix | every staff endpoint registered in `backend/tests/tenancy/` incl. v1.1/v1.2 apps (talent pool, analytics, billing, platform console, integrations) | part of the backend suite |
| Frontend unit / component | **196 passed** (40 files); ESLint, `tsc --noEmit`, production build pass | local Vitest 2026-11-19; CI |
| API contract | schema drift + generated types check green | CI run 44604411745 |
| E2E (Playwright, desktop + phone, axe) | green: apply, jobs, auth, core scenario, Phase 10 journeys, accessibility journeys | nightly 44486502792 (2026-11-19) |
| AI extraction | all docs/09 §5 targets met (table §3) | `extraction_benchmark_2026-11-19.md` |
| AI screening | recall of suitable 100 % (44/44), grounding 100 %, determinism 100 %, 0 not-suitable recommended | `screening_benchmark_2026-11-19.md` |
| Counterfactual fairness | **1,095/1,095** identical across five families; 121/121 in the screening benchmark | `fairness_2026-11-19.md` |
| Load | job board 210 RPS at P95 130-140 ms; HR list P95 < 60 ms; 1,100/1,100 burst submissions recorded, 0 failures | `PERFORMANCE.md` §2 (2026-11-18) |
| Throughput | 100 CVs submitted to evaluated in ~2.5 min (target 15 min) | `PERFORMANCE.md` §2.1 |
| Resilience | Redis outage, killed worker, PostgreSQL restart, duplicate delivery: 60/60 accounted for, no duplicates | `PERFORMANCE.md` §2.2 |
| Antivirus | real ClamAV with EICAR: infected files quarantined, never processed | nightly |
| Security scans | Bandit and pip-audit clean (nightly); npm audit clean (local). Semgrep reported four config findings, fixed in `c9b2100` (D-021); because the step failed, detect-secrets and Trivy were skipped in recent nightlies. **Pending:** the next nightly after `c9b2100` must pass Semgrep, detect-secrets and Trivy | nightly 44486502792; `docs/security/ASVS_CHECKLIST.md` |

Open defects: **no open P0/P1** (`DEFECT_LOG.md`).

## 2. Scope of the regression

The backend suite covers every module end to end through the API, including the v1.1/v1.2 flows:
interviews, scorecards, offers and hiring close-out (`test_phase12_hiring_flow.py`), talent pool
consent and search, reports and exports (`test_phase13_boundaries.py`), billing lifecycle, Paynow
callbacks and read-only mode (`test_phase14_billing.py`), integrations in sandbox mode (calendar,
SSO, SMS/WhatsApp, webhooks, public API, feeds), and the core scenario of 100 applications
(`test_core_scenario.py`).

## 3. AI benchmarks (engine 0.3.1, thresholds 2026.11.2)

| Metric | Result | Target |
|---|---|---|
| Parse success, text PDF/DOCX | 100 % | ≥ 98 % |
| Parse success incl. scanned (host without OCR) | 96.4 % | ≥ 90 % |
| Experience entry F1 | 0.963 | ≥ 0.85 |
| Education level accuracy | 1.00 | ≥ 0.90 |
| Skill precision / recall | 0.996 / 0.998 | ≥ 0.85 / ≥ 0.80 |
| Grounding, determinism | 100 % / 100 % | 100 % |
| Protected-attribute leaks | 0 | 0 |
| 100 CVs extracted (2 workers) | 84.7 s | ≤ 600 s |
| 100 evaluations + explanations | 0.08 s | ≤ 300 s |

Results are identical to the 2026-11-17 validation (`AI_VALIDATION_REPORT.md`), as expected: the
engine and thresholds have not changed since.

## 4. Not covered here (owner / staging)

- Browser (Playwright) journeys for hiring, talent pool, reports, billing and integrations screens:
  covered by API and component tests; to run on staging (`docs/BACKLOG.md`).
- Live providers (Paynow, Google/Microsoft OAuth, SMS aggregator, WhatsApp): sandbox only until the
  owner's accounts exist.
- ZAP full scan, Playwright suite and load test against staging: need the staging environment
  (Phase 11 T09/T12).
- Real-world AI calibration: needs HR-labelled real applications.

## 5. Reproduce

```bash
cd backend && pytest -q --create-db
cd frontend && npx vitest run && npm run lint && npm run typecheck && npm run build
python -m ai_engine.tests.benchmark.run_extraction_benchmark --workers 2 --semantic --out-dir ../docs/reports --check
python -m ai_engine.tests.benchmark.run_screening_benchmark --out-dir ../docs/reports --check
python -m ai_engine.tests.benchmark.run_fairness_benchmark --out-dir ../docs/reports --check
```
