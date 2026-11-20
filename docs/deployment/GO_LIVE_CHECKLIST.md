# Production go-live checklist — MUDHOTECH HR RECRUITING SYSTEM v1.0 (P11-T10)

Production opens to the pilot organisations only when **every** item below is ticked with its evidence.
The owner signs at the end; the signed copy (date, commit, release tag) is recorded in `PROGRESS.md` (P11 exit).
Items marked 👤 are the owner's; the rest are verified by engineering and initialled by the owner.

## Production on the shared VPS (ADR-033, owner decision 2026-11-20)

Production is **https://hr.agribizframework.com** on the shared agribizframework VPS (66.29.139.201),
deployed with `infrastructure/vps/`. Items in sections C, E and F that name AWS services (RDS, S3, SES,
CloudWatch, SSM, staging host) are replaced by the VPS equivalents below; sections A, B, D, G and H
still apply.

| Item | Status (2026-11-20) | Evidence |
|---|---|---|
| DNS `hr` -> 66.29.139.201 | ✅ | `check-production.sh` |
| TLS certificate (Let's Encrypt, auto-renew), HTTP -> HTTPS, HSTS 1 year | ✅ | valid until 2027-02-18; `check-production.sh` |
| Secrets generated on the server (Django, field encryption, database, S3); nothing default | ✅ | `setup-server.sh`; `.env` mode 600 |
| Database role without superuser / BYPASSRLS (row-level security applies) | ✅ | `mhrs_app` |
| Isolation from the four sibling sites (users, ports, databases, nginx blocks) | ✅ | all sibling sites 200 after deploy |
| Platform admin account | ✅ | `create-admin.sh` (owner typed the password) |
| Platform admin two-factor authentication 👤 | ☐ | mandatory after 7 days |
| Outgoing email (Gmail SMTP, ~500/day) 👤 | ✅ | `configure-email.sh` test email delivered |
| Nightly backups (database, file storage, keys) | ✅ | `mhrs-backup.timer` 01:45, 14 days |
| Restore drill | ✅ | `restore-drill.sh`: 1.2 MB dump restored in 4 s, all key tables match |
| Off-server copy of backups 👤 | ☐ | pending (needs a storage account) |
| Monitoring and alert email | ✅ | `mhrs-monitor.timer` every 5 min; test alert + stop/start fire test emailed 2026-11-20 |
| Integrations in sandbox, billing not enforced | ✅ (by design) | `INTEGRATIONS_SANDBOX=true`, `BILLING_ENFORCE=false` |
| Semantic skill matching | ⚠️ off | CPU has no AVX2 (D-029); ask the host for CPU passthrough |
| Pre-release verification without a staging host | ✅ | nightly CI stack (Playwright + axe + ZAP) and local fresh-database E2E pass |

Live commit at sign-off: `67d8eb6`.

Release: `v1.0.0` · Commit: `________` · Planned go-live: `____-__-__ __:__ UTC` (low-traffic window)

## A. Quality and security gates (Phase 10 exit criteria)
| # | Gate | Evidence | ✓ |
|---|---|---|---|
| A1 | No known critical/high vulnerabilities | latest nightly *Security scans* green: Semgrep, bandit, pip-audit, Trivy fs + images; accepted deviations listed in `docs/reports/DEFECT_LOG.md` with expiry | ☐ |
| A2 | End-to-end submission and shortlist flow | latest nightly E2E green on desktop + phone, **and** the staging run with *core scenario = true* (`docs/deployment/STAGING.md` §6) | ☐ |
| A3 | Evidence-grounded assessments with human approval | grounding 100 % and human-actor audit 100 % (`docs/reports/AI_VALIDATION_REPORT.md`); `manage.py check_human_decisions` → 0 on staging | ☐ |
| A4 | Tenant isolation 100 % | CI cross-tenant suite + permission matrix green on the release commit | ☐ |
| A5 | Privacy and retention implemented | rights requests, erasure + `verify_erasure`, retention jobs (Phase 09); privacy notice published per organisation | ☐ |
| A6 | AI validation thresholds | `docs/reports/AI_VALIDATION_REPORT.md` + `docs/reports/fairness_2026-11-17.md` (no perturbation changed a result); deviations accepted by the owner | ☐ |
| A7 | Performance NFRs | `docs/reports/PERFORMANCE.md` (job board P95, HR P95, 1,000 concurrent submissions, resilience) | ☐ |
| A8 | Release CI green | CI, Deploy (staging) and Staging checks green for the tagged commit | ☐ |

## B. Legal and compliance 👤 (D-08)
| # | Item | Evidence | ✓ |
|---|---|---|---|
| B1 | Counsel reviewed CDPA [Ch. 12:07] / SI 155 of 2024 obligations: POTRAZ registration/licensing as needed, DPO appointed or designated | counsel's written sign-off (date, name) | ☐ |
| B2 | Data processing agreement signed with each pilot organisation | `docs/legal/DPA_TEMPLATE.md` as reviewed by counsel; signed copies stored by the owner | ☐ |
| B3 | Privacy notice, terms and AI notice approved | public pages + each organisation's notice text | ☐ |
| B4 | Breach-notification deadlines and authority contact filled in | table at the end of `docs/runbooks/incident-data-leak.md` | ☐ |
| B5 | Cross-border transfer position (AWS `af-south-1`, Sentry, GitHub) confirmed | counsel note; Sentry PII scrubbing on (AWS_SETUP §9) | ☐ |
| B6 | DPIA reviewed and accepted | `docs/dpia/DPIA.md` signed by the DPO/owner | ☐ |

## C. Infrastructure and configuration
| # | Item | How to verify | ✓ |
|---|---|---|---|
| C1 | 👤 AWS production account set up per `docs/deployment/AWS_SETUP.md` | its §11 checklist fully ticked | ☐ |
| C2 | Host bootstrapped (`ec2-bootstrap.sh`, `MHRS_ENVIRONMENT=production`) | `ufw status`, `timedatectl` (NTP synchronised), `docker info`, `systemctl list-timers` shows certbot, host-checks | ☐ |
| C3 | 👤 DNS: `A <domain>` → Elastic IP, CAA `letsencrypt.org` | `dig +short <domain>`, `dig CAA <domain>` | ☐ |
| C4 | TLS certificate issued; **SSL Labs A+** | `certbot.sh status`; ssllabs.com report saved | ☐ |
| C5 | 👤 SES out of the sandbox; domain DKIM verified; SPF + DMARC published; SNS feedback subscribed | SES console; `send_test_email --to <owner>` arrives with `dkim=pass`; app log shows the SNS subscription confirmed | ☐ |
| C6 | No-reply mailbox receipt rule (ADR-024) | test reply gets the fixed auto-response once | ☐ |
| C7 | **Secrets rotated from defaults**: unique `SECRET_KEY`, `FIELD_ENCRYPTION_KEYS` (offline copy with the owner), DB password, SMTP credentials; no `DEMO_PASSWORD`, no `PLATFORM_ADMIN_PASSWORD` left in SSM; no dev values (`.env.example`) anywhere | `aws ssm get-parameters-by-path --path /mhrs/production/ --query 'Parameters[].Name'` reviewed; `deploy.sh` rendered `.env` mode 0600 | ☐ |
| C8 | Database role: app connects as `mhrs_app` (`NOSUPERUSER NOBYPASSRLS`), `rds.force_ssl=1` | `SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname='mhrs_app'` → `f f` | ☐ |
| C9 | Production compose profile has **no** `staging`/`ops` services running (no Mailpit) | `$DC ps` | ☐ |
| C10 | Operator allow-list and flower/mailpit htpasswd set as intended | `/etc/mhrs/nginx/ops-allowlist.conf` reviewed; `/django-admin/` returns 403 from outside | ☐ |

## D. Access and accounts
| # | Item | How to verify | ✓ |
|---|---|---|---|
| D1 | Platform administrators created with `create_platform_admin`; **MFA enrolled** for every admin and staff member with elevated rights | platform admin → users; sign-in requires the second factor | ☐ |
| D2 | Bootstrap password variables removed from SSM after use | C7 | ☐ |
| D3 | 👤 GitHub `production` environment: required reviewer (owner), tag rule `v*`, secrets `PROD_HOST` / `PROD_SSH_KEY` / `PROD_SSH_KNOWN_HOSTS` | Settings → Environments | ☐ |
| D4 | Least privilege: no long-lived AWS keys on the host; IAM users with MFA | IAM credential report | ☐ |

## E. Backups and recovery
| # | Item | How to verify | ✓ |
|---|---|---|---|
| E1 | RDS automated backups (14–35 days) + PITR on; deletion protection on | RDS console | ☐ |
| E2 | Weekly logical backup timer installed and **one backup run verified** | `backup.sh --install-timer`; first manual run uploaded with `.sha256` | ☐ |
| E3 | **Restore drill done on staging RDS** with timings within RPO ≤ 5 min / RTO ≤ 2 h | drill table in `docs/runbooks/restore-database.md` | ☐ |
| E4 | `FIELD_ENCRYPTION_KEYS` offline copy tested (can decrypt a staging value) | owner confirms | ☐ |

## F. Monitoring and alerting
| # | Item | How to verify | ✓ |
|---|---|---|---|
| F1 | `alarms.sh` run for production with the on-call email; SNS subscription confirmed | CloudWatch alarms list (23) | ☐ |
| F2 | **Monitoring fires test alerts**: `alarms.sh --test` email received by on-call | screenshot / email | ☐ |
| F3 | Ops metrics arriving (`OPS_METRICS_NAMESPACE=MHRS/production`) | CloudWatch metrics `MHRS/production` show `DeadLettersOpen`, `QueueDepth` within 5 min of deploy | ☐ |
| F4 | External uptime check on `https://<domain>/healthz` (1 min) alerting on-call | uptime service / Route 53 health check | ☐ |
| F5 | Sentry production projects receive a test event tagged with the release | Sentry issue for `v1.0.0` | ☐ |

## G. Release and cut-over
| # | Item | How to verify | ✓ |
|---|---|---|---|
| G1 | `CHANGELOG.md` and `docs/releases/v1.0.0.md` final | reviewed | ☐ |
| G2 | 👤 Tag pushed: `git tag -a v1.0.0 -m "v1.0.0" && git push origin v1.0.0` → **Deploy (production)** approved by the owner | workflow run green (promotes the staging-tested images) | ☐ |
| G3 | Smoke after deploy: public job board, sign-in, an HR applicants page, a test application by a staff test account | `deploy.sh` smoke + manual check | ☐ |
| G4 | Pilot organisations created and verified; their admins invited | platform admin → organisations | ☐ |
| G5 | HR onboarding sessions scheduled; support process live (`docs/training/PILOT_SUPPORT.md`) | calendar | ☐ |
| G6 | Rollback rehearsed: `deploy.sh rollback` on staging restores the previous release | staging log | ☐ |

## H. Decision 👤
- [ ] All items above are ticked, or exceptions are listed here with an owner-accepted mitigation and date:

| Exception | Mitigation | Accepted by / date |
|---|---|---|
| | | |

**Go-live approved** by ______________________ (MudhoTech Solutions (Pvt) Ltd) on ____-__-__.

## After go-live (first 2 weeks)
Daily: alarms, dead letters, AI quality counters, support queue. Weekly: restore check of the latest dump (listing),
override analytics per vacancy, pilot feedback review. At 2 weeks: pilot retrospective → backlog for Phase 12+.
