# Deploying MHRS to the shared VPS (hr.agribizframework.com)

Same server and same pattern as the sibling apps (ABI, DRP, AMA, mudhotech.com on 66.29.139.201):
its own system user, directory, ports, database, systemd units and nginx server block, installed
beside them without touching them. The AWS/Docker design in `docs/10_DEPLOYMENT_OPERATIONS.md`
stays the long-term target; this is the native single-server deployment.

| | Value |
|---|---|
| Address | https://hr.agribizframework.com |
| User / directory | `mhrs`, `/srv/mhrs` |
| Ports (loopback only) | API 8400, frontend 3400, S3 8533 (+9533/8580/8588), ClamAV 3410 |
| Database | `mhrs_prod`, role `mhrs_app` (no superuser, no BYPASSRLS: row-level security applies) |
| Redis | shared server Redis, databases 5 (queues) and 6 (cache) |
| Services | `mhrs-backend`, `mhrs-frontend`, `mhrs-worker`, `mhrs-beat`, `mhrs-s3`, `mhrs-clamd`, `mhrs-backup.timer` |
| Node / Python | private Node 24 in `/srv/mhrs/tools/node`; Python 3.12 venv built with uv from `uv.lock` |

All values live in `site.conf`. Secrets are generated on the server by `setup-server.sh` into
`/srv/mhrs/backend/.env` (mode 600) and never leave it.

## Release archive

From this computer, with everything committed (the archive holds committed files only, so no
`.env`, database or personal data can leak into it):

```bash
git archive --format=tar.gz -o mhrs-release.tar.gz HEAD
scp mhrs-release.tar.gz agribizframework:/tmp/
```

## First deployment (as root on the server)

```bash
mkdir -p /srv/mhrs && tar -xzf /tmp/mhrs-release.tar.gz -C /srv/mhrs
bash /srv/mhrs/infrastructure/vps/setup-server.sh
bash /srv/mhrs/infrastructure/vps/deploy.sh
certbot --nginx -d hr.agribizframework.com --redirect
bash /srv/mhrs/infrastructure/vps/create-admin.sh        # you type the password
bash /srv/mhrs/infrastructure/vps/configure-email.sh     # outgoing mailbox; you type the password
bash /srv/mhrs/infrastructure/vps/check-production.sh
```

Until `configure-email.sh` runs, emails (sign-up confirmations included) are only written to the
worker log (`journalctl -u mhrs-worker`). Payments, calendars, SMS and WhatsApp stay in sandbox mode
and billing is not enforced (`INTEGRATIONS_SANDBOX=true`, `BILLING_ENFORCE=false` in `.env`).

## Every update

```bash
git archive --format=tar.gz -o mhrs-release.tar.gz HEAD && scp mhrs-release.tar.gz agribizframework:/tmp/
ssh agribizframework "tar -xzf /tmp/mhrs-release.tar.gz -C /srv/mhrs && bash /srv/mhrs/infrastructure/vps/deploy.sh"
```

`deploy.sh` backs up first and refuses to migrate without a restore point, then installs the
locked dependencies, migrates (expand-only), rebuilds the frontend into a new release, restarts the
services (the worker finishes running tasks first) and checks the site through nginx.

## Rollback and restore

```bash
bash /srv/mhrs/infrastructure/vps/rollback.sh                              # previous frontend release
bash /srv/mhrs/infrastructure/vps/rollback.sh --release /tmp/older.tar.gz  # older code, no migrations
bash /srv/mhrs/infrastructure/vps/rollback.sh --restore-db /srv/mhrs/backups/mhrs-db-<stamp>.dump
```

Backups run nightly at 01:45 (`mhrs-backup.timer`): database dump, file storage and the `.env`
(which holds the field-encryption keys; without it the database backup cannot be read). Kept 14 days
in `/srv/mhrs/backups`. Copy them off the server regularly.

## Monitoring and alerts

`mhrs-monitor.timer` runs `monitor.sh` every 5 minutes: the site over HTTPS (`/readyz`, `/`), the six
services, disk (> 85 %), memory (< 250 MB available), documents queue, processing backlog (> 15 min),
event relay lag, dead letters (> 10), email failures (> 5 %), virus signatures (> 48 h), backup age
(> 26 h) and certificate expiry (< 14 days). It emails `OPS_ALERT_EMAILS` (backend `.env`) when a problem
appears, every 6 hours while it lasts, and once on recovery.

```bash
bash /srv/mhrs/infrastructure/vps/monitor.sh          # run the checks now
bash /srv/mhrs/infrastructure/vps/monitor.sh --test   # send a test alert
bash /srv/mhrs/infrastructure/vps/restore-drill.sh    # prove the latest backup restores
```

## Operations

```bash
systemctl status mhrs-backend mhrs-worker mhrs-beat mhrs-frontend mhrs-s3 mhrs-clamd
journalctl -u mhrs-worker -f                 # CV processing, screening, emails
tail -f /var/log/nginx/mhrs-error.log
```

Memory caps (systemd `MemoryMax`) keep MHRS from crowding out the other sites: worker 2.2 GB,
ClamAV 1.6 GB, API 1 GB, frontend 600 MB, storage 500 MB.
