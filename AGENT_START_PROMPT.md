# Agent Start / Resume Prompt

Open Claude Code in `D:\mudhotech_2026\MUDHOTECH HR RECRUITING SYSTEM` and paste the prompt below.
The same prompt works for the first session and every resumed session.

---

```
You are the lead engineer implementing the MUDHOTECH HR RECRUITING SYSTEM in this repository.

1. Read CLAUDE.md completely, then PROGRESS.md, then the current phase file in phases/.
2. Work through the phases in order (Phase 01 → Phase 16). Within a phase, implement tasks in order,
   each one fully per the Definition of Done in CLAUDE.md §7, reading the referenced docs/ sections first.
3. After each task: run the verification commands, fix until green, tick the task in the phase file AND
   in PROGRESS.md, add a session-log line, and commit (conventional commit with the task id).
4. When every task in a phase is ticked, verify every Exit Criterion with evidence, close the phase in
   PROGRESS.md, and continue directly with the next phase.
5. Use the documented defaults in docs/11_DECISIONS_LOG.md; do not stop for questions unless a STOP
   condition in CLAUDE.md §5 applies (secrets/credentials, principle/stack changes, repeated failures).
6. Never violate the non-negotiable principles in CLAUDE.md §2 (human-in-control, evidence-first,
   missing ≠ negative, tenant isolation, versioning, resilience, fairness, security, privacy).
7. Keep PROGRESS.md accurate at all times so that any new session can resume exactly where you stopped.

Begin now with the next unchecked task.
```

---

## Useful slash commands (defined in `.claude/commands/`)
- `/status` — where are we, what's next, blockers
- `/next-task [TASK-ID]` — implement the next task fully
- `/verify-phase [NN]` — check exit criteria with evidence
- `/close-phase` — close current phase and move on

## Tips for long runs
- If the context gets long, start a fresh session with the same prompt — PROGRESS.md carries the state.
- Keep Docker Desktop running; the agent uses `docker compose` for everything.
- When the agent stops for credentials (AWS, SES, Paynow, domain), provide them via `.env` / AWS SSM, never in chat history files.
