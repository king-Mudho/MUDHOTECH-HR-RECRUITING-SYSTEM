# Runbook — suspected personal-data breach

P11-T08. Legal frame: Zimbabwe Cyber and Data Protection Act [Ch. 12:07] and SI 155 of 2024 (docs/06 §2).
**Notification deadlines and the authority's contact details must be confirmed by counsel (D-08) before go-live
and written into the table at the end.** Never paste personal data into tickets, chats or emails about the incident.

## Symptoms (any of)
- A candidate or employer reports seeing someone else's data; a cross-tenant access report.
- Sentry/logs show a tenant-isolation error (`UnscopedTenantQueryError`), unusual exports or bulk downloads.
- A secret, backup or database dump found where it should not be; a lost device with access.
- An attacker claims to hold data; a ransomware note.

## Roles
| Role | Who | Does |
|---|---|---|
| Incident lead | on-call engineer, then the owner | runs this runbook, keeps the timeline |
| Data-protection lead | the DPO (or the owner until one is appointed, D-08) | assessment, notifications, records |
| Customer contact | the owner | informs affected organisations (they are controllers for their candidates) |

## Immediate actions (first hour) — contain, preserve
1. Start a **timeline** (UTC): when detected, by whom, what was seen.
2. **Contain**, choosing the smallest effective step:
   - a leaking feature → switch it off (feature flag, or deploy a revert: `deploy.sh rollback`);
   - a compromised account → `credential-compromise.md` (revoke sessions, rotate secrets);
   - AI path involved → `disable-ai.md`;
   - active attack → restrict nginx to the operator allow-list (maintenance) or stop `frontend`/`backend`.
3. **Preserve evidence** before changing more: the audit log is append-only and hash-chained —
   `$DC exec backend python manage.py verify_audit_chain`; export the relevant audit events (HR → Audit, or the CSV export
   `/api/v1/hr/audit-events/export/`), CloudWatch log groups (`/mhrs/<env>/*`), Sentry issues, and an RDS
   snapshot (`aws rds create-db-snapshot --db-snapshot-identifier mhrs-<env>-incident-<date>`).

## Assessment (first 24 hours)
- **What data, whose, how many?** Use the audit log (`log_view` records every view of candidate data,
  `audit.AccessLog` for downloads), nginx JSON logs (`/mhrs/<env>/nginx`), the break-glass support-access grants
  (*Platform admin → Support access*, `/admin/support-access`).
- **Which organisations?** Every tenant row carries `organisation_id`: the affected controllers.
- **Risk to people**: special categories involved? (the platform does not collect protected attributes, but CVs
  may contain them, docs/06) Identity theft or discrimination risk? Was data encrypted (field-level encryption
  ADR-011, S3 SSE)? Was it actually accessed or only exposed?

## Notification
1. **Affected organisations (controllers)** — the owner informs them without undue delay with: what happened,
   data categories, number of their candidates, measures taken, contact point (template in
   `docs/legal/DPA_TEMPLATE.md` §5: within 48 h).
2. **Data Protection Authority (POTRAZ)** — as required by the Act, within the deadline confirmed by counsel.
3. **Data subjects** — when the risk to them is high, in plain language (the organisations usually send this;
   the platform can send through the notification service with a dedicated template).
4. Record every notification (who, when, content) in the incident record.

## Resolution and verification
Fix the root cause, add a regression test (cross-tenant tests in `tests/tenancy/` for isolation bugs), deploy,
and verify with the original reproduction. Rotate anything that may have been exposed (`rotate-keys.md`).

## Follow-up
Post-incident review within 10 working days (timeline, root cause, what detected it, what would have detected it
sooner); update the risk register / DPIA (`docs/dpia/`); keep the incident record for the period counsel
advises.

| Item | Value (counsel to confirm, D-08) |
|---|---|
| Authority notification deadline | _to be confirmed_ |
| Authority contact | POTRAZ Data Protection Authority — _address/portal to be confirmed_ |
| Controller notification (contractual) | without undue delay, at most 48 h (DPA template) |
