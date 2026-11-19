# Platform admin guide

For MudhoTech staff who run the platform. Platform **support** users see the same pages read-only.

## 1. Dashboard

**Admin → Dashboard** shows organisations by status, published vacancies, applications per day,
open dead letters, the CV read failure rate and queue/outbox health. Check it daily.

## 2. Organisations

- **Organisations**: verify new organisations (publishing needs verification), suspend, reactivate
  or close them – every action needs a reason and is audited.
- Open an organisation for members by role and usage (vacancies, applications and AI evaluations this
  month, storage).
- **Support access** is break-glass only: time-boxed, with a reason, visible to the organisation and
  read-only.

## 3. Plans, invoices and payments

- **Plans & pricing**: edit USD/ZWG prices and limits (blank price = custom, blank limit = unlimited).
  Existing invoices keep the prices they were issued with.
- Record a **bank transfer** against an invoice (amount must equal the total); it reactivates a
  read-only organisation immediately.
- Payments that could not be confirmed within 15 minutes show as *needs a manual check*: confirm in
  the Paynow dashboard, then record the payment manually if it was received.

## 4. Users, flags and taxonomy

- **Users**: search by email or name (3+ characters); only minimal details are shown.
- **Feature flags**: platform defaults and per-organisation overrides (e.g. `ai.screening`, the AI
  kill-switch – see `docs/runbooks/disable-ai.md`).
- **Skills taxonomy**: add skills, aliases, relations and qualification names, then **Publish new
  version** with a note. Screening uses the published version only; evaluations keep the version they
  used. Run `embed_skills` in a worker for meaning-based matching of new skills.

## 5. Operations

- **Dead letters**: background tasks that failed after retries – retry once the cause is fixed, or
  mark resolved with a reason.
- **System health**: database, cache and storage checks plus queue depths.
- AI drift indicators: `GET /api/v1/platform/ai/quality/` or `manage.py ai_quality_report` (weekly
  report stored automatically).
- Runbooks for incidents, backups/restore, key rotation and deployments: `docs/runbooks/`.
