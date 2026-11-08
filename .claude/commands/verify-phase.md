---
description: Verify the current MHRS phase's exit criteria without closing it
---
For the current phase (or phase number in $ARGUMENTS):
1. Confirm every task is ticked; list any that are not.
2. Run the full backend and frontend test suites, lint, type-check, `makemigrations --check`, schema drift check, and `scripts/ec_coverage.py` for the phase's EC ids.
3. Evaluate each Exit Criterion one by one with evidence (command output, test names, report paths).
4. Output a table: criterion | pass/fail | evidence. Propose fixes for failures. Do not tick the phase.
