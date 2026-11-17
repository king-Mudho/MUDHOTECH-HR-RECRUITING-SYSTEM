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

## Follow-ups (not defects)

- Platform admin screens for users, feature flags, system health, dead letters and platform audit
  logs are not in any phase plan; until they are, operators use Django admin (dev), Flower and the
  runbooks. Recorded for the owner (product backlog).
