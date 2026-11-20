# Runbook — restore the database

P11-T06. Scripts: `infrastructure/deployment/backup.sh`, `infrastructure/deployment/restore.sh`.
Backups: RDS automated backups + point-in-time recovery (primary) and a weekly logical `pg_dump` to
`s3://mhrs-<env>-backups/postgres/YYYY/MM/` (secondary, SSE, 35-day lifecycle, versioned bucket, no delete
permission for the instance role).

| Objective | Target | How it is met |
|---|---|---|
| **RPO** (data loss) | ≤ 5 minutes | RDS PITR (transaction logs every 5 min); the weekly dump is a fallback with RPO ≤ 7 days |
| **RTO** (back in service) | ≤ 2 hours | PITR restore of a ~50 GB pilot database ≈ 20–40 min on RDS + verification + DNS-free switch (SSM + redeploy, ~10 min) |

## When to use

- Data was destroyed or corrupted (bad migration, operator error, application bug) — restore to the minute
  *before* the event with PITR.
- The RDS instance is lost or unusable — restore the latest snapshot / PITR into a new instance.
- RDS backups themselves are unavailable or suspected compromised — restore the weekly logical dump.
- Quarterly **restore drill** (go-live gate; record the timings below).

## Impact

A restore always creates a **new** database/instance; nothing is overwritten. While switching, the application is
in maintenance (writes would be lost otherwise). Data written after the restore point is gone unless re-entered:
note the restore point in the incident record and tell affected organisations (CDPA notification duties may
apply if personal data was lost — see `incident-data-leak.md`).

## Immediate actions

1. Open an incident (time, symptom, suspected start of the damage). **Stop the damage:** if a job/bug is still
   writing bad data, stop workers: `docker compose -f docker-compose.prod.yml stop worker-default worker-documents worker-ai beat`.
2. Decide the restore point (UTC): the last good moment before the damage (audit log, application logs, Sentry).
3. Put the site in maintenance if data must be switched: stop `frontend` and `backend` (nginx then answers 502;
   the public status message goes out through the owner's channels).

## A. Point-in-time restore (primary)

```bash
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier mhrs-<env>-db \
  --target-db-instance-identifier mhrs-<env>-db-restore-<yyyymmddhhmm> \
  --restore-time 2026-11-18T09:14:00Z \
  --db-subnet-group-name mhrs-<env>-db --vpc-security-group-ids <sg-db> \
  --db-parameter-group-name mhrs-<env>-pg16 --no-publicly-accessible --multi-az false
aws rds wait db-instance-available --db-instance-identifier mhrs-<env>-db-restore-<yyyymmddhhmm>
```

Then verify (below) against the new endpoint, update `/mhrs/<env>/DATABASE_URL` in SSM to the new endpoint and
run `infrastructure/deployment/deploy.sh <current tag>` (it renders the new `.env` and restarts everything). Keep
the damaged instance (renamed, deletion protection on) until the incident is closed — it is evidence.

## B. Logical restore (secondary / any PostgreSQL 16)

```bash
aws s3 ls s3://mhrs-<env>-backups/postgres/ --recursive | tail -5          # pick a dump
ADMIN_DATABASE_URL='postgres://mhrs_admin:<pw>@<endpoint>:5432/postgres?sslmode=require' \
  infrastructure/deployment/restore.sh s3://mhrs-<env>-backups/postgres/2026/11/mhrs-<env>-20261115T013000Z.dump \
  mhrs_restore_20261118 mhrs_app
```

`restore.sh` checks the SHA-256, **refuses an existing target database**, creates the extensions listed in the
dump as the admin, restores everything else **as `mhrs_app`** (so it owns the objects and the FORCEd row-level
security policies keep applying, ADR-012), with `--enable-row-security`, and prints the verification queries.
To switch: point `DATABASE_URL` (SSM) at `.../mhrs_restore_20261118` and redeploy.

## Verify (both paths)

1. `restore.sh` output (or the same queries by hand): migrations > 0, organisations / users / jobs / applications /
   documents / audit events plausible against the last known numbers, latest audit event ≈ the restore point,
   `rls_forced_tables` equal to the source database (24 since P12-T01: 19 + 5 interview tables), `owner_is_superuser` = false.
2. Audit hash chain intact:
   `docker compose -f docker-compose.prod.yml run --rm -e DATABASE_URL='<new url as mhrs_app>' backend python manage.py verify_audit_chain`
3. After the switch: `deploy.sh` smoke tests pass; sign in as a test HR user; open one application with evidence;
   object storage links resolve (documents live in S3, not in the database — a restore does not touch them).
4. `python manage.py check_human_decisions` → 0.

## Follow-up

- Incident record: restore point, data-loss window, organisations affected, timings (same columns as the drill
  table below).
- Personal data erased **after** the restore point is back in the restored database and must be erased again:
  run the retention job now
  (`docker compose -f docker-compose.prod.yml exec backend celery -A config call apps.privacy.tasks.retention_daily`)
  and re-apply every deletion request completed after the restore point (HR → Privacy requests / platform privacy
  requests, filter by completion date), then confirm each with `python manage.py verify_erasure <user_id>`.
- Re-enable workers/beat, watch the dead-letter count and the processing backlog for an hour.

## Restore drills

| Date | Environment | Source | Size | Backup | Restore | Verification | Result |
|---|---|---|---|---|---|---|---|
| 2026-11-18 | local rehearsal (dev stack, PostgreSQL 16 + pgvector) | dev database copied into a DB owned by a `NOSUPERUSER NOBYPASSRLS` role (like `mhrs_app`) | 46 MB DB → 9.1 MB dump | 1 s (`backup.sh --local`, 90 tables with data) | 4 s (`restore.sh`, 2 jobs) + 30 s `verify_audit_chain` | 90 tables / 34,716 rows identical; 19 FORCE-RLS tables + 19 policies restored; owner non-superuser; **6 audit chains verified** | ✅ |
| _pending_ | staging (RDS) | PITR + weekly dump | — | — | — | — | owner step (P11-T09) |

Findings from the 2026-11-18 rehearsal, fixed before this runbook was written:

- `pg_dump` as the RLS-bound app role fails without `--enable-row-security`
  (`query would be affected by row-level security policy`) → `backup.sh` passes it.
- Extension entries in the dump (`citext`, `pg_trgm`, `unaccent`, `vector`) cannot be restored or commented on
  by the non-superuser owner → `restore.sh` creates them as the admin from the dump's own list and restores the
  rest as the owner.
- PostgreSQL 16 requires role membership to create a database for / restore as `mhrs_app` → `restore.sh`
  grants it to the admin (RDS: allowed, the master user created the role).

Expected timings at pilot scale (to be confirmed by the staging drill): logical dump of 1–5 GB ≈ 1–5 min,
restore ≈ 2–4× the dump time; PITR ≈ 20–40 min (RDS-side).

### Shared VPS production (ADR-033)

`bash /srv/mhrs/infrastructure/vps/restore-drill.sh` takes a fresh backup, restores it into a scratch
database, compares key tables with live and drops the copy. Real restores:
`bash /srv/mhrs/infrastructure/vps/rollback.sh --restore-db /srv/mhrs/backups/mhrs-db-<stamp>.dump`
(asks for the database name to confirm). Restoring needs the matching `mhrs-env-<stamp>` file: it holds
the field-encryption keys.

| Date | Dump | Restore time | Result |
|---|---|---|---|
| 2026-11-20 | 1.2 MB (empty production, taxonomy loaded) | 4 s | all key tables match live |

## Setup (once per environment)

After the first deploy: `sudo /opt/mhrs/infrastructure/deployment/backup.sh --install-timer` (Sunday 01:30 UTC,
after the RDS backup window). Each run emits the CloudWatch metric `MHRS/<env> BackupSucceeded` (1/0); the alarm
fires when no success was recorded for 8 days (P11-T07). Manual run: `sudo -u mhrs /opt/mhrs/infrastructure/deployment/backup.sh`.
