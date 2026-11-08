---
description: Implement the next unchecked task of the current MHRS phase, fully, per Definition of Done
---
1. Read `CLAUDE.md`, `PROGRESS.md`, and the current phase file.
2. Select the first unchecked task (or the task ID given in $ARGUMENTS).
3. Read the referenced sections in `docs/` and the EC ids the phase lists that this task touches.
4. Implement it completely (backend, frontend, tests, OpenAPI, audit, tenancy tests) per `CLAUDE.md §7`.
5. Run verification (tests, lint, type-check, `makemigrations --check`). Fix until green.
6. Tick the task in the phase file AND in `PROGRESS.md`; add a session-log line (date, task id, summary, follow-ups).
7. Commit with a conventional commit message referencing the task id.
8. Continue with the next task unless a STOP condition (CLAUDE.md §5) applies.
