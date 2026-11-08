# PHASE 11 — Production Deployment & Operations (→ v1.0 pilot live)

**Release:** MVP · **Depends on:** Phase 10
**Read first:** `docs/10_DEPLOYMENT_OPERATIONS.md` (all), `docs/06 §7`

> STOP condition: real AWS credentials, domain DNS, SES verification and secrets require the owner. Prepare everything
> (scripts, IaC docs, checklists) and then ask the owner to supply/execute the credential-dependent steps.

## Tasks
- [ ] **P11-T01** — Production images: multi-stage, non-root, healthchecks, pinned bases, SBOM (syft) ; `docker-compose.prod.yml` (nginx, frontend standalone output, backend gunicorn+uvicorn workers, worker pools, beat, clamav, redis) with resource limits & restart policies.
- [ ] **P11-T02** — Nginx config per `docs/10 §5` + Certbot automation script; staging and prod server blocks.
- [ ] **P11-T03** — `infrastructure/deployment/ec2-bootstrap.sh` (Ubuntu 24.04: updates, unattended-upgrades, docker engine + compose plugin, chrony, ufw (80/443, 22 restricted), fail2ban, CloudWatch agent, swap, log rotation, deploy user).
- [ ] **P11-T04** — `docs/deployment/AWS_SETUP.md` step-by-step: VPC/SG, EC2 + IAM instance role (S3, SES, SSM read), RDS PostgreSQL 16 (pgvector), S3 buckets (block public access, SSE, versioning, lifecycle), SES domain + DKIM/SPF/DMARC + SNS bounce topic, SSM parameters list, Sentry projects, budgets/alarms.
- [ ] **P11-T05** — `deploy.sh` (pull, migrate, collectstatic, rolling restart, smoke, rollback) + `.github/workflows/deploy-staging.yml` (auto on main) and `deploy-prod.yml` (manual approval, tag-based).
- [ ] **P11-T06** — Backups: RDS automated + `backup.sh` logical dump to S3 weekly; `restore.sh`; **restore drill** on staging documented in `docs/runbooks/restore-database.md` with timings (RPO/RTO evidence).
- [ ] **P11-T07** — Monitoring/alerting per `docs/10 §8`: Sentry release tracking, CloudWatch alarms, uptime checks, queue-depth exporter or periodic check task posting metrics; on-call contact config.
- [ ] **P11-T08** — Runbooks in `docs/runbooks/` (all listed in `docs/10 §6`).
- [ ] **P11-T09** — Staging environment live with synthetic seed; full E2E smoke against staging URL; ZAP baseline against staging.
- [ ] **P11-T10** — Production go-live checklist `docs/deployment/GO_LIVE_CHECKLIST.md` (gates from Phase 10, D-08 legal sign-off, DNS, TLS A+ (SSL Labs), SES out of sandbox, admin MFA, secrets rotated from defaults, backups verified, monitoring firing test alerts) → owner executes/approves.
- [ ] **P11-T11** — HR onboarding/training material: short walkthrough doc + recorded-script outline; pilot support process.
- [ ] **P11-T12** — Tag `v1.0.0`; CHANGELOG; release notes.

## Edge cases
EC-OPS-04..10 (graceful deploys, expand/contract migrations, NTP, dead-letter alerting, disk alerts, ClamAV freshness, traffic spikes via ISR/caching + rate limits).

## Exit criteria
- [ ] Staging fully operational; prod deployed (or ready pending owner credentials with checklist).
- [ ] Restore drill done; alerts verified; go-live checklist signed in PROGRESS.md.
