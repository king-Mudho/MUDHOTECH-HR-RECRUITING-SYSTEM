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

### 3.1 Database roles (row-level security, ADR-012)
The application **must connect as a non-superuser role without `BYPASSRLS`** (e.g. `mhrs_app`, owner of the
schema objects is a separate migration role or the same role created with `NOSUPERUSER NOBYPASSRLS`).
PostgreSQL superusers and `BYPASSRLS` roles ignore row-level security even with `FORCE`, so the second line of
tenant defence would silently be off. On RDS the master user is `rds_superuser` (not a true superuser) and is
subject to RLS; still create a dedicated `mhrs_app` role for the application. The local Docker database uses a
superuser for convenience, so RLS is exercised in tests through a probe role (`apps/core/tests/test_rls.py`).

### 3.2 Application server and connection pool (ADR-029)
The API runs as **gunicorn WSGI with threaded workers** (`docker/entrypoint-prod.sh`: `GUNICORN_WORKERS`
default 3, `GUNICORN_THREADS` default 8). Database connections are pooled per process (psycopg pool via Django:
`DB_POOL_MIN` 1, `DB_POOL_MAX` 10, `DB_POOL_TIMEOUT` 10 s; `DB_POOL=false` falls back to persistent connections).
Celery workers keep one persistent connection per process (no pool: they fork). Keep `web workers × DB_POOL_MAX + Celery processes + headroom` below PostgreSQL
`max_connections` (RDS db.t4g.medium ≈ 400; the default container 100): e.g. 3 × 10 + 7 + 20 = 57.

### 3.3 Production images and compose (P11-T01)
| Image | Dockerfile | Contents |
|---|---|---|
| `mhrs-backend` | `backend/Dockerfile` | API (gunicorn gthread, §3.2), beat, flower, one-off `migrate` |
| `mhrs-worker` | `backend/Dockerfile.worker` | Celery workers + Tesseract/poppler + the baked local embedding model (offline) |
| `mhrs-frontend` | `frontend/Dockerfile` (`runtime` target) | Next.js standalone server |

- **Multi-stage:** a `builder` stage resolves the locked environment with uv (`--no-dev` for production builds);
  the `runtime` stage carries only `/opt/venv` (+ the model cache for workers) and the source. uv is not in the
  runtime image.
- **Non-root:** every runtime runs as uid/gid `10001` (`app`). In `docker-compose.prod.yml` application containers
  also drop all Linux capabilities and set `no-new-privileges`; the frontend runs with a read-only root filesystem.
- **Pinned bases:** `python:3.12.16-slim-trixie`, `node:24.22.3-alpine3.24`, `nginx:1.30.7-alpine3.24`,
  `redis:7.4.12-alpine3.22`, `clamav/clamav:1.5.4`, uv `0.13.9`. Dependabot (`.github/dependabot.yml`) proposes
  monthly bumps; never use `latest`. Application services take `MHRS_TAG` (required, the release tag).
- **Version:** builds pass `MHRS_VERSION` (git SHA or tag); it is an OCI label and the Sentry `release`.
- **SBOM:** CI generates SPDX JSON SBOMs with syft for all three images (artifact `sbom`, 90 days) and scans the
  backend image with Trivy; releases attach the SBOMs (P11-T12).
- **Health and limits** (t3.xlarge, 16 GB): every service has a healthcheck, `restart: unless-stopped`, rotated
  JSON logs (5 × 20 MB) and CPU/memory limits (total ≈ 10.5 GB; flower is on the `ops` profile).

| Service | Memory | Healthcheck |
|---|---|---|
| nginx | 128 MB | `nginx -t` |
| redis | 512 MB (`maxmemory` 384 MB, `noeviction`) | `redis-cli ping` |
| clamav | 1.5 GB | `clamdcheck.sh` (5 min start period for signatures) |
| backend | 1.5 GB | `GET /healthz` |
| worker-default / -documents / -ai | 1 GB / 1.5 GB / 2.5 GB | `celery inspect ping` addressed to itself |
| beat | 256 MB | schedule file rewritten in the last 10 minutes |
| frontend | 768 MB | `GET /robots.txt` |

Workers get a 120 s warm-shutdown grace period (tasks are `acks_late`, so anything cut off is re-delivered).
Django static files are collected into the `static` volume and served by nginx from `/srv/static`.
`backend/tests/integration/test_prod_compose.py` enforces these rules.

### 3.4 Host bootstrap (P11-T03)
`sudo [variables] bash infrastructure/deployment/ec2-bootstrap.sh` prepares a fresh Ubuntu 24.04 instance and is safe
to re-run (e.g. to change the operator allow-list).

| Area | What it sets |
|---|---|
| Updates | full upgrade, then `unattended-upgrades` for **security origins only** with automatic reboot at 03:30 UTC (Docker Engine is upgraded in a deploy window) |
| Time | chrony preferring the Amazon Time Sync Service `169.254.169.123`; host TZ UTC (EC-OPS-06) |
| Docker | Engine + compose/buildx plugins from Docker's apt repository; `daemon.json`: rotated JSON logs (5 × 20 MB), `live-restore`, `no-new-privileges`, no userland proxy |
| Firewall | ufw deny-by-default; 80/443 open; 22 only from `SSH_ALLOW_CIDR` (empty = closed, use SSM Session Manager). The security group is the outer boundary |
| SSH | no root login, keys only, 3 tries; fail2ban `sshd` jail (5 failures / 10 min → 1 h ban) |
| Memory | `SWAP_SIZE_GB` swap file (default 4), `vm.swappiness=10`, `vm.overcommit_memory=1` (Redis) |
| Kernel | rp_filter, no ICMP redirects, syncookies, `somaxconn 1024` |
| Monitoring | CloudWatch agent with `infrastructure/monitoring/cloudwatch-agent.json`: namespace `MHRS/<env>` (memory, swap, disk `/` + `/var/lib/docker`, iowait/steal), log groups `/mhrs/<env>/containers` (30 days) and `/mhrs/<env>/host` (90 days) |
| Tools | AWS CLI v2 (snap), certbot, `htpasswd`, `psql` 16 |
| Users | `mhrs` deploy user in the `docker` group, key from `DEPLOY_SSH_KEY`; `/opt/mhrs` (app), `/var/log/mhrs` (logrotate weekly × 8), `/var/www/certbot` |
| nginx host files | `/etc/mhrs/nginx/ops-allowlist.conf` from `OPS_ALLOW_IPS` (always ends `deny all;`), empty `flower.htpasswd` |

## 4. Deployment procedure (`infrastructure/deployment/deploy.sh`)
1. Pull new image tags. 2. Run `migrate` in one-off container (expand-only migrations), then `load_taxonomy` and, in a worker container, `embed_skills` (only new or other-model skill vectors are computed; ADR-025). 3. `collectstatic`. 4. Rolling restart: backend → frontend → workers (warm shutdown, `--max-tasks-per-child`), beat last. 5. Smoke: `/readyz`, public jobs page, login page. 6. Tag release; record in `CHANGELOG.md`. Rollback: previous image tags + (if needed) backward-compatible schema means no DB rollback.

**As built (P11-T05).**

| Step | `deploy.sh <tag>` (as `mhrs` in `/opt/mhrs`; `flock` prevents parallel runs) |
|---|---|
| 1. Config | `/mhrs/<env>/` from SSM → `.env` (0600, values single-quoted so Compose never interpolates `$` in secrets; multi-line or quoted values refused; `GHCR_READ_TOKEN` is used for `docker login` only and never reaches containers). Environment from `/etc/mhrs/environment` (bootstrap) |
| 2. Code | `git checkout --detach <tag>` (compose file, nginx templates, scripts are versioned with the images) |
| 3. Images | `docker compose pull` of `ghcr.io/<owner>/mhrs-{backend,worker,frontend}:<tag>` + pinned infra images |
| 4. Schema | one-off containers: `migrate` (expand-only), `load_taxonomy`, `embed_skills` (worker image), `check --deploy` |
| 5. Roll | **backend, frontend side by side:** the new container starts next to the old one (`--scale 2 --no-recreate`); when healthy, nginx's upstream file (`/etc/mhrs/nginx/upstreams/<svc>.conf`) is pointed at the new container and nginx reloads gracefully; the old container is stopped (40 s drain) and removed; the upstream goes back to the service name. A new container that never becomes healthy is removed and the old one keeps serving. **Workers** restart in place with warm shutdown (120 s, `acks_late`), **beat** last, **nginx** re-renders its template and reloads gracefully |
| 6. Smoke | `/readyz` inside the backend; `/healthz`, `/jobs`, `/login`, `/api/v1/jobs/` through nginx with the real certificate. Failure → automatic redeploy of the previous release with `--skip-migrate` |
| 7. Record | `releases/current`, `releases/previous`, `releases/history`; `docker image prune` (images older than 7 days, EC-OPS-08) |

`deploy.sh rollback` redeploys `releases/previous` without migrations; `deploy.sh status` shows both and the running
images. **Rehearsal:** `infrastructure/deployment/test-rolling-deploy.sh` runs nginx with the production template and
stand-in servers with gunicorn's shutdown semantics, rolls both services under continuous traffic and fails on any
non-200 (CI infra job; locally ~230 requests, 0 failures). Upstream keepalive: nginx closes idle connections after
4 s, before gunicorn (`--keep-alive 5`) and Node (5 s) do.

**Pipelines.** `deploy-staging.yml`: after every green CI run on `main` it builds and pushes the three images as
`sha-<commit>` (BuildKit SBOM + provenance attestations, GHA cache) and deploys them to staging over SSH; the deploy
job is skipped with a notice until the owner adds the `staging` environment secrets (`STAGING_HOST`,
`STAGING_SSH_KEY`, `STAGING_SSH_KNOWN_HOSTS`). `deploy-prod.yml`: a `vX.Y.Z` tag (or a manual run with a tag)
**re-tags the staging images of that commit** — production only ever runs bits that ran on staging; it refuses a
commit that was never deployed to staging — then deploys after the `production` environment's required reviewer
approves. Rollback in production = run the workflow manually with the previous tag (or `deploy.sh rollback`).

## 5. Nginx
`/` → frontend:3000; `/api/` → backend:8000; `/healthz`; gzip/brotli; `client_max_body_size 30m`; rate limit zones `auth` (10r/m) & `search` (60r/m); security headers; HTTP/2; deny dotfiles; access logs JSON.

**As built (P11-T02).** `infrastructure/nginx/templates/default.conf.template` is rendered by the official image at
start (`envsubst` of `MHRS_DOMAIN` and `MHRS_ENVIRONMENT` only, `NGINX_ENVSUBST_FILTER=^MHRS_`) into
`conf.d/default.conf`, replacing the stock site. Staging and production use the same template; the
`env-staging.conf` / `env-production.conf` snippet adds per-environment directives (staging: `X-Robots-Tag: noindex`).

| Path | Behaviour |
|---|---|
| port 80 | ACME webroot `/.well-known/acme-challenge/`, `/healthz`, everything else 301 → HTTPS |
| unknown `Host` on 443 | connection closed (444) |
| `/api/v1/auth/` | `auth` zone: **POST only**, 10/min per IP, burst 5 (session GETs are never throttled) |
| `/api/v1/jobs/`, `/jobs` | `search` zone: 60/min per IP, burst 30 |
| `/django-admin/`, `/api/docs/`, `/api/schema/`, `/readyz` | operator IP allow-list (`/etc/mhrs/nginx/ops-allowlist.conf`) |
| `/flower/` | allow-list + basic auth (`/etc/mhrs/nginx/flower.htpasswd`); flower runs on the `ops` profile |
| `/static/` | Django static files from the shared volume, 7-day cache |
| `/_next/static/` | content-hashed assets, 1-year cache |
| dotfiles | 404 |

- **TLS:** TLS 1.2/1.3, ECDHE AEAD suites, session tickets off, HTTP/2, HSTS 1 year + `includeSubDomains` + `preload`.
  No OCSP stapling (Let's Encrypt retired OCSP in 2025). The certificate lineage is always `mhrs`
  (`/etc/letsencrypt/live/mhrs/`).
- **Headers:** nginx owns HSTS, `nosniff` and `X-Request-ID` (passed upstream as the request id); CSP and the other
  headers come from the apps (tested with the code). `server_tokens off`.
- **Logs:** JSON (`mhrs_json`) with `$uri`, never the query string (tokens / personal data).
- **Brotli:** not in the official image; gzip only (a custom build is not worth it for the pilot).
- **Certificates:** `sudo infrastructure/deployment/certbot.sh issue <domain> <email>` (host certbot; first issue
  standalone with nginx stopped, then renewals switch to webroot), `certbot.timer` renews twice a day and a deploy
  hook reloads nginx; `certbot.sh status` shows expiry. Runbook: `docs/runbooks/certificate-renewal.md`.
- **Validation:** `infrastructure/nginx/test-config.sh` renders both environments in the pinned image and fails on any
  `nginx -t` error or warning (CI images job).

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

**As built (P11-T07).** Every alarm notifies the SNS topic `mhrs-<env>-alerts` (on-call email subscription;
`infrastructure/monitoring/alarms.sh` creates/updates all of them idempotently; `alarms.sh --test` fires one end to end).

| Source | Metrics (namespace `MHRS/<env>`) | Alarm |
|---|---|---|
| `apps/core/ops_metrics.py` (beat, every minute; CloudWatch when `OPS_METRICS_NAMESPACE` is set, else a log line) | `QueueDepth[Queue]`, `ProcessingBacklogAgeSeconds`, `OutboxLagSeconds`, `DeadLettersOpen`, `EmailFailureRatePercent`, `EmailsProcessedLastHour`, `ClamavSignatureAgeHours`, `OpsMetricSourceErrors` | documents queue > 500; oldest unfinished application > 15 min; outbox lag > 5 min; dead letters > 10 (EC-OPS-07); email failures > 5 %/h; ClamAV signatures > 48 h (EC-OPS-09, missing = breaching); no metrics for 10 min (beat/worker down); a metric source failing |
| nginx access log → `/var/log/mhrs/nginx/access.json` → CloudWatch agent → log group `/mhrs/<env>/nginx` + metric filters | `Requests`, `Server5xx` | 5xx rate > 2 % over 5 min (metric math, only with ≥ 50 requests) |
| `infrastructure/monitoring/host-checks.sh` (systemd timer, 15 min) | `CertDaysLeft`, `UnhealthyContainers`, `ContainersRunning`, `BackupAgeHours` | certificate < 14 days; any unhealthy/restarting container; no successful backup for 8 days |
| `backup.sh` | `BackupSucceeded` | a backup run failed |
| CloudWatch agent | `mem_used_percent`, `disk_used_percent[path]` | memory > 90 %; `/` or `/var/lib/docker` > 80 % (EC-OPS-08) |
| AWS | EC2 status/CPU, RDS CPU/storage/connections, SES bounce/complaint rate | status check → also EC2 *recover*; CPU > 85 %/80 %; < 10 GB free; > 200 connections; bounces > 4 %, complaints > 0.08 % |

Sentry: backend events carry `release` = the image tag (`MHRS_VERSION`) and `environment` (`SENTRY_ENVIRONMENT`),
so a regression is tied to the deploy that introduced it. Uptime: an external HTTPS check of `/healthz` every
minute (Route 53 health check or an uptime service, owner's choice) alerting the same on-call address.
