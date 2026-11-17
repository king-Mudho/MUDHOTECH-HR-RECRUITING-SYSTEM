# Runbook — disable AI screening (kill-switch)

P09-T11. Code: `backend/apps/screening/killswitch.py`. UI: `/admin/model-registry` (platform) and
**HR → Settings → Organisation policy → AI screening** (one organisation, by its own admins).

## When to use

- AI output looks wrong (model drift, a bad taxonomy or threshold release, grounding failures in
  the daily AI quality report, a counterfactual test failing).
- A suspected prompt-injection or data-handling problem in the AI path.
- A legal or regulatory instruction, or a customer asks to pause AI for their organisation.
- An external LLM provider has an incident (switching the LLM off alone is also possible:
  `LLM_PROVIDER=none`, or the organisation's `llm_enabled` policy).

## Impact

While AI is off for an organisation:

- New and re-run evaluations are **not computed**. Applications move from `processing` to
  `under_review` in the `manual_review_requested` band: no score, no band hint, no AI explanation,
  no AI summary. Applications already evaluated have their AI numbers hidden the next time they are
  evaluated (screening runs started by HR).
- AI criteria suggestions and LLM summaries are unavailable.
- Nothing is lost: applications, CVs, extracted evidence and earlier evaluations stay stored;
  decisions continue as normal (they always required a person).
- Candidates are not notified (manual review is a normal path; the AI notice states it).

## Immediate actions

1. Decide the scope: **platform** (every organisation) or **one organisation**.
2. Switch off, with a reason that names the incident (it goes into the audit log):
   - UI: `/admin/model-registry` → *Switch AI off* (platform admin, MFA).
   - Shell (when the UI is unavailable):
     ```bash
     docker compose exec backend python manage.py ai_switch off --reason "INC-123: grounding drop"
     docker compose exec backend python manage.py ai_switch off --org <organisation-uuid> --reason "INC-123"
     docker compose exec backend python manage.py ai_switch status
     ```
3. The flag cache lives 30 s; workers pick the change up within that time. In-flight tasks that
   already started an evaluation may finish it (they are idempotent and versioned).

## Diagnosis

- `AuditEvent` actions `ai.kill_switch` (who, scope, reason) and `screening.ai_disabled`
  (each application routed to manual review).
- Daily `AIQualityReport` counters (bands, grounding, verification overrides) for the period before
  the switch; the screening benchmark (`run_screening_benchmark --check`) against the release.
- `ModelRegistryEntry`: which engine/threshold/model versions were active (`/admin/model-registry`).

## Resolution and switching back on

1. Fix and verify (benchmark targets met, counterfactual invariance 100 %).
2. `ai_switch on --reason "INC-123 resolved"` (or the UI). For an organisation override use
   `ai_switch inherit --org <uuid> --reason "..."`.
3. Switching on does **not** re-evaluate anything automatically. Tell HR they can start a screening
   run on a vacancy (`scope=all`) when they want AI assistance again; re-evaluation creates new
   evaluation versions, never overwrites.

## Verification

- `python manage.py ai_switch status` shows the expected state.
- Submit a synthetic application on staging: it reaches `under_review` with band
  `manual_review_requested` while off, and an evaluation while on.
- Automated: `backend/apps/screening/tests/test_killswitch.py`.

## Follow-up

Incident record (timeline, scope, number of applications routed to manual review — count
`screening.ai_disabled` audit events), customer communication if one organisation's screening
was affected, and an entry in `docs/11_DECISIONS_LOG.md` if thresholds or models change.
