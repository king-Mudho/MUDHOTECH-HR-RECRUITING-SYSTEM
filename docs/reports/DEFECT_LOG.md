# Defect log

Phase 10 bug bash (P10-T10) and defects found while closing Phase 09. Severity: **P0** data loss,
security or legal breach, blocks the core scenario · **P1** a core journey broken or wrong for many
users · **P2** a journey degraded, workaround exists · **P3** cosmetic / tooling.

Go-live gate: no open P0/P1.

| ID | Found | Area | Description | Severity | Status | Fix |
|---|---|---|---|---|---|---|
| D-001 | 2026-11-17 | Public site | Footer links `/privacy`, `/terms`, `/accessibility` returned 404; the platform privacy notice (backup expiry, EC-PRV-10) was not published | P1 | Fixed | `1d4cd28`; guard `tests/legal-pages.test.ts` |
| D-002 | 2026-11-17 | Navigation | Six navigation items linked to pages that do not exist (`/hr/reports`, `/admin/users`, `/admin/feature-flags`, `/admin/system-health`, `/admin/dead-letters`, `/admin/audit-logs`) | P2 | Fixed (hidden until built; reports in P13-T05, platform admin pages unplanned - see follow-up) | `navigation.ts`; guard `tests/navigation.test.ts` |
| D-003 | 2026-11-17 | Organisations | Organisations could not be closed (EC-ORG-10): no closed flow, candidates never told | P1 | Fixed | `1d4cd28` (`close_organisation`, admin UI) |
| D-004 | 2026-11-17 | Accessibility | Four signed-in pages had no main landmark, so the skip link had no target; the sticky top bar could cover the focused element | P2 | Fixed | `bfefd77`; guard `tests/a11y-landmarks.test.ts` |
| D-005 | 2026-11-17 | E2E (nightly) | Core-scenario spec read `me.active_organisation_id`, which is null until a user switches organisation, so the nightly browser run failed | P2 | Fixed (confirm on next nightly) | `40ace9f` (`e2e/hr-context.ts`) |
| D-006 | 2026-11-17 | CI | Nightly bandit (all severities) failed on two false positives | P3 | Fixed | `40ace9f` |
| D-007 | 2026-11-17 | Tests | Core-scenario test lost the clarification email in daytime runs (sent at once, then cleared); RLS overhead check failed on sub-millisecond noise on CI | P3 | Fixed | `1d4cd28`, `49ee168` |
| D-008 | 2026-11-17 | AI screening | Pilot benchmark on the demo Software Developer vacancy: 4 of 7 gold-*suitable* developer CVs routed to *lower match* (recall of suitable in recommended ∪ review needed 3/7, target ≥ 95 %). Causes: (a) the demo rubric's four essentials are all skills, and skills shown only under "Skills" score 50 by design (EC-DOC-24), giving totals of 64–67 < 70; (b) the criterion "REST API design" does not match the CV skill "REST APIs" (no equivalent/alias); (c) "Cloud deployment" vs "AWS Certified Cloud Practitioner" needs semantic matching, off on the host run. Humans still review every application, but the routing hint misleads | P1 | Fixed — ADR-028 calibration (listed-only 75, config 2026.11.2; extraction semantic 0.65, engine 0.3.1) + demo rubric equivalents; pilot rerun: 0/7 suitable in lower match (6 recommended) | `551d369`, P10-T03 commit; `AI_VALIDATION_REPORT.md` |
| D-009 | 2026-11-18 | API server | First load test against the production server set-up (gunicorn + uvicorn ASGI workers): 69 % of job-board requests returned 500, P95 4.6 s, 117 RPS; logins failed. Cause: under ASGI Django's persistent connections are not reused across requests (one worker held 57 PostgreSQL connections after 600 requests), exhausting `max_connections`; and every synchronous view ran on one thread per worker | P0 | Fixed - ADR-029: gunicorn WSGI threaded workers + psycopg connection pool (connections stayed at 11 under the same local load); confirm with the next Load run | `entrypoint-prod.sh`, `config/settings/base.py` |
| D-010 | 2026-11-18 | API server | Load run 3: 1 in 100 and 11 in 1,000 submissions returned 500. The readiness check set `statement_timeout` at session level; with the new connection pool (D-009) the setting stayed on the pooled connection and cancelled slow statements in later requests (a submit waiting on the reference-counter lock) | P1 | Fixed - transaction-local setting + regression test `apps/core/tests/test_health.py`; server-error summary added to the Load workflow | `apps/core/health.py` |
| D-011 | 2026-11-18 | Resilience | Redis outage would fail every API request (EC-OPS-01): the Django cache raised on connection errors and every request reads it (rate-limit throttles, feature flags, public cache) - submissions included | P0 | Fixed - `apps.core.cache.ResilientRedisCache` degrades to a cache miss with 0.5 s socket timeouts; `apps/core/tests/test_cache_resilience.py` | `config/settings/base.py` |
| D-012 | 2026-11-18 | Resilience | A killed worker container left applications in *processing* for up to an hour (EC-OPS-04): Redis redelivers unacknowledged tasks only after the 1-hour visibility timeout, and nothing swept stuck work | P1 | Fixed - `recover_stuck_processing` beat task (every 5 min, work stuck > 15 min) + retries clear partial output; `apps/resumes/tests/test_recovery.py` | `apps/resumes/recovery.py` |

## Follow-ups (not defects)

- Platform admin screens for users, feature flags, system health, dead letters and platform audit
  logs are not in any phase plan; until they are, operators use Django admin (dev), Flower and the
  runbooks. Recorded for the owner (product backlog).
