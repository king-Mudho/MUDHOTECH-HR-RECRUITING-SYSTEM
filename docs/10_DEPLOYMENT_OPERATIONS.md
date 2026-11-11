# 10 — Deployment & Operations

## 1. Local development (Windows, D: drive)
- Prereqs: Docker Desktop (WSL2 backend), Git, Node.js LTS (for running frontend tooling outside Docker optional), Python 3.12 (optional, for IDE).
- Path contains spaces → `docker-compose.yml` sets `name: mhrs`; scripts quote paths; prefer running commands inside containers.
- Line endings: `.gitattributes` with `* text=auto eol=lf`, `*.ps1 text eol=crlf`; shell scripts must be LF (or containers fail with `\r`).
- Performance on Windows bind mounts: acceptable for dev; if slow, document option to clone into WSL filesystem.
- `scripts/dev-up.ps1` / `dev-up.sh`: copy `.env.example`→`.env` if missing, `docker compose up -d --build`, migrate, seed.

### docker-compose services (dev)
`postgres` (pgvector/pgvector:pg16) · `redis:7` · `minio` + `minio-init` (create buckets, policies) · `mailpit` · `clamav` (clamav/clamav:stable) · `backend` (runserver / uvicorn reload) · `worker-documents` · `worker-ai` · `worker-default` (default+notifications+reports) · `beat` · `flower` · `frontend` (next dev). Healthchecks + `depends_on: condition: service_healthy`.

## 2. Environments & config
Env vars (see `.env.example`): `DJANGO_SETTINGS_MODULE`, `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`, `S3_BUCKET_QUARANTINE`, `S3_BUCKET_DOCUMENTS`, `S3_BUCKET_EXPORTS`, `S3_BUCKET_PUBLIC`, `EMAIL_URL`/SES settings, `DEFAULT_FROM_EMAIL`, `FIELD_ENCRYPTION_KEYS`, `CLAMAV_HOST`, `CLAMAV_PORT`, `SENTRY_DSN`, `FRONTEND_URL`, `LLM_PROVIDER` (none), `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `EMBEDDING_MODEL`, `PAYNOW_INTEGRATION_ID`, `PAYNOW_INTEGRATION_KEY`, `NEXT_PUBLIC_SITE_URL`, `API_INTERNAL_URL`.

## 3. Production (AWS) — default design
| Item | Choice |
|---|---|
| Region | `af-south-1` (Cape Town) preferred for latency/data proximity (D-07 owner confirmation) |
| Compute | EC2 Ubuntu 24.04 LTS; start `t3.xlarge` (4 vCPU/16 GB) single host for pilot: nginx, frontend, backend, workers, beat, clamav (Docker Compose prod profile) |
| DB | Amazon RDS PostgreSQL 16 (db.t4g.medium), Multi-AZ optional, automated backups 14–35 days, PITR; `pgvector` extension enabled |
| Redis | Container on host (pilot) → ElastiCache later |
| Storage | S3 buckets with Block Public Access (except public logos via CloudFront/OAC optional), SSE, versioning on documents bucket, lifecycle rules (quarantine 1 day, exports 1 day) |
| Email | SES (domain verified, DKIM, SPF, DMARC), bounce/complaint SNS → webhook endpoint → suppression list |
| DNS/TLS | Domain (e.g. `hr.mudhotech.co.zw` — D-09), Nginx + Certbot auto-renew |
| Secrets | SSM Parameter Store → rendered into `.env` at deploy by `deploy.sh` (instance role) |
| Monitoring | Sentry (backend+frontend), CloudWatch agent (logs, disk, mem), uptime check (healthz), Flower behind basic auth + IP allow-list |
| Backups | RDS automated + weekly logical `pg_dump` to S3 (encrypted, 35-day lifecycle); S3 versioning |
| CI/CD | GitHub Actions: build images → push to GHCR/ECR → SSH (or SSM Run Command) deploy → `docker compose pull && up -d` → migrate → smoke test → rollback on failure (previous tag) |

## 4. Deployment procedure (`infrastructure/deployment/deploy.sh`)
1. Pull new image tags. 2. Run `migrate` in one-off container (expand-only migrations). 3. `collectstatic`. 4. Rolling restart: backend → frontend → workers (warm shutdown, `--max-tasks-per-child`), beat last. 5. Smoke: `/readyz`, public jobs page, login page. 6. Tag release; record in `CHANGELOG.md`. Rollback: previous image tags + (if needed) backward-compatible schema means no DB rollback.

## 5. Nginx
`/` → frontend:3000; `/api/` → backend:8000; `/healthz`; gzip/brotli; `client_max_body_size 30m`; rate limit zones `auth` (10r/m) & `search` (60r/m); security headers; HTTP/2; deny dotfiles; access logs JSON.

## 6. Operations runbooks (`docs/runbooks/`)
- `processing-backlog.md` — scale workers, inspect dead letters, retry.
- `restore-database.md` — RDS PITR / pg_restore steps; verification queries.
- `incident-data-leak.md`, `credential-compromise.md`, `malware-detected.md`, `disable-ai.md` (feature flag), `email-deliverability.md`, `certificate-renewal.md`, `disk-full.md`, `rotate-keys.md` (field encryption key rotation with re-encrypt task).

### No-reply mailbox (ADR-024, EC-NOT-06)
Candidates sometimes reply to notification emails. The application never reads that mailbox; instead:

1. Verify the sending domain in SES and use `DEFAULT_FROM_EMAIL="<Org platform name> <no-reply@<domain>>"`.
2. Create an SES **receipt rule** for `no-reply@<domain>`: action 1 = Lambda (or SES "bounce"-style
   template reply) that sends the fixed auto-response below **once per sender per day** and only when
   the incoming mail has no `Auto-Submitted` header (never answer auto-replies); action 2 = **stop**
   (do not store the message - it may contain personal data meant for the employer).
3. Auto-response text (plain text, no personal data, no quoting of the original):

   > Thank you for your message. This address does not accept replies, and your email has not been
   > read or kept. To contact the employer about your application, sign in at <portal URL> and use the
   > **Messages** section of the application. If you cannot sign in, use "Forgot password" on the
   > sign-in page.

4. Monitoring: alert if the rule's invocation count spikes (likely a mail loop or a campaign).

## 7. Scheduled jobs (Celery Beat)
| Job | Schedule |
|---|---|
| outbox relay | every 2 s |
| publish scheduled jobs / close expired jobs / abandon expired drafts | every minute |
| draft deadline reminders (24 h before) | hourly |
| clarification expiry | hourly |
| orphan upload cleanup | daily 02:00 |
| retention & anonymisation | daily 03:00 (per-org dry-run report weekly) |
| email suppression sync | hourly |
| AI quality/override metrics aggregation | daily 04:00 |
| freshclam freshness check | daily |
| session cleanup | daily |
| billing: invoices/dunning/usage roll-up (v1.1) | daily |

## 8. SLOs & alerts
Submission availability 99.5%; alert when: 5xx rate > 2% over 5 min; queue depth `documents` > 500 or oldest task > 15 min; dead letters > 10; disk > 80%; cert expiry < 14 days; ClamAV DB > 48 h old; email failure rate > 5%.
