# Staging environment — bring-up and acceptance (P11-T09)

Staging mirrors production (same images, compose file, nginx template, deploy script) with **synthetic data only**,
a smaller instance, and two differences: email is caught by **Mailpit** (compose profile `staging`) instead of
being sent through SES, and nginx rate limits are raised so the E2E suite (one runner IP) is not throttled.

Steps marked 👤 need the owner (AWS account, domain, GitHub settings). Everything else is scripted.

## 1. Infrastructure 👤
Follow `docs/deployment/AWS_SETUP.md` with `ENV=staging` and `DOMAIN=staging.<domain>` (t3.large, db.t4g.small,
`mhrs-staging-*` buckets). SES is not needed for staging (Mailpit), but the SNS feedback topic can wait for
production.

## 2. Host
```bash
sudo git clone https://github.com/king-Mudho/MUDHOTECH-HR-RECRUITING-SYSTEM.git /opt/mhrs
sudo MHRS_ENVIRONMENT=staging OPS_ALLOW_IPS="<operator-ip>/32" DEPLOY_SSH_KEY="<public key of the CI deploy key>" \
     bash /opt/mhrs/infrastructure/deployment/ec2-bootstrap.sh
sudo chown -R mhrs:mhrs /opt/mhrs
# Mailpit basic auth for the staging E2E workflow (and for you to read staging mail in a browser)
sudo htpasswd -B -c /etc/mhrs/nginx/mailpit.htpasswd e2e        # remember the password -> STAGING_MAILPIT_AUTH
```

## 3. SSM parameters 👤
Everything in AWS_SETUP §6 under `/mhrs/staging/`, with these staging values:

| Parameter | Staging value |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.staging` |
| `COMPOSE_PROFILES` | `staging` (starts Mailpit) |
| `EMAIL_URL` | `smtp://mailpit:1025` |
| `DEFAULT_FROM_EMAIL` | `MUDHOTECH HR RECRUITING SYSTEM <no-reply@staging.<domain>>` |
| `DEMO_PASSWORD` | a long random password shared by the synthetic accounts (SecureString) |
| `MHRS_AUTH_RATE`, `MHRS_SEARCH_RATE` | `120r/m`, `600r/m` (production keeps the defaults 10r/m / 60r/m) |
| `SENTRY_ENVIRONMENT`, `OPS_METRICS_NAMESPACE` | `staging`, `MHRS/staging` |
| `GHCR_READ_TOKEN` | read-only package token (if the images are private) |

## 4. GitHub 👤
*Settings → Environments → `staging`*:
- secrets `STAGING_HOST`, `STAGING_SSH_KEY` (private half of the deploy key), `STAGING_SSH_KNOWN_HOSTS`
  (`ssh-keyscan -t ed25519 <host>`), `DEMO_PASSWORD` (same as SSM), `STAGING_MAILPIT_AUTH` (`e2e:<password>`);
- variable `STAGING_URL` = `https://staging.<domain>`.

## 5. DNS, certificate, first deploy
1. 👤 `A staging.<domain> → <Elastic IP>`; CAA as in AWS_SETUP §8.
2. On the host: `sudo /opt/mhrs/infrastructure/deployment/certbot.sh issue staging.<domain> <contact-email>`.
3. GitHub → Actions → **Deploy (staging)** → *Run workflow* (later deploys run automatically after every green CI
   on `main`). It builds/pushes `sha-<commit>` images and runs `deploy.sh` on the host (migrations, rolling start,
   smoke tests).
4. On the host, as `mhrs`: `/opt/mhrs/infrastructure/deployment/seed-staging.sh --core`, then take a baseline
   snapshot for resets: `aws rds create-db-snapshot --db-instance-identifier mhrs-staging-db --db-snapshot-identifier mhrs-staging-seeded`.
5. `sudo /opt/mhrs/infrastructure/deployment/backup.sh --install-timer`.

## 6. Acceptance (the P11-T09 evidence)
| Check | How | Expected |
|---|---|---|
| Staging checks (E2E + ZAP) | Actions → **Staging checks** → *Run workflow* with **core scenario = true** (first run after a fresh seed) | Playwright: all specs pass on desktop + phone (axe included); ZAP: no FAIL rules |
| Automatic chain | push any commit to `main` | CI → Deploy (staging) → Staging checks (core scenario skipped) all green |
| Rolling deploy without errors | `5xx-rate` alarm and nginx log during a deploy | no 5xx |
| Restore drill on RDS | `docs/runbooks/restore-database.md` (PITR + logical) | timings recorded in its drill table |
| Alarms reach on-call | `ENV=staging ONCALL_EMAIL=... infrastructure/monitoring/alarms.sh`, then `alarms.sh --test` | test email received |
| TLS | SSL Labs on `staging.<domain>` | A+ |

Record the results here:

| Date | Commit | Staging checks run | E2E | ZAP | Restore drill | Alarm test | SSL Labs |
|---|---|---|---|---|---|---|---|
| _pending_ | | | | | | | |

## Operating notes
- Reset to the seeded state: restore `mhrs-staging-seeded` (PITR runbook, path A) or rerun `seed-staging.sh`
  (it is additive). The core scenario can only run once per seed (it approves the seeded shortlist), which is why
  the automatic staging checks skip it.
- Read staging mail: `https://staging.<domain>/mailpit/` (basic auth).
- Never copy production data to staging (CDPA; CLAUDE.md §2).
