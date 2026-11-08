# Operations runbooks — MUDHOTECH HR RECRUITING SYSTEM

Runbooks are short, step-by-step procedures for on-call engineers (docs/10 §6). Each runbook follows the
same template: **Symptoms → Impact → Immediate actions → Diagnosis → Resolution → Verification →
Follow-up (incident record, audit, communication)**. Never paste personal data or secrets into tickets.

| Runbook | Status | Written in |
|---|---|---|
| `processing-backlog.md` — scale workers, inspect dead letters, retry | planned | Phase 06/10 |
| `restore-database.md` — RDS PITR / `pg_restore`, verification queries | planned | Phase 11 |
| `incident-data-leak.md` — contain, assess, notify (CDPA / POTRAZ) | planned | Phase 09 |
| `credential-compromise.md` — rotate secrets, revoke sessions | planned | Phase 09 |
| `malware-detected.md` — quarantine handling, candidate messaging | planned | Phase 04 |
| `disable-ai.md` — feature-flag kill switch for AI screening | planned | Phase 07 |
| `email-deliverability.md` — SES bounces/complaints, suppression | planned | Phase 05 |
| `certificate-renewal.md` — Certbot renewal and checks | planned | Phase 11 |
| `disk-full.md` — logs, docker images, volumes | planned | Phase 11 |
| `rotate-keys.md` — field-encryption key rotation + re-encrypt job | planned | Phase 09 |

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
