---
description: Close the current MHRS phase after all exit criteria pass, and advance to the next phase
---
1. Run the `/verify-phase` procedure. If any criterion fails, fix it first; do not close.
2. Mark the phase ✅ in `PROGRESS.md` (phase table + date), tick its exit criteria in the phase file.
3. Write a short phase summary in PROGRESS.md "Phase summaries" (what was built, deviations, known limitations, follow-ups).
4. Update `CHANGELOG.md`; update `CLAUDE.md` / nested CLAUDE.md files if conventions or commands changed.
5. Set "Current phase" to the next phase; commit `chore(progress): close phase NN`.
6. Start the next phase's first task.
