# Operations runbooks — MUDHOTECH HR RECRUITING SYSTEM

Runbooks are short, step-by-step procedures for on-call engineers (docs/10 §6). Each runbook follows the
same template: **Symptoms → Impact → Immediate actions → Diagnosis → Resolution → Verification →
Follow-up (incident record, audit, communication)**. Never paste personal data or secrets into tickets.

In every runbook, `$DC` stands for the production compose command on the host:

```bash
DC="docker compose -f /opt/mhrs/docker-compose.prod.yml --env-file /opt/mhrs/.env"
```

Paths starting with `/django-admin/`, `/api/docs/` and `/readyz` are only reachable from the operator IP allow-list
(`/etc/mhrs/nginx/ops-allowlist.conf`). Alarm names (`mhrs-<env>-…`) come from `infrastructure/monitoring/alarms.sh`.

| Runbook | Alarm(s) | Written in |
|---|---|---|
| `processing-backlog.md` — workers, queues, outbox, stuck applications, dead-letter retry | documents-queue, processing-backlog, outbox-lag, dead-letters | P11-T08 |
| `restore-database.md` — RDS PITR / `pg_restore`, verification queries, drill log | backup-age, backup-failed | P11-T06 |
| `incident-data-leak.md` — contain, preserve evidence, assess, notify (CDPA / POTRAZ) | — | P11-T08 |
| `credential-compromise.md` — accounts, admins, application secrets, AWS keys | — | P11-T08 |
| `malware-detected.md` — quarantine handling, campaigns, ClamAV freshness | clamav-signatures | P11-T08 |
| `disable-ai.md` — kill switch for AI screening | — | P09-T11 |
| `email-deliverability.md` — SES bounces/complaints, suppression, SMTP failures | email-failures, ses-bounces, ses-complaints | P11-T08 |
| `certificate-renewal.md` — Certbot renewal and checks | cert-expiry | P11-T08 |
| `disk-full.md` — logs, docker images, volumes, growing EBS | disk-root, disk-docker | P11-T08 |
| `rotate-keys.md` — field-encryption key rotation + `rotate_field_keys` | — | P11-T08 |

Other alarms: `5xx-rate`, `unhealthy-containers`, `memory`, `ec2-*`, `rds-*` → start with `$DC ps`, `$DC logs --tail
200 <service>` and Sentry for the release in question; `deploy.sh rollback` if a deploy caused it.

## Quick reference (dev stack, Phase 01)
| Check | Command |
|---|---|
| Liveness / readiness | `curl -fsS http://127.0.0.1:8000/healthz` · `curl -fsS http://127.0.0.1:8000/readyz` |
| Worker round-trip | `docker compose exec backend python manage.py celery_ping` |
| Email path | `docker compose exec backend python manage.py send_test_email` → Mailpit http://localhost:8025 |
| Outbox backlog | Django admin `/django-admin/core/outboxevent/?status__exact=pending` |
| Dead letters | Django admin `/django-admin/core/deadletter/` |
| Queue monitor | Flower http://localhost:5555 |

> Windows note: if `http://localhost:…` resets the connection, use `http://127.0.0.1:…` (IPv6 `::1` vs IPv4
> port publishing).
